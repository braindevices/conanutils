# -*- coding: UTF-8 -*-
import shutil
import typing
from conans import tools
from conans import ConanFile
import conans
import yaml
import os
import glob
from .pkg_conf_utils import get_all_pkg_names, get_all_names_in_pkgconfig, MyPkgConfig
import re
VERSION_REGEX = re.compile(r'([0-9.]+)-(.+)-([a-z0-9]+)')

def parse_version(version: str):
    matches = VERSION_REGEX.match(version)
    if matches:
        return matches.groups()
    raise RuntimeError('% does not match version pattern: %s'%version%VERSION_REGEX.pattern)


def libpkg_exists(libname: str, scope_output):
    pkgconf = tools.PkgConfig(libname)
    try:
        pkgconf_vars = pkgconf.variables
        scope_output.info('{} exists'.format(libname))
        return True
    except conans.errors.ConanException as e:
        scope_output.warn('{}'.format(e))
        return False


def get_required_os_field(conandata: typing.Dict[str, typing.Any], field_name: str):
    data = conandata[field_name]
    ret: typing.Dict[str, str] = {}
    if tools.os_info.linux_distro == "ubuntu":
        ret = data['ubuntu']
    elif tools.os_info.linux_distro == "fedora":
        ret = data['fedora']
    elif tools.os_info.is_macos:
        ret = data['osx']
    return ret, data['fallback']


