# -*- coding: UTF-8 -*-

from conans import tools
import subprocess
import conans
import os

class MyPkgConfig(tools.PkgConfig):

    def __init__(self, *args, **kwargs):
        super(MyPkgConfig, self).__init__(*args, **kwargs)
        self.arg_list_all= '--list-package-names' if self.is_pkgconf() else '--list-all'
        self._is_pkgconf = self.is_pkgconf()


    def is_pkgconf(self):
        command = [
            self.pkg_config_executable,
            '--about'
        ]
        try:
            if self._cmd_output(command):
                return True
        except subprocess.CalledProcessError as e:
            return False


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