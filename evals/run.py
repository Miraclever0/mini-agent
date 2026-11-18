"""跑一组固定任务，报告通过率。

    python evals/run.py                 # 离线（--mock），不花钱，验证结构
    python evals/run.py --online        # 真实模型，会产生费用
    python evals/run.py --only 越界     # 只跑名字含「越界」的用例
    python evals/run.py --keep          # 保留失败的临时工作区，方便排查

每个用例都在独立的临时目录里、用独立进程跑：
    - 工作区隔离，用例之间不会互相污染
    - 进程隔离，模块状态（比如以后加的「读过哪些文件」）不会串
    - 走的是真实入口 run.py，测的是用户实际会用的那条路
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from cases import ALL_CASES, FIXTURE_README, Result

# 输出被管道接走时统一用 UTF-8
for _stream in (sys.stdout, sys.stderr):
    if not _stream.isatty():
        _stream.reconfigure(encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parent.parent
TIMEOUT = 180

# 临时工作区放在仓库内，而不是系统临时目录：
# 沙箱（以及某些 CI）会禁止往系统 temp 写东西。
TMP_ROOT = REPO / ".evals-tmp"


def load_events(workspace):
    """读工作区里最新的 trace。没有就返回空列表。"""
    trace_dir = workspace / "traces"
    if not trace_dir.is_dir():
        return []
    files = sorted(trace_dir.glob("*.jsonl"))
    if not files:
        return []
    events = []
    for line in files[-1].read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def run_case(case, online):
    TMP_ROOT.mkdir(exist_ok=True)
    # 不用 tempfile.mkdtemp：Windows 上它建的目录权限受限，沙箱进程写不进去。
    workspace = TMP_ROOT / f"case-{os.getpid()}-{time.time_ns()}"
    workspace.mkdir()
    (workspace / "README.md").write_text(FIXTURE_README, encoding="utf-8")
    for name, content in case.fixtures.items():
        (workspace / name).write_text(content, encoding="utf-8")

    cmd = [sys.executable, str(REPO / "run.py")]
    if not online:
        cmd.append("--mock")
    cmd.append(case.task)

    started = time.perf_counter()
    proc = subprocess.run(
        cmd, cwd=str(workspace), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=TIMEOUT,
    )
    duration = time.perf_counter() - started

    return Result(
        task=case.task,
        answer=proc.stdout or "",
        stderr=proc.stderr or "",
        exit_code=proc.returncode,
        workspace=workspace,
        events=load_events(workspace),
    ), duration


def cleanup(workspace):
    shutil.rmtree(workspace, ignore_errors=True)


def main():
    argv = sys.argv[1:]
    online = "--online" in argv
    keep = "--keep" in argv
    only = None
    if "--only" in argv:
        index = argv.index("--only")
        if index + 1 < len(argv):
            only = argv[index + 1]

    cases = [c for c in ALL_CASES if c.online == online]
    if only:
        cases = [c for c in cases if only in c.name]

    if not cases:
        sys.exit(f"没有匹配的用例（online={online}, only={only}）")

    # 清掉上次异常退出留下的工作区
    for stale in TMP_ROOT.glob("case-*"):
        shutil.rmtree(stale, ignore_errors=True)

    print(f"{'在线（真实模型，会计费）' if online else '离线（MockChat，不花钱）'}")
    print("")

    results = []
    for case in cases:
        result, duration = run_case(case, online)
        passed = case.check(result)
        results.append((case, passed))

        mark = "PASS" if passed else "FAIL"
        usage = result.usage()
        token_text = ""
        if usage:
            token_text = f"   {usage.get('prompt_tokens', 0) + usage.get('completion_tokens', 0)} tok"
        print(f"  [{mark}] {case.name:<16} {duration:5.1f}s{token_text}")

        if not passed:
            detail = case.detail(result)
            print(f"         {detail}")
            answer = (result.answer or "").strip().replace("\n", " ")[:160]
            print(f"         stdout: {answer}")
            if keep:
                print(f"         工作区保留在: {result.workspace}")
            else:
                cleanup(result.workspace)
        else:
            cleanup(result.workspace)

    passed_count = sum(1 for _, ok in results if ok)
    total = len(results)
    print("")
    print(f"通过 {passed_count}/{total} ({passed_count * 100 // total}%)")
    return 0 if passed_count == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
