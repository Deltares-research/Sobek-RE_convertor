from __future__ import annotations

from pathlib import Path

from ...models import BranchRoughness
from .records import load_records


def read_friction(input_dir: Path) -> tuple[tuple[BranchRoughness, ...], list[str]]:
    warnings: list[str] = []
    records = load_records(input_dir, "DEFFRC", {"BDFR"})

    roughness_by_branch: dict[str, BranchRoughness] = {}
    for record in records:
        branch_id = record.attrs.get("ci")
        if not branch_id:
            continue

        values: list[float] = []
        if record.tables:
            for row in record.tables[0]:
                if len(row) < 2:
                    continue
                try:
                    values.append(float(row[1]))
                except ValueError:
                    continue

        if not values:
            warnings.append(f"DEFFRC branch {branch_id} has no valid friction values; using default roughness.")
            continue

        # FM roughness writer currently uses one representative value per branch.
        representative = sum(values) / len(values)
        roughness_by_branch[branch_id] = BranchRoughness(
            branch_id=branch_id,
            friction_type="Chezy",
            value=representative,
        )

    roughness = tuple(roughness_by_branch[key] for key in sorted(roughness_by_branch.keys()))
    return roughness, warnings
