"""最小 agent：一个 while 循环 + 4 个工具。零依赖，只用标准库。

用法:
    python agent.py                     # 跑默认任务
    python agent.py "把 tests 里失败的用例找出来"   # 跑指定任务
    python agent.py --mock              # 不联网，用假模型走一遍完整循环

改这一行就能跑：API_KEY
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------- 配置

# 输出被管道接走时统一用 UTF-8，避免 Windows 下按 GBK 编码导致乱码
for _stream in (sys.stdout, sys.stderr):
    if not _stream.isatty():
        _stream.reconfigure(encoding="utf-8", errors="replace")

API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-00000000000000000000000000000000")  # ← 换成你的 Key
BASE_URL = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-chat"
MAX_STEPS = 12          # 步数上限：模型不会自己停，你得给它一个死线
MAX_OUTPUT = 4000       # 单次工具输出上限：防止一个文件把上下文撑爆
WORKROOT = Path.cwd().resolve()   # 工具只能碰这个目录以内的东西

SYSTEM_PROMPT = """你是一个能操作本机文件的助手。

规则：
- 需要了解现状时先调用工具查看，不要凭猜测回答。
- 修改文件前先读原文件。
- 任务完成后，直接给出简洁的结论，不要再调用工具。
"""


# ---------------------------------------------------------------- 工具实现

def _clip(text, limit=MAX_OUTPUT):
    text = "" if text is None else str(text)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n...（已截断，原文共 {len(text)} 字符）"


def _resolve(p):
    """把相对路径解析到 WORKROOT 下，并阻止逃逸。"""
    path = Path(p)
    path = (WORKROOT / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_relative_to(WORKROOT):
        raise PermissionError(f"拒绝访问工作区外的路径: {p}")
    return path


def list_dir(path="."):
    target = _resolve(path)
    if not target.is_dir():
        return f"错误：{path} 不是目录"
    lines = []
    for item in sorted(target.iterdir()):
        kind = "DIR " if item.is_dir() else "FILE"
        size = "" if item.is_dir() else f" {item.stat().st_size}B"
        lines.append(f"{kind} {item.name}{size}")
    return "\n".join(lines) or "（空目录）"


def read_file(path, offset=1, limit=200):
    target = _resolve(path)
    if not target.is_file():
        return f"错误：{path} 不是文件"
    text = target.read_text(encoding="utf-8", errors="replace").splitlines()
    start = max(1, int(offset))
    chunk = text[start - 1:start - 1 + int(limit)]
    body = "\n".join(f"{i:5d}| {line}" for i, line in enumerate(chunk, start))
    return _clip(f"{target.name}（共 {len(text)} 行，当前 {start}-{start + len(chunk) - 1}）\n{body}")


def write_file(path, content):
    target = _resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"已写入 {target.relative_to(WORKROOT)}（{len(content)} 字符）"


def run_shell(cmd):
    result = subprocess.run(
        cmd, shell=True, cwd=WORKROOT, capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=60,
    )
    out = (result.stdout or "") + (result.stderr or "")
    return _clip(f"exit={result.returncode}\n{out.strip() or '（无输出）'}")


TOOL_IMPL = {
    "list_dir": list_dir,
    "read_file": read_file,
    "write_file": write_file,
    "run_shell": run_shell,
}


# ---------------------------------------------------------------- 工具声明
# 这份 JSON 就是前面聊的「线上格式」：名字 + 自然语言描述 + JSON Schema 参数

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


# ---------------------------------------------------------------- 调模型

def chat(messages, tools=TOOLS, retries=3):
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": tools,
        "temperature": 0,
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}",
    }
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(BASE_URL, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            return body["choices"][0]["message"]
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:500]
            if e.code in (429, 500, 502, 503) and attempt < retries:
                time.sleep(2 * attempt)
                continue
            raise RuntimeError(f"HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            if attempt < retries:
                time.sleep(2 * attempt)
                continue
            raise RuntimeError(f"网络错误: {e.reason}") from e


# ---------------------------------------------------------------- 执行 + 主循环

def execute(name, args):
    fn = TOOL_IMPL.get(name)
    if fn is None:
        return f"错误：不存在的工具 {name}。可用：{', '.join(TOOL_IMPL)}"
    try:
        return fn(**args)
    except TypeError as e:
        return f"错误：参数不对（{e}）。请对照工具定义检查参数名和类型。"
    except Exception as e:  # 工具失败不崩，把错误回传给模型让它自己改
        return f"错误：{type(e).__name__}: {e}"


def run(task, chat_fn=chat):
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]

    for step in range(1, MAX_STEPS + 1):
        msg = chat_fn(messages, TOOLS)
        msg.setdefault("content", msg.get("content") or "")
        messages.append(msg)

        calls = msg.get("tool_calls") or []
        if not calls:                      # 不调工具 = 它认为任务结束
            return msg.get("content") or "（模型没有给出内容）"

        for call in calls:                 # 模型只是提了个建议，执行权在这里
            name = call["function"]["name"]
            raw = call["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw)
            except json.JSONDecodeError:
                result = f"错误：arguments 不是合法 JSON：{raw[:200]}"
            else:
                result = execute(name, args)

            print(f"[{step}] {name} {raw}", file=sys.stderr)
            print(f"     -> {_clip(result, 160)}", file=sys.stderr)
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": result,
            })

    return f"达到步数上限 {MAX_STEPS}，任务未收敛。"


# ---------------------------------------------------------------- mock 模型

MOCK_SCRIPT = [
    ("list_dir", {"path": "."}),
    ("read_file", {"path": "README.md"}),
    (None, None),
]


class MockChat:
    """假模型：按脚本回放工具调用，用来验证循环本身是否正常。"""

    def __init__(self):
        self.i = 0

    def __call__(self, messages, tools):
        name, args = MOCK_SCRIPT[min(self.i, len(MOCK_SCRIPT) - 1)]
        self.i += 1
        if name is None:
            return {"role": "assistant", "content": "（mock）已看完目录和 README，循环正常。"}
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": f"call_{self.i}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
            }],
        }


# ---------------------------------------------------------------- 入口

DEFAULT_TASK = "看一下当前目录里有什么，读一下 README.md，用三句话总结这个项目。"

if __name__ == "__main__":
    argv = [a for a in sys.argv[1:]]
    mock = "--mock" in argv
    argv = [a for a in argv if a != "--mock"]
    task = " ".join(argv) or DEFAULT_TASK

    if not mock and not API_KEY.startswith("sk-"):
        sys.exit("请先把 agent.py 里的 API_KEY 换成你的 DeepSeek Key。")

    print(f"任务：{task}\n", file=sys.stderr)
    answer = run(task, MockChat() if mock else chat)
    print("\n" + answer)
