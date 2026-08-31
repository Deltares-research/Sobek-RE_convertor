from datetime import datetime
from pathlib import Path

from sre_convertor.io.fm.boundary_writer import write_external_forcing_file, write_lateral_bc_files
from sre_convertor.models import LateralDischarge, RuntimeSettings, TimeSeriesPoint


def test_write_lateral_bc_files_extends_single_point_to_runtime_end(tmp_path: Path) -> None:
    runtime = RuntimeSettings(refdate=datetime(2000, 1, 1), tstart_seconds=0, tstop_seconds=7200)
    laterals = (
        LateralDischarge(
            id="L1",
            name="L1",
            branch_id="B1",
            chainage=10.0,
            series=(TimeSeriesPoint(time="lt", value=1.25),),
        ),
    )

    created = write_lateral_bc_files(laterals, runtime, tmp_path)
    assert len(created) == 1

    text = (tmp_path / "L1.bc").read_text(encoding="utf-8")
    assert "0\t1.250000" in text
    assert "121\t1.250000" in text


def test_write_external_forcing_file_omits_lateral_name_keyword(tmp_path: Path) -> None:
    laterals = (
        LateralDischarge(
            id="L1",
            name="SomeName",
            branch_id="B1",
            chainage=10.0,
            series=(),
        ),
    )

    target = tmp_path / "demo.ext"
    write_external_forcing_file((), laterals, target)

    text = target.read_text(encoding="utf-8")
    assert "[lateral]" in text
    assert "name                  =" not in text
