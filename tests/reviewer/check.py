import argparse
import json
import re
import sys
from difflib import unified_diff
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Compare reviewer answers with fixed baselines.")
    parser.add_argument("answers", type=Path, help="JSON object mapping case IDs to raw answer strings")
    args = parser.parse_args()
    cases = json.loads(Path(__file__).with_name("cases.json").read_text(encoding="utf-8"))
    actual = json.loads(args.answers.read_text(encoding="utf-8-sig"))
    if not isinstance(actual, dict) or any(not isinstance(value, str) for value in actual.values()):
        parser.error("Expected a JSON object with string values")

    failures = []
    expected_ids = {case["id"] for case in cases}
    for extra in sorted(actual.keys() - expected_ids):
        failures.append(f"{extra}: unexpected answer")
    for case in cases:
        case_id, expected = case["id"], case["expected"]
        answer = actual.get(case_id)
        if answer is None:
            failures.append(f"{case_id}: missing answer")
            continue
        if not re.fullmatch(case["pattern"], answer):
            failures.append(f"{case_id}: invariant failed: {case['preserve']}")
        if answer != expected:
            diff = unified_diff(expected.split("\n"), answer.split("\n"),
                                fromfile=f"{case_id}/expected", tofile=f"{case_id}/actual", lineterm="")
            failures.append("\n".join(diff))
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"{len(cases)} reviewer answers match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
