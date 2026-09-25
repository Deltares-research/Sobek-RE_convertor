from pathlib import Path

from sre_convertor.io.fm.structure_writer import write_structures
from sre_convertor.models import Structure


def test_write_structures_uses_structure_name_as_fm_id(tmp_path: Path) -> None:
    structure = Structure(
        id="ST_100",
        name="Driel_Z",
        branch_id="7262",
        chainage=13000.0,
        structure_type="orifice",
        crest_level=2.7,
        crest_width=102.0,
    )

    target_path = tmp_path / "Structures.ini"
    write_structures((structure,), target_path)

    text = target_path.read_text(encoding="utf-8")
    assert "    id                    = Driel_Z" in text
    assert "    id                    = ST_100" not in text