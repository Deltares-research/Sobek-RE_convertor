from pathlib import Path

from sre_convertor.io.fm.initial_field_writer import write_initial_fields_reference, write_initial_water_depth
from sre_convertor.models import BranchInitialCondition


def test_write_initial_fields_reference_uses_fm_inifield_v2_format(tmp_path: Path) -> None:
    target = tmp_path / "initialFields.ini"

    write_initial_fields_reference(target, "InitialWaterDepth.ini")

    text = target.read_text(encoding="utf-8")
    assert "[General]" in text
    assert "fileVersion         = 2.00" in text
    assert "fileType            = iniField" in text
    assert "[Initial]" in text
    assert "quantity            = waterdepth" in text
    assert "dataFile            = InitialWaterDepth.ini" in text
    assert "dataFileType        = 1dField" in text


def test_write_initial_water_depth_uses_median_deficn_level(tmp_path: Path) -> None:
    target = tmp_path / "InitialWaterDepth.ini"
    source = (
        BranchInitialCondition(branch_id="1", chainage=0.0, water_level=8.0),
        BranchInitialCondition(branch_id="2", chainage=0.0, water_level=5.0),
        BranchInitialCondition(branch_id="3", chainage=0.0, water_level=6.2),
    )

    write_initial_water_depth(target, source)

    text = target.read_text(encoding="utf-8")
    assert "value               = 6.200" in text
