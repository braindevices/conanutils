# -*- coding: UTF-8 -*-
import shutil
import typing
from typing import Dict, Union, NamedTuple, List, Tuple, Iterable
from conans import tools
from conans import ConanFile
import conans
import yaml
import os
import glob

from .file_utils import replace_regex_in_file
from .pkg_conf_utils import get_all_pkg_names, get_all_names_in_pkgconfig, MyPkgConfig, get_default_pc_path, \
    get_default_lib_path
from conans.model.version import Version
from .command_utils import check_cmd_version
import re
VERSION_REGEX = re.compile(r'([0-9.]+)-(.+)-([a-z0-9]+)')

def parse_version(version: str):
    matches = VERSION_REGEX.match(version)
    if matches:
        return matches.groups()
    raise RuntimeError('% does not match version pattern: %s'%version%VERSION_REGEX.pattern)


def libpkg_exists(
        libname: str, scope_output,
        ver_range: Union[Tuple[str], Tuple[str, str]] = ()
):
    pkgconf = tools.PkgConfig(libname)
    try:
        _modversion = Version(pkgconf._get_option('modversion')[0])
        pkgconf_vars = pkgconf.variables
        scope_output.info('{} {} exists'.format(libname, _modversion))
        if ver_range:
            min_ver = Version(ver_range[0])
            max_ver = Version(ver_range[1]) if len(ver_range) == 2 else None
            if _modversion < min_ver or (max_ver is not None and _modversion > max_ver):
                scope_output.info('{} version {} is not in {}'.format(libname, _modversion, ver_range))
                return False
        return True
    except conans.errors.ConanException as e:
        scope_output.warn('{}'.format(e))
        return False

class sys_lib_requirement_t(NamedTuple):
    pkg: str
    version: Union[Tuple[str], Tuple[str, str]]

def get_required_os_field(conandata: Dict[str, typing.Any], field_name: str):
    data = conandata[field_name]
    ret: Dict[str, Dict] = {}
    if tools.os_info.linux_distro == "ubuntu":
        ret = data['ubuntu']
    elif tools.os_info.linux_distro == "fedora":
        ret = data['fedora']
    elif tools.os_info.linux_distro == "centos":
        ret = data['centos']
    elif tools.os_info.is_macos:
        ret = data['osx']
    else:
        tools.logger.warning('un-supported os: {}'.format(tools.os_info.linux_distro))
    return ret, data['fallback']


