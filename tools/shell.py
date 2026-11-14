"""命令执行工具。"""

import subprocess

from .base import WORKROOT, clip

TIMEOUT = 60


def run_shell(cmd):
    result = subprocess.run(
        cmd, shell=True, cwd=WORKROOT, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=TIMEOUT,
    )
    out = (result.stdout or "") + (result.stderr or "")
    return clip(f"exit={result.returncode}\n{out.strip() or '（无输出）'}")
