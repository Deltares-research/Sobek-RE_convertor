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

        section_profiles: list[tuple[str, tuple[float, ...], tuple[float, ...]]] = []
        table_indices = (
            ("Main channel", 0),
            ("Floodplain 1", 2),
        )
        for section_name, table_index in table_indices:
            if table_index >= len(record.tables):
                continue
            table = record.tables[table_index]
            chainages: list[float] = []
            values: list[float] = []
            for row in table:
                if len(row) < 2:
                    continue
                try:
                    chainages.append(float(row[0]))
                    values.append(float(row[1]))
                except ValueError:
                    continue
            if chainages and values:
                section_profiles.append((section_name, tuple(chainages), tuple(values)))

        if not section_profiles:
            warnings.append(f"DEFFRC branch {branch_id} has no valid friction values; using default roughness.")
            continue

        main_profile = section_profiles[0]
        if record.attrs.get("s2") == "6":
            floodplain_2 = ("Floodplain 2", main_profile[1], main_profile[2])
        elif len(record.tables) > 4:
            table = record.tables[4]
            chainages = []
            values = []
            for row in table:
                if len(row) < 2:
                    continue
                try:
                    chainages.append(float(row[0]))
                    values.append(float(row[1]))
                except ValueError:
                    continue
            floodplain_2 = ("Floodplain 2", tuple(chainages), tuple(values))
        else:
            floodplain_2 = ("Floodplain 2", main_profile[1], main_profile[2])
        section_profiles.append(floodplain_2)

        chainages = main_profile[1]
        values = main_profile[2]

        roughness_by_branch[branch_id] = BranchRoughness(
            branch_id=branch_id,
            friction_type="Chezy",
            chainages=chainages,
            values=values,
            section_profiles=tuple(section_profiles),
        )

    roughness = tuple(roughness_by_branch[key] for key in sorted(roughness_by_branch.keys()))
    return roughness, warnings