class AutoConanFile(ConanFile):
    exports_dir_path = os.path.realpath('./')
    os_packages = {}
    _source_subfolder = "source_subfolder"
    _build_subfolder = "build_subfolder"
    default_lib_paths = get_default_lib_path()
    #TODO: compatibility management is required when fallback to conan package
    #TODO: compatibility management is required when fallback to meson wrap

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
        packages: Dict[str, Dict] = {}
        packages, fallbacks = get_required_os_field(self.conan_data, 'system-packages')
        self.output.info('system_requirements_from_conan_data: exclude={}'.format(exclude))
        for _i in exclude:
            if _i in packages:
                packages.pop(_i)
            if _i in fallbacks:
                fallbacks.pop(_i)
        self.output.info('packages={}'.format(packages))
        if packages:
            installer = tools.SystemPackageTool(
                conanfile=self,
                default_mode='disabled' # export CONAN_SYSREQUIRES_SUDO='enabled' to allow actual installation
            )
            self.output.info('system_requirements_from_conan_data: packages={}'.format(packages))
            for libname, libinfo in packages.items():
                libreq = sys_lib_requirement_t(**libinfo)
                self.output.info('system_requirements_from_conan_data: check libname={}, pkgname={}, version={}'.format(libname, libreq.pkg, libreq.version))
                if not libpkg_exists(libname, self.output, libreq.version):
                    if libreq.pkg:
                        self.output.info(
                            'system_requirements_from_conan_data: try to isntall {} for {}'.format(libreq.pkg, libname))
                        installer.install(libreq.pkg, update=False)
                        if installer.installed(libreq.pkg):
                            self.output.success('installed {}'.format(libreq.pkg))
                        else:
                            self.output.info('fail to install {}'.format(libreq.pkg))

                        if libpkg_exists(libname, self.output, libreq.version):
                            continue
                        else:
                            self.output.warn('{} insalled, but version does not match {}.'.format(libreq.pkg, libreq.version))
                    if libname in fallbacks:
                        conan_pkg = fallbacks[libname]
                        if conan_pkg:
                            self.output.warn('cannot find/install system lib {}, requires conan package {}.'.format(libname, conan_pkg))
                            self.requires(conan_pkg)
                            continue
                    self.output.error('{} does not exist in system nor in conan.'.format(libname))


    def build_requirements_from_conan_data(self, exclude=()):
        required_cmds, fallbacks = get_required_os_field(self.conan_data, 'required-commands')
        required_cmd_vers = self.conan_data['required-command-versions']
        for _i in exclude:
            if _i in required_cmds:
                required_cmds.pop(_i)
            if _i in fallbacks:
                required_cmds.pop(_i)
        if required_cmds:
            installer = tools.SystemPackageTool(
                conanfile=self,
                default_mode='disabled'  # export CONAN_SYSREQUIRES_SUDO='enabled' to allow actual installation
            )
            for cmd in required_cmds:
                if tools.which(cmd):
                    if cmd in required_cmd_vers:
                        self.output.info(required_cmd_vers[cmd])
                        if check_cmd_version(cmd, log_output=self.output, **required_cmd_vers[cmd]):
                            self.output.info('{} version matched'.format(cmd))
                            continue
                    else:
                        self.output.info('has {} (any version is ok).'.format(cmd))
                        continue
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
                _cflags, _includedirs, _libdirs, _libs, _syslibs = self.get_cpp_info_fields_from_pkg(pkg_name)
                self.cpp_info.components[pkg_name].names["cmake_find_package"] = pkg_name
                self.cpp_info.components[pkg_name].libdirs = _libdirs
                self.cpp_info.components[pkg_name].libs = _libs
                self.cpp_info.components[pkg_name].cflags = _cflags
                # TODO: split cflags to defines and pure cflags
                self.cpp_info.components[pkg_name].includedirs = _includedirs
                self.cpp_info.components[pkg_name].system_libs = _syslibs
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


    def collect_libs_info_from_pc(self, pkgconf_dir:str, aux_pkgconf_dirs: Tuple[str]):
        ''' Find all pc files and convert them to cpp_info.components. It uses PKG_CONFIG_$PACKAGE_$VARIABLE to define the prefix variable
        :param pkgconf_dir:
        :return:
        '''
        print(pkgconf_dir)
        pkg_names = get_all_names_in_pkgconfig(pkgconf_dir)
        env_vars = self.create_pkgconfig_prefix_env(pkg_names)

        pkgconf_paths = []
        pkgconf_paths.append(pkgconf_dir)
        pkgconf_paths.extend(aux_pkgconf_dirs)
        #pkgconf_paths.append(self.build_folder) # some components might require pc from build dir
        if tools.get_env('PKG_CONFIG_PATH'):
            pkgconf_paths.append(tools.get_env('PKG_CONFIG_PATH'))
        pkgconf_path = ':'.join(pkgconf_paths)
        print('PKG_CONFIG_PATH=%s'%pkgconf_path)
        env_vars.update({'PKG_CONFIG_PATH': pkgconf_path})

        libdirs = set()
        libs = set()
        syslibs = set()
        cflags = set()
        includedirs = set()
        with tools.environment_append(env_vars):
            for pkg_name in pkg_names:
                _cflags, _includedirs, _libdirs, _libs, _syslibs = self.get_cpp_info_fields_from_pkg(pkg_name)
                libdirs.update(_libdirs)
                libs.update(_libs)
                syslibs.update(_syslibs)
                cflags.update(_cflags)
                includedirs.update(_includedirs)

        self.output.info('includedirs={}'.format(includedirs))
        self.output.info('libdirs={}'.format(libdirs))
        self.output.info('libs={}'.format(libs))
        self.output.info('system_libs={}'.format(syslibs))
        self.cpp_info.libdirs = list(libdirs)
        self.cpp_info.libs = list(libs)
        self.cpp_info.system_libs = list(syslibs)
        self.cpp_info.cflags= list(cflags)
        self.cpp_info.includedirs = list(includedirs)
        # self.output.info("INCLUDES: {}; LIBRARIES: {} {}; DEFINES={}".format(self.cpp_info.includedirs, self.cpp_info.libdirs, self.cpp_info.libs, self.cpp_info.cflags))
        # the orc-0.4 has bug, the libdir and include dir does not composite with $prefix
        # need to fix with pkgconfig module
        # https://gitlab.freedesktop.org/gstreamer/orc/-/blob/master/meson.build


    def get_cpp_info_fields_from_pkg(self, pkg_name):
        pkg = tools.PkgConfig(pkg_name)
        libdirs = []
        syslibs = []
        libs = []
        following_is_syslibs = False
        for _i in pkg.libs:
            if not _i.strip():
                continue
            if _i.startswith('-L'):
                conans.tools.logger.debug('required lib: {}; default_lib_paths: {}'.format(_i[2:], self.default_lib_paths))
                if _i[2:] in self.default_lib_paths:
                    self.output.info('found system libdir {}'.format(_i[2:]))
                    following_is_syslibs = True
                    continue
                else:
                    libdirs.append(_i[2:])
                    following_is_syslibs = False
                    continue
            elif _i.startswith('-l'):
                if following_is_syslibs:
                    syslibs.append(_i[2:])
                else:
                    libs.append(_i[2:])
            elif _i.startswith('-Wl'):
                self.output.info('ignore linker flags {}'.format(_i))
            else:
                raise conans.errors.ConanException('Does not support libs entries without "-L" or "-l"')


        if len(libdirs) > 1:
            #TODO: cpp_info is still clumsy here, the -L and -l order actually mattered. the components is come into rescue but it still have some issue in the way they designed it.
            self.output.warn('FIXME: multiple libdirs={}. libs in one of the dir can hide the libs in another dir. Use components instead. If components is already in use, it might require split this project into sub-packages.'.format(libdirs))
        cflags = pkg.cflags_only_other
        # TODO: split cflags to defines and pure cflags
        includedirs = [_i[2:] for _i in pkg.cflags_only_I]
        if MyPkgConfig(None).is_pkgconf():
            _prefix = re.compile(pkg.variables['prefix'])
            conans.tools.logger.debug(
                'replace prefix (`{}`) with current package folder.'.format(_prefix.pattern))
            libdirs = self.fix_pkgconfig_prefix(libdirs, _prefix)
            libs = self.fix_pkgconfig_prefix(libs, _prefix)
            cflags = self.fix_pkgconfig_prefix(cflags, _prefix)
            includedirs = self.fix_pkgconfig_prefix(includedirs, _prefix)
        return cflags, includedirs, libdirs, libs, syslibs


    def create_pkgconfig_prefix_env(self, pkg_names):
        prefix_vars = dict()
        if MyPkgConfig(None).is_pkgconf():
            self.output.warn('pkg-config is provided by pkgconf. It does not support PKG_CONFIG_$PKGNAME_$VARIABLE')
        for pkg_name in pkg_names:
            pkg_var_name = re.sub('[^a-zA-Z0-9]', '_', pkg_name)
            pkg_prefix_var = 'PKG_CONFIG_{}_PREFIX'.format(pkg_var_name.upper())
            conans.tools.logger.info(
                '{}={}'.format(pkg_prefix_var, self.package_folder)
            )
            prefix_vars[pkg_prefix_var] = self.package_folder
        return prefix_vars


    def fix_pkgconfig_prefix(self, itemlist: typing.List[str], oldprefix: typing.Pattern):
        ret = []
        for item in itemlist:
            ret.append(oldprefix.sub(self.package_folder, item))
        return ret


def replace_path_in_files(pattern: str, *args, **kwargs):
    for file_path in glob.glob(pattern, recursive=True):
        print(file_path)
        tools.replace_path_in_file(file_path, *args, **kwargs)


def replace_regex_in_files(pattern: str, *args, **kwargs):
    for file_path in glob.glob(pattern, recursive=True):
        print(file_path)
        replace_regex_in_file(file_path, *args, **kwargs)


def replace_path_in_pkgconfig(pc_file_root_dir, dependency_package_dir):
    dep_path_comps = dependency_package_dir.split(os.path.sep)
    pkg_name_version_channel = os.path.join(*dep_path_comps[-6:-2])
    print(pkg_name_version_channel)
    replace_regex_in_files(
        os.path.join(pc_file_root_dir, '**', '*.pc'),
        search=os.path.join('/.*', pkg_name_version_channel, 'package', '[0-9a-z]+'),
        replace=dependency_package_dir,
        strict=False
    )