"""Extract unmodified public-server results for the offline MCP Apps host."""

import argparse
import json
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=root / "scripts/smoke_result_remote.json")
    parser.add_argument("--output", type=Path, default=root / "ui/fixtures")
    args = parser.parse_args()
    rows = json.loads(args.source.read_text(encoding="utf-8"))
    targets = {
        "3인 시나리오": "real_propose.json",
        "서연 예산 양보": "real_yield.json",
        "불가능 시나리오": "real_infeasible.json",
    }
    fixtures = []
    for step, filename in targets.items():
        matches = [row for row in rows if row.get("step") == step]
        if len(matches) != 1:
            raise ValueError(f"Expected exactly one result: {step}")
        row = matches[0]
        state = row["result"]
        if state.get("v") != 1 or not isinstance(row["content"], list):
            raise ValueError(f"Unexpected result shape: {step}")
        # Only the CallToolResult envelope changes; all recorded values stay intact.
        content = [{"type": "text", "text": value} for value in row["content"]]
        fixtures.append((filename, {"structuredContent": state, "content": content}))
    args.output.mkdir(parents=True, exist_ok=True)
    for filename, fixture in fixtures:
        (args.output / filename).write_text(
            json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(filename)


if __name__ == "__main__":
    main()
