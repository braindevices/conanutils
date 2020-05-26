# -*- coding: UTF-8 -*-

from conans import tools
import subprocess
import conans
import os

class MyPkgConfig(tools.PkgConfig):
    def all_pkgs(self, only_in_dir=None):
        _env = dict()
        if only_in_dir:
            _env['PKG_CONFIG_LIBDIR'] = only_in_dir
        print(_env)
        with tools.environment_append(_env):
            command = [self.pkg_config_executable, '--list-package-names']
            try:
                return self._cmd_output(command).split(os.linesep)
            except subprocess.CalledProcessError as e:
                raise conans.ConanException('pkg-config command %s failed with error: %s' % (command, e))

def get_all_pkg_names(lib_folder):
    pkgdir = os.path.join(lib_folder, 'pkgconfig')
    print('look pc file in %s' % pkgdir)
    return MyPkgConfig('').all_pkgs(only_in_dir=pkgdir)