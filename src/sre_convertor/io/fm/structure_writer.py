from __future__ import annotations

from pathlib import Path

from ...models import Structure


def write_structures(
    structures: tuple[Structure, ...],
    target_path: Path,
    branch_names: dict[str, str] | None = None,
) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        "[General]",
        "    fileVersion           = 2.00",
        "    fileType              = structure",
        "",
    ]

    branch_names = branch_names or {}
    for structure in structures:
        lines.extend(
            [
                "[Structure]",
                f"    id                    = {structure.name}",
                f"    branchId              = {branch_names.get(structure.branch_id, structure.branch_id)}",
                f"    chainage              = {structure.chainage:.3f}",
                f"    type                  = {structure.structure_type}",
                f"    crestLevel            = {structure.crest_level:.3f}",
                f"    crestWidth            = {structure.crest_width:.3f}",
            ]
        )

        if structure.structure_type == "orifice":
            lines.extend(
                [
                    "    allowedFlowDir        = both",
                    "    gateHeight            = 1.0e10",
                    f"    gateOpeningWidth      = {structure.gate_opening_width or structure.crest_width:.3f}",
                    f"    gateLowerEdgeLevel    = {structure.gate_lower_edge_level or structure.crest_level:.3f}",
                ]
            )

        lines.extend(
            [
                "    corrCoeff             = 1.000",
                "",
            ]
        )

    target_path.write_text("\n".join(lines), encoding="utf-8")
