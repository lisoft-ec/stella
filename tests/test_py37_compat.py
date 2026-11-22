"""The board runs Python 3.7: make sure no newer syntax or stdlib API slips in."""
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _vermin():
    exe = shutil.which("vermin", path=os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", ""))
    if exe is None:
        pytest.skip("vermin no está instalado")
    return exe


def test_package_is_python37_compatible():
    result = subprocess.run(
        [_vermin(), "-t=3.7-", "--no-tips", "--violations", "--eval-annotations",
         "--backport", "dataclasses", os.path.join(ROOT, "stella")],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True,
    )
    assert result.returncode == 0, result.stdout
