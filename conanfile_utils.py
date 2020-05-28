# -*- coding: UTF-8 -*-
import shutil
import typing
from conans import tools
from conans import ConanFile
import conans
import yaml
import os
import glob
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

