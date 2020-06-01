# -*- coding: UTF-8 -*-
import re
import sys

from conans import tools
import subprocess
import conans
import os

class MyPkgConfig(tools.PkgConfig):

    def __init__(self, *args, **kwargs):
        super(MyPkgConfig, self).__init__(*args, **kwargs)
        self._is_pkgconf = self._check_is_pkgconf()
        self.arg_list_all= '--list-package-names' if self._check_is_pkgconf() else '--list-all'


    def _check_is_pkgconf(self):
        command = [
            self.pkg_config_executable,
            '--about'
        ]
        try:
            if self._cmd_output(command):
                return True
        except subprocess.CalledProcessError as e:
            return False


    def is_pkgconf(self):
        return self._is_pkgconf



    def version(self):
        command = [
            self.pkg_config_executable,
            '--version'
        ]
        try:
            return self._cmd_output(command).strip()
        except subprocess.CalledProcessError as e:
            raise conans.errors.ConanException('pkg-config command %s failed with error: %s' % (command, e))


    def all_pkgs(self, only_in_dir=None):
        _env = dict()
        if only_in_dir:
            _env['PKG_CONFIG_LIBDIR'] = only_in_dir
            if 'PKG_CONFIG_PATH' in _env:
                _env.pop('PKG_CONFIG_PATH')
        print(_env)
        with tools.environment_append(_env):
            command = [
                self.pkg_config_executable,
                self.arg_list_all
            ]
            try:
                if self._is_pkgconf:
                    return self._cmd_output(command).split(os.linesep)
                else:
                    names = []
                    for _line in self._cmd_output(command).split(os.linesep):
                        names.append(_line.split(' ', 1)[0])
                    return names
            except subprocess.CalledProcessError as e:
                raise conans.errors.ConanException('pkg-config command %s failed with error: %s' % (command, e))


def get_all_pkg_names(lib_folder):
    pkgdir = os.path.join(lib_folder, 'pkgconfig')
    get_all_names_in_pkgconfig(pkgdir)


def get_all_names_in_pkgconfig(pkgconfig_folder):
    print('look pc file in %s' % pkgconfig_folder)
    return MyPkgConfig('').all_pkgs(only_in_dir=pkgconfig_folder)


def get_default_pc_path():
    vars = tools.PkgConfig('pkg-config').variables
    print('vars={}'.format(vars))
    pc_path_str = vars['pc_path']
    if (pc_path_str):
        return pc_path_str.split(':')
    return []

def get_default_lib_path():
    if tools.os_info.is_linux:
        ld_output = subprocess.check_output('ld --verbose | grep SEARCH_DIR', shell=True)
        if ld_output:
            return re.findall(r'SEARCH_DIR\("=([^()]+)"\);', ld_output.decode())
        else:
            return []
    elif tools.os_info.is_macos:
        # TODO: return default lib search path for MacOS
        print('FIXME: create get_default_lib_path() for MacOS', file=sys.stderr)
        return []
    else:
        raise conans.errors.ConanException('does not support get_default_lib_path() in current OS')