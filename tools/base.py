"""工具层的公共设施：错误类型、路径约束、输出截断。

这个模块不 import 包内的其他模块，避免循环依赖。
"""

from pathlib import Path

from config_loader import MAX_OUTPUT, WORKROOT


class ToolError(Exception):
    """工具的可预期失败（文件不存在、路径越界……）。

    用异常而不是返回 "错误：..." 字符串，是为了让调用方能区分
    「工具执行失败」和「工具正常返回了一段内容」，trace 才能如实记录。
    """


def clip(text, limit=None):
    """截断过长的输出，避免一次读大文件把上下文撑爆。"""
    limit = MAX_OUTPUT if limit is None else limit
    text = "" if text is None else str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...（已截断，原文共 {len(text)} 字符）"


def resolve(p):
    """把相对路径解析到 WORKROOT 下，并阻止逃逸。"""
    path = Path(p)
    path = (WORKROOT / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_relative_to(WORKROOT):
        raise PermissionError(f"拒绝访问工作区外的路径: {p}")
    return path
