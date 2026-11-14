"""文件类工具：看目录、读文件、写文件。"""

from .base import WORKROOT, ToolError, clip, resolve


def list_dir(path="."):
    target = resolve(path)
    if not target.is_dir():
        raise ToolError(f"{path} 不是目录")
    lines = []
    for item in sorted(target.iterdir()):
        kind = "DIR " if item.is_dir() else "FILE"
        size = "" if item.is_dir() else f" {item.stat().st_size}B"
        lines.append(f"{kind} {item.name}{size}")
    return "\n".join(lines) or "（空目录）"


def read_file(path, offset=1, limit=200):
    target = resolve(path)
    if not target.is_file():
        raise ToolError(f"{path} 不是文件")
    text = target.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, int(offset))
    chunk = text[start - 1:start - 1 + int(limit)]
    body = "\n".join(f"{i:5d}| {line}" for i, line in enumerate(chunk, start))
    return clip(f"{target.name}（共 {len(text)} 行，当前 {start}-{start + len(chunk) - 1}）\n{body}")


def write_file(path, content):
    target = resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"已写入 {target.relative_to(WORKROOT)}（{len(content)} 字符）"
