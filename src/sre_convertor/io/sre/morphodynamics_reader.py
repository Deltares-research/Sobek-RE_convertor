from __future__ import annotations

from pathlib import Path

from ...models import MorphodynamicsSummary
from .records import load_records


def read_morphodynamics_summary(input_dir: Path) -> tuple[MorphodynamicsSummary, list[str]]:
    warnings: list[str] = []

    mpin_records = load_records(input_dir, "DEFICN", {"MPIN"})
    sbst_records = load_records(input_dir, "DEFSUB", {"SBST"})

    branch_ids = {
        record.attrs.get("ci", "")
        for record in mpin_records
        if record.attrs.get("ci") and record.attrs.get("ci") != "-1"
    }
    has_morphology_switch = any(record.attrs.get("md") == "1" for record in sbst_records)

    if branch_ids and not has_morphology_switch:
        warnings.append("MPIN grain-size initialization found, but DEFSUB does not indicate active morphology switch.")

    summary = MorphodynamicsSummary(
        branch_count_with_grainsize=len(branch_ids),
        has_morphology_switch=has_morphology_switch,
    )
    return summary, warnings
