from pathlib import Path

from sre_convertor.io.fm.initial_field_writer import write_initial_fields_reference


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
