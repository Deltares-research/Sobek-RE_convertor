from __future__ import annotations

from pathlib import Path

from ...models import BranchInitialCondition


def write_initial_water_depth(
    target_path: Path,
    initial_conditions: tuple[BranchInitialCondition, ...],
    default_depth: float = 5.0,
) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    depth_value = _derive_default_depth(initial_conditions, default_depth)
    content = "\n".join(
        [
            "[General]",
            "    fileVersion           = 2.00",
            "    fileType              = 1dField",
            "",
            "[Global]",
            "    quantity            = waterdepth",
            "    unit                = m",
            f"    value               = {depth_value:.3f}",
            "",
        ]
    )
    target_path.write_text(content, encoding="utf-8")


def write_initial_fields_reference(target_path: Path, water_depth_file_name: str) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(
        [
            "[General]",
            "    fileVersion         = 2.00",
            "    fileType            = iniField",
            "",
            "[Initial]",
            "    quantity            = waterdepth",
            f"    dataFile            = {water_depth_file_name}",
            "    dataFileType        = 1dField",
            "",
        ]
    )
    target_path.write_text(content, encoding="utf-8")


def _derive_default_depth(
    initial_conditions: tuple[BranchInitialCondition, ...],
    fallback: float,
) -> float:
    if not initial_conditions:
        return fallback

    levels = [item.water_level for item in initial_conditions]
    if not levels:
        return fallback

    # Use median water level as a stable proxy for startup depth.
    sorted_levels = sorted(levels)
    mid = len(sorted_levels) // 2
    if len(sorted_levels) % 2 == 0:
        return (sorted_levels[mid - 1] + sorted_levels[mid]) / 2.0
    return sorted_levels[mid]
