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
            "if defined D3D_FM_SUITE_DIR (",
            "  set RUN_DIMR=%D3D_FM_SUITE_DIR%\\plugins\\DeltaShell.Dimr\\kernels\\x64\\bin\\run_dimr.bat",
            ") else (",
            "  set RUN_DIMR=c:\\Program Files\\Deltares\\Delft3D FM Suite 2025.02 HMWQ\\plugins\\DeltaShell.Dimr\\kernels\\x64\\bin\\run_dimr.bat",
            ")",
            "",
            "if not exist \"%RUN_DIMR%\" (",
            "  echo Could not find run_dimr.bat at %RUN_DIMR%",
            "  echo Set D3D_FM_SUITE_DIR to your Delft3D FM Suite installation root.",
            "  exit /b 1",
            ")",
            "",
            f"call \"%RUN_DIMR%\" {dimr_config_name}",
            "",
        ]
    )
    target.write_text(content, encoding="utf-8")
    return target
