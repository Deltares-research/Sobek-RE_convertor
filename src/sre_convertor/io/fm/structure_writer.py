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

        if structure.structure_type == "generalstructure":
            gate_height = structure.gate_height
            gate_height_text = (
                f"{gate_height:.3f}"
                if gate_height is not None and gate_height > 0
                else "1.0e10"
            )
            lines.extend(
                [
                    "    allowedFlowdir         = both",
                    f"    upstream1Width         = {_value_or_default(structure.upstream1_width, structure.crest_width):.3f}",
                    f"    upstream1Level         = {_value_or_default(structure.upstream1_level, structure.crest_level):.3f}",
                    f"    upstream2Width         = {_value_or_default(structure.upstream2_width, structure.crest_width):.3f}",
                    f"    upstream2Level         = {_value_or_default(structure.upstream2_level, structure.crest_level):.3f}",
                    f"    crestLength            = 0.000",
                    f"    downstream1Width       = {_value_or_default(structure.downstream1_width, structure.crest_width):.3f}",
                    f"    downstream1Level       = {_value_or_default(structure.downstream1_level, structure.crest_level):.3f}",
                    f"    downstream2Width       = {_value_or_default(structure.downstream2_width, structure.crest_width):.3f}",
                    f"    downstream2Level       = {_value_or_default(structure.downstream2_level, structure.crest_level):.3f}",
                    f"    gateLowerEdgeLevel     = {_value_or_default(structure.gate_lower_edge_level, structure.crest_level):.3f}",
                    f"    gateHeight             = {gate_height_text}",
                    f"    gateOpeningWidth       = {_value_or_default(structure.gate_opening_width, 0.0):.3f}",
                    "    gateOpeningHorizontalDirection = symmetric",
                    "    useVelocityHeight     = true",
                ]
            )
        elif structure.structure_type == "orifice":
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


def _value_or_default(value: float | None, default: float) -> float:
    return default if value is None else value