class AutoConanFile(ConanFile):
    exports_dir_path = os.path.realpath('./')
    os_packages = {}
    _source_subfolder = "source_subfolder"
    _build_subfolder = "build_subfolder"


    def git_source(self):
        _target_version, self.repo_branch, self.target_commit = parse_version(self.version)
        git = tools.Git(folder=self._source_subfolder)
        git.clone(
            self.repo_url,
            branch=self.repo_branch,
            shallow=True,
        )
        current_commit = git.get_commit()
        if not current_commit.startswith(self.target_commit):
            # if the wanted commit is not on the top
            # we have to get full repo
            git.run('fetch --unshallow')
            if self.target_commit:
                git.checkout(self.target_commit)


    def system_requirements_from_conan_data(self, exclude=()):
        packages: typing.Dict[str, str] = {}
        packages, fallbacks = get_required_os_field(self.conan_data, 'system-packages')
        for _i in exclude:
            if _i in packages:
                packages.pop(_i)
            if _i in fallbacks:
                packages.pop(_i)
        self.output.warn('packages={}'.format(packages))
        if packages:
            installer = tools.SystemPackageTool(
                conanfile=self,
                default_mode='disabled' # export CONAN_SYSREQUIRES_SUDO='enabled' to allow actual installation
            )
            for libname, pkg in packages.items():
                if not libpkg_exists(libname, self.output):
                    if pkg:
                        installer.install(pkg, update=False)
                        if installer.installed(pkg):
                            self.output.success('installed {}'.format(pkg))
                        else:
                            self.output.error('fail to install {}'.format(pkg))
                        if libpkg_exists(libname, self.output):
                            continue
                    if libname in fallbacks:
                        conan_pkg = fallbacks[libname]
                        if conan_pkg:
                            self.output.warn('cannot find/install system lib {}, requires {}.'.format(libname, conan_pkg))
                            self.requires(conan_pkg)
                            continue
                    self.output.error('{} does not exist in system nor in conan.'.format(libname))


    def build_requirements_from_conan_data(self):
        required_cmds, fallbacks = get_required_os_field(self.conan_data, 'required-commands')
        if required_cmds:
            installer = tools.SystemPackageTool(
                conanfile=self,
                default_mode='disabled'  # export CONAN_SYSREQUIRES_SUDO='enabled' to allow actual installation
            )
            for cmd in required_cmds:
                if not tools.which(cmd):
                    sys_pkg = required_cmds[cmd]
                    if sys_pkg:
                        self.output.warn('install {} for cmd ``{}'.format(sys_pkg, cmd))
                        installer.install(sys_pkg)
                    if not sys_pkg or not installer.installed(sys_pkg):
                        if cmd in fallbacks:
                            self.output.warn('requires {} for cmd `{}`.'.format(fallbacks[cmd], cmd))
                            self.build_requires(fallbacks[cmd])
                        else:
                            self.output.error('cannot install/find {}'.format(cmd))


    def apply_patches(self):
        for filename in sorted(glob.glob("patches/*.diff")):
            self.output.info('applying patch "%s"' % filename)
            tools.patch(base_path=self._source_subfolder, patch_file=filename)


    def copy_pkg_config(self, name):
        root = self.deps_cpp_info[name].rootpath
        self.output.info('prefix in pc file will be replaced with %s'%root)
        pc_dir = os.path.join(root, 'lib', 'pkgconfig')
        pc_files = glob.glob('%s/*.pc' % pc_dir)
        if not pc_files:  # zlib store .pc in root
            pc_files = glob.glob('%s/*.pc' % root)
        for pc_name in pc_files:
            new_pc = os.path.basename(pc_name)
            self.output.warn('copy and modify .pc file %s' %pc_name)
            shutil.copy(pc_name, new_pc)
            prefix = root
            tools.replace_prefix_in_pc_file(new_pc, prefix)


    def collect_components_info_from_pc(self, pkgconf_dir):
        ''' Find all pc files and convert them to cpp_info.components. It uses PKG_CONFIG_$PACKAGE_$VARIABLE to define the prefix variable
        :param pkgconf_dir:
        :return:
        '''
        pkg_names = get_all_names_in_pkgconfig(pkgconf_dir)
        env_vars = self.create_pkgconfig_prefix_env(pkg_names)
        pkgconf_path = tools.get_env('PKG_CONFIG_PATH')
        if pkgconf_path:
            pkgconf_path = pkgconf_dir + ':' + pkgconf_path
        else:
            pkgconf_path = pkgconf_dir
        print('PKG_CONFIG_PATH=%s'%pkgconf_path)
        env_vars.update({'PKG_CONFIG_PATH': pkgconf_path})
        with tools.environment_append(env_vars):
            for pkg_name in pkg_names:
                _cflags, _includedirs, _libdirs, _libs = self.get_cpp_info_fields_from_pkg(pkg_name)
                self.cpp_info.components[pkg_name].names["cmake_find_package"] = pkg_name
                self.cpp_info.components[pkg_name].libdirs = _libdirs
                self.cpp_info.components[pkg_name].libs = _libs
                self.cpp_info.components[pkg_name].cflags = _cflags
                # TODO: split cflags to defines and pure cflags
                self.cpp_info.components[pkg_name].includedirs = _includedirs
                # self.cpp_info.components[pkg_name].requires = pkg.requires
                # the design of cpp_info_components
                # prevent any dependency outside conan
                # package from working.
                # It has to be a lib created in this package
                # or a lib in another conan pkg which need
                # to use conan_pkgname::lib to identify.
                # this is very clumsy when same libs can be
                # either from a system package or from current
                # build or from an another conan package
                # we should improve the components in conan
                # currently we can just ignore it, since there is
                # no components concept in generator at all.
                self.output.info("{} LIBRARIES: {}, requires: {}".format( pkg_name, self.cpp_info.components[pkg_name].libs, self.cpp_info.components[pkg_name].requires))
        # the component info is not really used in generators
        # so the best way is to use cmake side find_package on deployed pc file or cmake_paths's CMAKE_MODULE_PATH as XX_ROOT


    def collect_libs_info_from_pc(self, pkgconf_dir):
        ''' Find all pc files and convert them to cpp_info.components. It uses PKG_CONFIG_$PACKAGE_$VARIABLE to define the prefix variable
        :param pkgconf_dir:
        :return:
        '''
        pkg_names = get_all_names_in_pkgconfig(pkgconf_dir)
        env_vars = self.create_pkgconfig_prefix_env(pkg_names)

        pkgconf_path = tools.get_env('PKG_CONFIG_PATH')
        if pkgconf_path:
            pkgconf_path = pkgconf_dir + ':' + pkgconf_path
        else:
            pkgconf_path = pkgconf_dir
        print('PKG_CONFIG_PATH=%s'%pkgconf_path)
        env_vars.update({'PKG_CONFIG_PATH': pkgconf_path})

        libdirs = set()
        libs = set()
        cflags = set()
        includedirs = set()
        with tools.environment_append(env_vars):
            for pkg_name in pkg_names:
                _cflags, _includedirs, _libdirs, _libs = self.get_cpp_info_fields_from_pkg(pkg_name)
                libdirs.update(_libdirs)
                libs.update(_libs)
                cflags.update(_cflags)
                includedirs.update(_includedirs)

        # self.output.info('self.cpp_info.includedirs={}'.format(self.cpp_info.includedirs))
        # self.output.info('self.cpp_info.libdirs={}'.format(self.cpp_info.libdirs))
        # self.output.info('self.cpp_info.libs={}'.format(self.cpp_info.libs))
        self.cpp_info.libdirs = list(libdirs)
        self.cpp_info.libs = list(libs)
        self.cpp_info.cflags= list(cflags)
        self.cpp_info.includedirs = list(includedirs)
        self.output.info("INCLUDES: {}; LIBRARIES: {} {}; DEFINES={}".format(self.cpp_info.includedirs, self.cpp_info.libdirs, self.cpp_info.libs, self.cpp_info.cflags))
        # the orc-0.4 has bug, the libdir and include dir does not composite with $prefix
        # need to fix with pkgconfig module
        # https://gitlab.freedesktop.org/gstreamer/orc/-/blob/master/meson.build

    def get_cpp_info_fields_from_pkg(self, pkg_name):
        pkg = tools.PkgConfig(pkg_name)
        _libdirs = [_i[2:] for _i in pkg.libs_only_L]
        _libs = [_i[2:] for _i in pkg.libs_only_l]
        _cflags = pkg.cflags_only_other
        # TODO: split cflags to defines and pure cflags
        _includedirs = [_i[2:] for _i in pkg.cflags_only_I]
        if MyPkgConfig(None).is_pkgconf():
            self.output.warn(
                'FIXME: replace prefix (`{}`) with current package folder.'.format(pkg.variables['prefix']))
            # TODO: fix prefix here for pkgconf
        return _cflags, _includedirs, _libdirs, _libs

    def create_pkgconfig_prefix_env(self, pkg_names):
        prefix_vars = dict()
        if MyPkgConfig(None).is_pkgconf():
            self.output.warn('pkg-config is provided by pkgconf. It does not support PKG_CONFIG_$PKGNAME_$VARIABLE')
        for pkg_name in pkg_names:
            pkg_var_name = re.sub('[^a-zA-Z0-9]', '_', pkg_name)
            pkg_prefix_var = 'PKG_CONFIG_{}_PREFIX'.format(pkg_var_name.upper())
            self.output.info(
                '{}={}'.format(pkg_prefix_var, self.package_folder)
            )
            prefix_vars[pkg_prefix_var] = self.package_folder
        return prefix_vars

    def fix_pkgconfig_prefix(self, itemlist: typing.List[str], oldprefix: str):
        pat = re.compile(oldprefix)
        ret = []
        for item in itemlist:
            ret.append(pat.sub(self.package_folder, item))
        return ret