from pathlib import Path

from sre_convertor.io.fm.structure_writer import write_structures
from sre_convertor.models import Structure


def test_write_structures_uses_structure_name_as_fm_id(tmp_path: Path) -> None:
    structure = Structure(
        id="ST_100",
        name="Driel_Z",
        branch_id="7262",
        chainage=13000.0,
        structure_type="generalstructure",
        crest_level=2.7,
        crest_width=90.0,
        gate_height=0.0,
        upstream1_width=102.0,
        upstream1_level=2.26,
        upstream2_width=95.0,
        upstream2_level=2.36,
        downstream1_width=95.0,
        downstream1_level=2.16,
        downstream2_width=102.0,
        downstream2_level=2.06,
    )

    target_path = tmp_path / "Structures.ini"
    write_structures((structure,), target_path)

    text = target_path.read_text(encoding="utf-8")
    assert "    id                    = Driel_Z" in text
    assert "    id                    = ST_100" not in text
    assert "    type                  = generalstructure" in text
    assert "    upstream1Width         = 102.000" in text
    assert "    upstream1Level         = 2.260" in text
    assert "    crestWidth            = 90.000" in text
    assert "    downstream2Level       = 2.060" in text
    assert "    gateHeight             = 1.0e10" in text
    assert "    gateOpeningWidth       = 0.000" in text