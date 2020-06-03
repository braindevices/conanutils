# -*- coding: UTF-8 -*-
import subprocess
import typing

from conans.client.output import ScopedOutput
from conans.errors import ConanException
from conans.util.runners import check_output_runner
from conans.model.version import Version
from conans.client.graph import range_resolver
import re
import logging
default_logger = logging.getLogger(__name__)
def check_cmd_version(
    cmd_name: str,
    ver_range_expr: str,
    ver_opts: typing.List[str] = ('--version',),
    ver_output_pattern: str = r'.*?([0-9][.0-9a-zA-Z-_]+)',
    log_output: typing.Union[ScopedOutput, logging.Logger] = default_logger
) -> bool:
    cmd = [
        cmd_name,
    ]
    cmd.extend(ver_opts)
    output = check_output_runner(cmd)
    if output:
        output = output.strip()
        match = re.match(ver_output_pattern, output)
        if match:
            results = []
            ver_str = match.group(1)
            log_output.info('{} version = {}'.format(cmd_name, ver_str))
            ver_satisfied = range_resolver.satisfying([ver_str,], ver_range_expr, results)
            for result in results:
                log_output.info(result)
            if ver_satisfied:
                return True
            else:
                log_output.info('{} version does not meet requirement {}'.format(cmd_name, ver_range_expr))
        else:
            msg = 'WARNING: output from {} is {}, which does not match version pattern `{}`'.format(' '.join(cmd), output, ver_output_pattern.pattern)
            log_output.warn(msg)
    else:
        log_output.warn('WARNING: no output from command {}'.format(' '.join(cmd)))
    return False