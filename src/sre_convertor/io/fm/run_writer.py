from __future__ import annotations

from pathlib import Path


def write_run_dimr_bat(output_dir: Path, dimr_config_name: str = "dimr_config.xml") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / "run_dimr.bat"

    content = "\n".join(
        [
            "@echo off",
            "setlocal",
            "",
            "set RUN_DIMR=c:\\checkouts\\sc_fm_trunk\\install_fm-suite_release\\bin\\run_dimr.bat",
            "",
            "if not exist \"%RUN_DIMR%\" (",
            "  echo Could not find run_dimr.bat at %RUN_DIMR%",
            "  echo Update RUN_DIMR in this script to the Delft3D FM installation path.",
            "  exit /b 1",
            ")",
            "",
            f"call \"%RUN_DIMR%\" {dimr_config_name}",
            "",
        ]
    )
    target.write_text(content, encoding="utf-8")
    return target
