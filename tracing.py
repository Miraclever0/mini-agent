"""结构化 trace：每次运行写一个 JSONL 文件，附带一个查看器。

    python run.py "任务"        # 运行，同时写 traces/<时间>.jsonl
    python run.py --no-trace    # 不写
    python tracing.py           # 看最近一次
    python tracing.py traces/2026-11-14T17-05-12.jsonl

为什么用 JSONL 而不是日志文本：
    每行一条完整的事件，可以直接 grep、可以用 jq 过滤、
    也可以后续接自己的分析脚本。文本日志只能给人看。
"""

import json
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

# 输出被管道接走时统一用 UTF-8
for _stream in (sys.stdout, sys.stderr):
    if not _stream.isatty():
        _stream.reconfigure(encoding="utf-8", errors="replace")


class Trace:
    """一次运行的记录器。用法：trace.emit("tool", step=1, name="read_file", ...)"""

    def __init__(self, directory=None, console=True):
        self.dir = Path(directory) if directory else Path.cwd() / "traces"
        self.dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        self.path = self.dir / f"{stamp}.jsonl"
        self._file = self.path.open("w", encoding="utf-8")
        self.console = console

    def emit(self, event, **fields):
        record = {"ts": datetime.now().astimezone().isoformat(timespec="milliseconds"), "event": event}
        record.update(fields)
        self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._file.flush()          # 崩了也要留下已经发生的部分
        if self.console:
            _echo(record)

    def close(self):
        if not self._file.closed:
            self._file.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _echo(r):
    """把事件渲染成人和测试都能读的一行。"""
    kind = r.get("event")
    if kind == "run_start":
        print(f"任务：{r.get('task')}\n", file=sys.stderr)
    elif kind == "llm":
        u = r.get("usage") or {}
        print(
            f"[{r['step']}] 模型 {r['duration_ms']}ms"
            f"  in={u.get('prompt_tokens', '?')} out={u.get('completion_tokens', '?')}",
            file=sys.stderr,
        )
    elif kind == "tool":
        mark = "" if r.get("ok", True) else "  ✗"
        print(f"[{r['step']}] {r['name']} {r['duration_ms']}ms {r['chars']}B{mark}", file=sys.stderr)
        preview = (r.get("preview") or "").replace("\n", " ")
        if preview:
            print(f"     -> {preview}", file=sys.stderr)


def load(path):
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _w(text):
    """终端显示宽度：中文算两格。"""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in str(text))


def _pad(text, width):
    return str(text) + " " * max(0, width - _w(text))


def _padl(text, width):
    return " " * max(0, width - _w(text)) + str(text)


def render(records, out=sys.stdout):
    """把一个 trace 渲染成表。返回汇总 dict，方便测试。"""
    start = next((r for r in records if r["event"] == "run_start"), {})
    end = next((r for r in records if r["event"] == "run_end"), {})

    print(f"任务  {start.get('task', '?')}", file=out)
    print(f"模型  {start.get('model', '?')}   步数上限 {start.get('max_steps', '?')}", file=out)
    print("", file=out)

    header = (" 步  " + _pad("类型", 6) + _padl("耗时", 8) + "  "
              + _pad("内容", 36) + _padl("上下文", 8))
    print(header, file=out)
    print(" " + "-" * (_w(header) - 1), file=out)

    for r in records:
        if r["event"] == "llm":
            usage = r.get("usage") or {}
            n = r.get("tool_calls") or 0
            action = f"决定调用 {n} 个工具" if n else "结束"
            context = usage.get("prompt_tokens", "-")
            print(f" {r['step']:>2}  " + _pad("思考", 6) + _padl(f"{r['duration_ms']}ms", 8) + "  "
                  + _pad(action, 36) + _padl(context, 8), file=out)
        elif r["event"] == "tool":
            mark = "" if r.get("ok", True) else "  ✗ 失败"
            print(f" {r['step']:>2}  " + _pad("执行", 6) + _padl(f"{r['duration_ms']}ms", 8) + "  "
                  + _pad(f"{r['name']}{mark} → {r['chars']}B", 36) + _padl("-", 8), file=out)

    print("", file=out)
    usage = end.get("usage") or {}
    print(f"结束  {end.get('steps', '?')} 步  {end.get('duration_ms', '?')}ms", file=out)
    print(f"用量  上下文峰值 {end.get('peak_context', '?')}   "
          f"累计输入 {usage.get('prompt_tokens', '?')} / 输出 {usage.get('completion_tokens', '?')}", file=out)

    answer = end.get("answer")
    if answer:
        print(f"\n回答  {answer}", file=out)

    return {
        "steps": end.get("steps"),
        "duration_ms": end.get("duration_ms"),
        "peak_context": end.get("peak_context"),
        "usage": usage,
        "answer": answer,
    }


def latest(directory=None):
    d = Path(directory) if directory else Path.cwd() / "traces"
    files = sorted(d.glob("*.jsonl"))
    return files[-1] if files else None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        path = Path(argv[0])
    else:
        path = latest()
        if not path:
            sys.exit("traces/ 里还没有记录。先跑一次 python run.py")
    if not path.exists():
        sys.exit(f"找不到 trace：{path}")

    records = load(path)
    print(f"trace  {path}\n")
    render(records)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
