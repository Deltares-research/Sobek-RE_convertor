from __future__ import annotations

from pathlib import Path

from hydrolib.core.dflowfm.mdu.models import FMModel


def write_mdu(target_path: Path, net_file_name: str) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)

    model = FMModel()
    model.geometry.netfile = net_file_name
    model.save(target_path)
