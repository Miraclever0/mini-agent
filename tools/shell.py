"""命令执行工具。"""

import locale
import subprocess

from .base import WORKROOT, clip

TIMEOUT = 60


def decode_output(raw):
    """子进程输出的编码不固定，得猜。

    - Linux / macOS：一般是 UTF-8
    - 中文 Windows：cmd 内建命令和 Python 子进程通常按 GBK(cp936) 输出
    - 控制台被设成 UTF-8（chcp 65001）时又是 UTF-8

    所以先按 UTF-8 严格解码，失败再退回本地编码，最后兜底替换。
    硬编码任何一种都会在另一类环境里出乱码。
    """
    if not raw:
        return ""
    candidates = ["utf-8", locale.getpreferredencoding(False), "gbk"]
    for encoding in candidates:
        try:
            return raw.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")


def run_shell(cmd):
    # 不用 text=True：需要拿到原始字节，才能自己决定怎么解码
    result = subprocess.run(
        cmd, shell=True, cwd=WORKROOT, capture_output=True, timeout=TIMEOUT,
    )
    out = decode_output(result.stdout or b"") + decode_output(result.stderr or b"")
    return clip(f"exit={result.returncode}\n{out.strip() or '（无输出）'}")
