"""mini-agent 的唯一入口。

    python run.py                # 交互模式：保留上下文，可以连续追问
    python run.py "任务"          # 只跑一次，跑完退出
    python run.py --mock         # 用假模型，不联网、不花钱
    python run.py --no-trace     # 本次不写 trace

带任务参数就单次执行；不带参数就进交互模式。
第一次运行会自动生成 config.py 并提示粘贴 DeepSeek Key。
"""

import getpass
import os
import sys
from pathlib import Path

from tracing import Trace

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.py"
EXAMPLE_PATH = HERE / "config.example.py"

# 与 config_loader.KEY_PLACEHOLDER 保持一致。这里不 import config_loader，
# 因为它在 import 时就会读配置，必须等引导跑完。
PLACEHOLDER = "你的DeepSeekKey"

FLAGS = ("--mock", "--no-trace")

# 输出被管道接走时统一用 UTF-8；输入同理，否则中文会被按本地编码误解
for _stream in (sys.stdout, sys.stderr):
    if not _stream.isatty():
        _stream.reconfigure(encoding="utf-8", errors="replace")
if not sys.stdin.isatty():
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")

HELP = """命令：
  /context  查看当前上下文的规模
  /trace    显示最近一次的 trace 文件
  /reset    清空上下文，开始新对话
  /help     显示这份帮助
  /exit     退出

其余输入都当作任务交给 agent。
"""


def bootstrap(argv):
    """首次运行时生成 config.py，缺 Key 时问一次。已经配好就什么都不做。"""
    if "--mock" in argv:              # mock 不联网，不需要 Key
        return
    if not EXAMPLE_PATH.exists():     # 安装不完整，交给 agent 报错
        return
    # 环境变量提供了 Key：临时覆盖 / CI 用，完全不碰磁盘
    if (os.getenv("DEEPSEEK_API_KEY") or "").strip():
        return

    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(EXAMPLE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        print("首次运行：已从 config.example.py 生成 config.py", file=sys.stderr)

    text = CONFIG_PATH.read_text(encoding="utf-8")
    if PLACEHOLDER not in text:       # 已经有真 Key 了
        return

    if not sys.stdin.isatty():        # 非交互环境别卡住，交给 agent.main() 报错
        return

    print("\n需要 DeepSeek API Key（只配一次，写进 config.py，不会提交）", file=sys.stderr)
    print("  申请地址 https://platform.deepseek.com", file=sys.stderr)
    try:
        key = getpass.getpass("  粘贴 Key（输入不显示）: ").strip()
    except (EOFError, KeyboardInterrupt):
        sys.exit("\n已取消。")

    if not key:
        return
    if not key.startswith("sk-"):
        print("提醒：DeepSeek 的 Key 一般以 sk- 开头，确认一下没粘错", file=sys.stderr)

    # 逐行替换，保留原来的换行符（CRLF / LF 都能处理）
    out = []
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("API_KEY"):
            ending = line[len(line.rstrip("\r\n")):]
            out.append(f'API_KEY = "{key}"{ending}')
        else:
            out.append(line)
    CONFIG_PATH.write_text("".join(out), encoding="utf-8")
    print("已写入 config.py（.gitignore 已忽略，不会进仓库）\n", file=sys.stderr)


def chat_loop(agent, mock, use_trace):
    """交互模式：每轮把消息留在内存里，下一轮带着历史继续。"""
    chat_fn = agent.MockChat() if mock else agent.chat
    messages = agent.new_messages()
    last_trace = None
    last_summary = None

    print("mini-agent 交互模式" + ("（mock，假模型）" if mock else ""))
    print("/help 看命令，/exit 退出\n")

    while True:
        try:
            line = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        if line.startswith("/"):
            command = line.lower()
            if command in ("/exit", "/quit", "/q"):
                break
            if command == "/help":
                print(HELP)
            elif command == "/context":
                print(f"  消息 {len(messages)} 条", end="")
                if last_summary:
                    usage = last_summary.get("usage") or {}
                    print(f"，上次请求 {last_summary.get('peak_context', '?')} token"
                          f"（累计 in {usage.get('prompt_tokens', '?')} / out {usage.get('completion_tokens', '?')}）")
                else:
                    print("，还没跑过")
            elif command == "/trace":
                print(f"  {last_trace.path if last_trace else '还没有运行过'}")
            elif command == "/reset":
                messages = agent.new_messages()
                last_summary = None
                print("  上下文已清空")
            else:
                print(f"  不认识的命令：{line}（试试 /help）")
            continue

        trace = Trace() if use_trace else None
        last_trace = trace
        snapshot = len(messages)      # 中断时回滚到这一轮之前
        try:
            answer = agent.run(line, chat_fn, trace=trace, messages=messages)
        except KeyboardInterrupt:
            del messages[snapshot:]
            print("\n  已中断，本轮已丢弃\n")
            continue
        except Exception as exc:      # 网络 / 鉴权 / 工具异常都不该炸掉会话
            del messages[snapshot:]
            print(f"\n  出错：{exc}\n")
            continue
        finally:
            if trace:
                trace.close()

        last_summary = trace.summary if trace else None

        print()
        print(answer)
        if last_summary:
            print(f"\n  [本轮上下文 {last_summary.get('peak_context', '?')} token"
                  f"，共 {len(messages)} 条消息]")

    if last_trace:
        print(f"\ntrace: {last_trace.path}")
        print("查看: python tracing.py")
    return 0


def main():
    argv = sys.argv[1:]
    mock = "--mock" in argv
    use_trace = "--no-trace" not in argv
    task = " ".join(a for a in argv if a not in FLAGS)

    bootstrap(argv)

    import agent  # noqa: E402 —— 必须在 bootstrap 之后，agent 在 import 时读配置

    if task:                     # 单次执行
        return agent.main(argv)

    return chat_loop(agent, mock, use_trace)


if __name__ == "__main__":
    raise SystemExit(main())
