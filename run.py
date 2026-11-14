"""mini-agent 的入口：准备配置，然后把参数交给 agent.main()。

用法:
    python run.py                    # 跑默认任务
    python run.py "你的任务"          # 跑指定任务
    python run.py --mock             # 不联网，用假模型跑一遍完整循环

首次运行会自动从 config.example.py 生成 config.py，并提示粘贴 DeepSeek Key。

为什么单独一个文件：
    agent.py 是可 import 的库，import 时会读配置。入口如果也放在里面，
    import 就会触发交互式提问，调试和测试都很难受。分开之后：
        - run.py 只做「准备配置 + 传参」两件事
        - agent.py 可以被单独 import，反复调用 run(task, chat_fn=...)
"""

import getpass
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.py"
EXAMPLE_PATH = HERE / "config.example.py"

# 与 agent.KEY_PLACEHOLDER 保持一致。这里不 import agent，
# 因为 agent 在 import 时就会读配置，必须等引导跑完。
PLACEHOLDER = "你的DeepSeekKey"

# 输出被管道接走时统一用 UTF-8，避免 Windows 下按 GBK 编码导致乱码
for _stream in (sys.stdout, sys.stderr):
    if not _stream.isatty():
        _stream.reconfigure(encoding="utf-8", errors="replace")


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


def main():
    bootstrap(sys.argv[1:])
    import agent  # noqa: E402  —— 必须在 bootstrap 之后，agent 在 import 时读配置
    return agent.main()


if __name__ == "__main__":
    raise SystemExit(main())
