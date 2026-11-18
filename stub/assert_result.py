"""断言一份 .result.json 符合预期的规则计数。

供 stub/smoke_test.sh 在 docker run 后调用，也可独立使用：

    python3 stub/assert_result.py <result.json> <expected_pass> <expected_manual> <expected_exit>

退出码 0 表示全部匹配，1 表示不匹配（含详细差异）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def check(result: dict, exp_pass: int, exp_manual: int, exp_exit: int) -> list[str]:
    """返回差异描述列表；空列表表示全部匹配。"""
    summary = result.get("summary", {})
    diffs: list[str] = []
    actual_pass = summary.get("pass_count")
    actual_manual = summary.get("manual_required_count")
    actual_exit = result.get("exit_code")
    if actual_pass != exp_pass:
        diffs.append(f"pass_count: expected {exp_pass}, got {actual_pass}")
    if actual_manual != exp_manual:
        diffs.append(f"manual_required_count: expected {exp_manual}, got {actual_manual}")
    if actual_exit != exp_exit:
        diffs.append(f"exit_code: expected {exp_exit}, got {actual_exit}")
    # 额外一致性：逐条 status 与 summary 计数是否自洽
    results = result.get("check_results", [])
    pass_count = sum(1 for r in results if r.get("status") == "PASS")
    manual_count = sum(1 for r in results if r.get("status") == "MANUAL_REQUIRED")
    if pass_count != actual_pass:
        diffs.append(f"summary.pass_count({actual_pass}) != 实际 PASS 条数({pass_count})")
    if manual_count != actual_manual:
        diffs.append(f"summary.manual_required_count({actual_manual}) != 实际 MANUAL_REQUIRED 条数({manual_count})")
    return diffs


def main() -> int:
    if len(sys.argv) != 5:
        print("usage: assert_result.py <result.json> <expected_pass> <expected_manual> <expected_exit>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    exp_pass, exp_manual, exp_exit = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    result = json.loads(path.read_text(encoding="utf-8"))
    diffs = check(result, exp_pass, exp_manual, exp_exit)
    run_id = result.get("run_id", "?")
    overall = result.get("summary", {}).get("overall_status", "?")
    if diffs:
        print(f"[FAIL] {path.name} run_id={run_id} overall={overall}")
        for d in diffs:
            print(f"       - {d}")
        # 打印每条规则状态便于排查
        for r in result.get("check_results", []):
            print(f"       {r.get('id')}: {r.get('status')}")
        return 1
    print(f"[OK]   {path.name} run_id={run_id} overall={overall} pass={exp_pass} manual={exp_manual} exit={exp_exit}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
