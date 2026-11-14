"""最小 agent：一个 while 循环。零依赖，只用标准库。跨平台。

这个文件只负责两件事：**调模型**和**跑循环**。

    配置加载  config_loader.py
    工具实现  tools/
    观测记录  tracing.py
    入口      run.py

import 时没有副作用，适合在调试器里单步跟进 run()。
"""

import json
import sys
import time
import urllib.error
import urllib.request

from config_loader import (
    API_KEY,
    BASE_URL,
    CONFIG_FILE,
    KEY_PLACEHOLDER,
    MAX_STEPS,
    MODEL,
    TEMPERATURE,
)
from tools import TOOLS, clip, execute
from tracing import Trace

# 输出被管道接走时统一用 UTF-8，避免 Windows 下按 GBK 编码导致乱码
for _stream in (sys.stdout, sys.stderr):
    if not _stream.isatty():
        _stream.reconfigure(encoding="utf-8", errors="replace")

SYSTEM_PROMPT = """你是一个能操作本机文件的助手。

规则：
- 需要了解现状时先调用工具查看，不要凭猜测回答。
- 修改文件前先读原文件。
- 任务完成后，直接给出简洁的结论，不要再调用工具。
"""


# ---------------------------------------------------------------- 调模型

def chat(messages, tools=TOOLS, retries=3):
    """调一次模型，返回 (message, usage)。usage 可能是 None（某些代理不透传）。"""
    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": tools,
        "temperature": TEMPERATURE,
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
            return body["choices"][0]["message"], body.get("usage")
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


# ---------------------------------------------------------------- 主循环

def run(task, chat_fn=chat, trace=None):
    """跑一轮任务。trace 可以是 tracing.Trace，也可以是 None（不记录）。"""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]
    started = time.perf_counter()
    totals = {"prompt_tokens": 0, "completion_tokens": 0}
    peak_context = 0

    for step in range(1, MAX_STEPS + 1):
        t0 = time.perf_counter()
        msg, usage = chat_fn(messages, TOOLS)
        took = round((time.perf_counter() - t0) * 1000)

        if usage:                          # 累计账单用量，同时记录上下文峰值
            for key in totals:
                totals[key] += usage.get(key) or 0
            peak_context = max(peak_context, usage.get("prompt_tokens") or 0)

        msg.setdefault("content", msg.get("content") or "")
        messages.append(msg)

        calls = msg.get("tool_calls") or []
        if trace:
            trace.emit("llm", step=step, duration_ms=took, usage=usage, tool_calls=len(calls))

        if not calls:                      # 不调工具 = 它认为任务结束
            answer = msg.get("content") or "（模型没有给出内容）"
            if trace:
                trace.emit("run_end", steps=step, duration_ms=round((time.perf_counter() - started) * 1000),
                           usage=totals, peak_context=peak_context, answer=answer)
            return answer

        for call in calls:                 # 模型只是提了个建议，执行权在这里
            name = call["function"]["name"]
            raw = call["function"].get("arguments") or "{}"
            t1 = time.perf_counter()
            try:
                args = json.loads(raw)
            except json.JSONDecodeError:
                ok, result = False, f"错误：arguments 不是合法 JSON：{raw[:200]}"
            else:
                ok, result = execute(name, args)

            if trace:
                trace.emit("tool", step=step, name=name, args=args,
                           duration_ms=round((time.perf_counter() - t1) * 1000),
                           ok=ok, chars=len(result), preview=clip(result, 200))
            messages.append({
                "role": "tool",
                "tool_call_id": call["id"],
                "content": result,
            })

    answer = f"达到步数上限 {MAX_STEPS}，任务未收敛。"
    if trace:
        trace.emit("run_end", steps=MAX_STEPS, duration_ms=round((time.perf_counter() - started) * 1000),
                   usage=totals, peak_context=peak_context, answer=answer)
    return answer


# ---------------------------------------------------------------- mock 模型

MOCK_SCRIPT = [
    ("list_dir", {"path": "."}),
    ("read_file", {"path": "README.md"}),
    (None, None),
]


class MockChat:
    """假模型：按脚本回放工具调用，用来验证循环本身是否正常。

    顺带伪造 token 用量（按上下文字符数估算），这样 trace 查看器里
    也有东西可看，方便验证记录链路。
    """

    def __init__(self):
        self.i = 0

    def __call__(self, messages, tools):
        name, args = MOCK_SCRIPT[min(self.i, len(MOCK_SCRIPT) - 1)]
        self.i += 1
        usage = {
            "prompt_tokens": sum(len(json.dumps(m, ensure_ascii=False)) for m in messages) // 4,
            "completion_tokens": 20,
        }
        if name is None:
            return {"role": "assistant", "content": "（mock）已看完目录和 README，循环正常。"}, usage
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": f"call_{self.i}",
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
            }],
        }, usage


# ---------------------------------------------------------------- 入口

DEFAULT_TASK = "看一下当前目录里有什么，读一下 README.md，用三句话总结这个项目。"


def main(argv=None):
    """命令行入口。返回进程退出码，由 run.py 负责抛出。"""
    argv = list(sys.argv[1:] if argv is None else argv)
    mock = "--mock" in argv
    no_trace = "--no-trace" in argv
    flags = ("--mock", "--no-trace")
    task = " ".join(a for a in argv if a not in flags) or DEFAULT_TASK

    if not mock:
        if KEY_PLACEHOLDER in API_KEY or not API_KEY.startswith("sk-"):
            print(
                f"还没有可用的 Key（当前配置：{CONFIG_FILE}）。\n"
                f"  交互式运行会自动提示你粘贴；非交互环境请设置环境变量：\n"
                f"    setx DEEPSEEK_API_KEY \"sk-...\"     (Windows)\n"
                f"    export DEEPSEEK_API_KEY=sk-...     (bash)\n"
                f"  想先验证循环能跑：python run.py --mock",
                file=sys.stderr,
            )
            return 1

    trace = None
    if not no_trace:
        trace = Trace()
        trace.emit("run_start", task=task, model="mock" if mock else MODEL, max_steps=MAX_STEPS)

    try:
        answer = run(task, MockChat() if mock else chat, trace=trace)
    except RuntimeError as exc:          # 网络 / 鉴权问题，别甩一屏 traceback
        print(f"调用失败：{exc}", file=sys.stderr)
        return 1
    finally:
        if trace:
            trace.close()

    print("\n" + answer)
    if trace:
        print(f"\ntrace: {trace.path}", file=sys.stderr)
        print("查看: python tracing.py", file=sys.stderr)
    return 0


if __name__ == "__main__":
    # 这是库文件，不是入口。直接跑它只会得到一句提示，而不是静默什么都不做。
    sys.exit('这是库文件。入口是 run.py：python run.py "你的任务"')
