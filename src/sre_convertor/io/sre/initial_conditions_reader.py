from __future__ import annotations

from pathlib import Path
import shlex

from ...models import BranchInitialCondition
from .records import list_family_files


def read_initial_conditions(input_dir: Path) -> tuple[tuple[BranchInitialCondition, ...], list[str]]:
    warnings: list[str] = []

    initial_conditions: list[BranchInitialCondition] = []
    for path in list_family_files(input_dir, "DEFICN"):
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for raw_line in lines:
            line = raw_line.strip()
            if not line or not line.upper().startswith("FLIN "):
                continue

            parsed = _parse_flin_line(line)
            if parsed is None:
                warnings.append("Skipped DEFICN FLIN record with unsupported token layout.")
                continue

            branch_id, chainage, water_level = parsed
            if branch_id == "-1":
                continue

            initial_conditions.append(
                BranchInitialCondition(
                    branch_id=branch_id,
                    chainage=chainage,
                    water_level=water_level,
                )
            )

    initial_conditions_sorted = tuple(
        sorted(initial_conditions, key=lambda item: (item.branch_id, item.chainage))
    )
    return initial_conditions_sorted, warnings


def _as_float(value: str | None, default: float | None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _parse_flin_line(line: str) -> tuple[str, float, float] | None:
    tokens = shlex.split(line)
    if not tokens or tokens[0].upper() != "FLIN":
        return None

    branch_id = _value_after(tokens, "ci")
    if branch_id is None:
        return None

    chainage = _value_two_after(tokens, "lq")
    water_level = _value_two_after(tokens, "ll")
    if chainage is None or water_level is None:
        return None

    return branch_id, chainage, water_level


def _value_after(tokens: list[str], key: str) -> str | None:
    key_lower = key.lower()
    for idx in range(len(tokens) - 1):
        if tokens[idx].lower() == key_lower:
            return tokens[idx + 1]
    return None


def _value_two_after(tokens: list[str], key: str) -> float | None:
    key_lower = key.lower()
    for idx in range(len(tokens) - 2):
        if tokens[idx].lower() == key_lower:
            return _as_float(tokens[idx + 2], None)
    return None
