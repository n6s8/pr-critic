from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REAL_WORLD_CASES_PATH = Path(__file__).with_name("real_world_cases.json")


def load_real_world_cases() -> list[dict[str, Any]]:
    payload = json.loads(REAL_WORLD_CASES_PATH.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = []
    for item in payload:
        pr_url = str(item["pr_url"])
        description = str(item["description"])
        cases.append(
            {
                "id": pr_url,
                "pr_url": pr_url,
                "name": description,
                "category": str(item.get("category", "real_world")),
                "expected_issues": list(item.get("expected_issues", [])),
            }
        )
    return cases
