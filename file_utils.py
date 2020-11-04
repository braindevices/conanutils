# -*- coding: UTF-8 -*-
from conans.client.tools.files import _manage_text_not_found
from conans.util.fallbacks import default_output
from conans.util.files import (_generic_algorithm_sum, load, save)
import re

def replace_regex_in_file(file_path, search, replace, flags=0, strict=True, output=None, encoding=None, warning=False):
    output = default_output(output, 'replace_regex_in_file')

    encoding_in = encoding or "auto"
    encoding_out = encoding or "utf-8"
    content = load(file_path, encoding=encoding_in)
    #print(content)
    content, nb = re.subn(search, replace, content, flags=flags)
    if nb == 0:
        if strict or warning:
            _manage_text_not_found(search, file_path, strict, 'replace_regex_in_file', output=output)
        #return

    content = content.encode(encoding_out)
    save(file_path, content, only_if_modified=False, encoding=encoding_out)