from __future__ import annotations

from pathlib import Path


def write_default_initial_water_depth(target_path: Path, default_depth: float = 5.0) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(
        [
            "[General]",
            "    fileVersion           = 2.00",
            "    fileType              = 1dField",
            "",
            "[Global]",
            "    quantity            = waterdepth",
            "    unit                = m",
            f"    value               = {default_depth:.3f}",
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
