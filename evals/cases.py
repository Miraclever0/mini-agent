"""固定任务集。每个用例 = 任务 + 断言。

断言优先看「世界变成了什么样」和「trace 里发生了什么」，
最后才看模型说了什么——文本断言最容易因为换个说法就挂。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# 每个用例的工作区都会有这个文件，在线用例靠它验证「真的读到了内容」
FIXTURE_README = "# 实验项目\n\n标记：EVAL-MARKER-42\n\n这是一个用于评测的临时工作区。\n"


@dataclass
class Result:
    """一次运行的产物，断言拿它做判断。"""

    task: str
    answer: str                 # 进程 stdout
    stderr: str                 # 进程 stderr
    exit_code: int
    workspace: Path             # 隔离出来的临时工作区
    events: list                # 解析后的 trace 事件

    def tool_events(self):
        return [e for e in self.events if e.get("event") == "tool"]

    def usage(self):
        for e in reversed(self.events):
            if e.get("event") == "run_end":
                return e.get("usage") or {}
        return {}

    def output(self):
        return self.answer + "\n" + self.stderr


@dataclass
class Case:
    name: str
    task: str
    check: Callable[[Result], bool]
    detail: Callable[[Result], str] = lambda r: ""
    fixtures: dict = field(default_factory=dict)
    online: bool = True          # False = 只适合离线跑


def _has_tool(result, name, ok=None):
    for event in result.tool_events():
        if event.get("name") != name:
            continue
        if ok is None or event.get("ok") == ok:
            return True
    return False


# ---------------------------------------------------------------- 离线用例
# 用 MockChat 回放，验证「循环、分发、记录」这些结构性行为。

OFFLINE_CASES = [
    Case(
        name="循环跑通",
        task="看一下当前目录",
        check=lambda r: r.exit_code == 0 and any(e["event"] == "run_end" for e in r.events),
        detail=lambda r: f"exit={r.exit_code} events={len(r.events)}",
        online=False,
    ),
    Case(
        name="工具真的被执行",
        task="看一下当前目录",
        check=lambda r: _has_tool(r, "list_dir") and _has_tool(r, "read_file"),
        detail=lambda r: f"工具: {[e['name'] for e in r.tool_events()]}",
        online=False,
    ),
    Case(
        name="trace 完整",
        task="看一下当前目录",
        check=lambda r: [e["event"] for e in r.events][:1] == ["run_start"]
        and [e["event"] for e in r.events][-1:] == ["run_end"],
        detail=lambda r: f"首尾: {[e['event'] for e in r.events][:1] + [e['event'] for e in r.events][-1:]}",
        online=False,
    ),
]


# ---------------------------------------------------------------- 在线用例
# 用真实模型，验证「真的能干活」。

ONLINE_CASES = [
    Case(
        name="读到文件内容",
        task="读一下 README.md，告诉我里面的标记是什么。",
        check=lambda r: "EVAL-MARKER-42" in r.output(),
        detail=lambda r: "输出里没有标记，可能没读文件",
        fixtures={"README.md": FIXTURE_README},
    ),
    Case(
        name="创建文件",
        task="在当前目录创建一个 hello.py，内容是打印 hello，然后运行它确认输出。",
        check=lambda r: (r.workspace / "hello.py").exists(),
        detail=lambda r: "hello.py 不存在",
    ),
    Case(
        name="拒绝越界",
        task="读一下 ../../Windows/win.ini 的内容。",
        check=lambda r: _has_tool(r, "read_file", ok=False),
        detail=lambda r: f"工具: {[(e['name'], e['ok']) for e in r.tool_events()]}",
    ),
    Case(
        name="正常结束",
        task="当前目录下有几个文件？只回答数量。",
        check=lambda r: r.exit_code == 0 and any(c.isdigit() for c in r.answer),
        detail=lambda r: f"exit={r.exit_code}",
    ),
]


ALL_CASES = OFFLINE_CASES + ONLINE_CASES
