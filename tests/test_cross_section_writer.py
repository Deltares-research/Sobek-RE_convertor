from pathlib import Path

from sre_convertor.io.fm.cross_section_writer import write_cross_section_definitions
from sre_convertor.models import CrossSectionDefinition


def test_write_cross_section_definitions_sets_mainwidth_from_flowwidths(tmp_path: Path) -> None:
    target = tmp_path / "CrossSectionDefinitions.ini"
    definition = CrossSectionDefinition(
        id="x1",
        name="x1",
        levels=(0.0, 1.0),
        flow_widths=(3.0, 5.5),
        total_widths=(3.0, 5.5),
    )

    write_cross_section_definitions((definition,), target)

    text = target.read_text(encoding="utf-8")
    assert "mainWidth = 5.500000" in text
