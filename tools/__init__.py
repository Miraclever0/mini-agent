"""agent 能调用的工具：实现、声明、分发。

三层分开：
    base.py   公共设施（错误类型、路径约束、截断）
    files.py  文件类实现
    shell.py  命令类实现
    本文件    工具声明（给模型看的 schema）+ 名字到实现的映射 + 分发

加新工具时只需要：写实现 → 加进 TOOL_IMPL → 加一条 TOOLS 声明。
"""

from .base import ToolError, clip, resolve
from .files import list_dir, read_file, write_file
from .shell import run_shell

__all__ = ["TOOLS", "TOOL_IMPL", "execute", "ToolError", "clip", "resolve"]

TOOL_IMPL = {
    "list_dir": list_dir,
    "read_file": read_file,
    "write_file": write_file,
    "run_shell": run_shell,
}


def execute(name, args):
    """执行一个工具调用，返回 (ok, 文本)。失败不抛异常，把错误交回给模型。"""
    fn = TOOL_IMPL.get(name)
    if fn is None:
        return False, f"错误：不存在的工具 {name}。可用：{', '.join(TOOL_IMPL)}"
    try:
        return True, str(fn(**args))
    except ToolError as e:
        return False, f"错误：{e}"
    except TypeError as e:
        return False, f"错误：参数不对（{e}）。请对照工具定义检查参数名和类型。"
    except Exception as e:  # 工具失败不崩，把错误回传给模型让它自己改
        return False, f"错误：{type(e).__name__}: {e}"


# ------------------------------------------------------------------ 工具声明
# 这份 JSON 就是给模型看的「接口文档」：名字 + 自然语言描述 + JSON Schema 参数。
# 描述决定模型选不选、填不填得对，比参数名重要得多。

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "列出目录下的文件和子目录。需要先了解项目结构时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "相对路径，默认当前目录 '.'"}
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取文本文件，返回带行号的内容。修改文件前必须先调用它。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "offset": {"type": "integer", "description": "起始行，默认 1"},
                    "limit": {"type": "integer", "description": "最多读多少行，默认 200"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "把完整内容写入文件（覆盖），父目录不存在会自动创建。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "文件路径"},
                    "content": {"type": "string", "description": "要写入的完整文本"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "在工作目录执行一条 shell 命令并返回输出。用于跑测试、查环境。",
            "parameters": {
                "type": "object",
                "properties": {
                    "cmd": {"type": "string", "description": "要执行的命令，单条"}
                },
                "required": ["cmd"],
            },
        },
    },
]
