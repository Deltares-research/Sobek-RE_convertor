from __future__ import annotations

from pathlib import Path

from ...models import CrossSectionDefinition, CrossSectionLocation


def write_cross_section_definitions(
    definitions: tuple[CrossSectionDefinition, ...],
    target_path: Path,
) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        "[General]",
        "   fileVersion           = 3.00",
        "   fileType              = crossDef",
        "",
    ]

    for definition in definitions:
        main_width = max(definition.flow_widths) if definition.flow_widths else 1.0
        lines.extend(
            [
                "[Definition]",
                f"   id = #{definition.id}#",
                "   type = zwRiver",
                "   thalweg = 0.000000",
                f"   numLevels = {float(len(definition.levels)):.6f}",
                f"   levels = {_format_series(definition.levels)}",
                f"   flowWidths = {_format_series(definition.flow_widths)}",
                f"   totalWidths = {_format_series(definition.total_widths)}",
                f"   mainWidth = {main_width:.6f}",
                "   fp1Width = 0.000000",
                "   fp2Width = 0.000000",
                "   isShared = 0.000000",
                "",
            ]
        )

    target_path.write_text("\n".join(lines), encoding="utf-8")


def write_cross_section_locations(
    locations: tuple[CrossSectionLocation, ...],
    target_path: Path,
) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [
        "[General]",
        "   fileVersion           = 1.01",
        "   fileType              = crossLoc",
        "",
    ]

    for location in locations:
        lines.extend(
            [
                "[CrossSection]",
                f"   id = #{location.id}#",
                f"   branchId = #{location.branch_id}#",
                f"   chainage = {location.chainage:.6f}",
                f"   shift = {location.reference_level:.6f}",
                f"   definitionId = #{location.definition_id}#",
                "",
            ]
        )

    target_path.write_text("\n".join(lines), encoding="utf-8")


def _format_series(values: tuple[float, ...]) -> str:
    return " ".join(f"{value:.6f}" for value in values)
