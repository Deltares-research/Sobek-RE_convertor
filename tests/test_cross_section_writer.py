from pathlib import Path

from sre_convertor.io.fm.cross_section_writer import write_cross_section_definitions, write_cross_section_locations
from sre_convertor.models import CrossSectionDefinition, CrossSectionLocation


def test_write_cross_section_definitions_sets_mainwidth_from_flowwidths(tmp_path: Path) -> None:
    target = tmp_path / "CrossSectionDefinitions.ini"
    definition = CrossSectionDefinition(
        id="x1",
        name="x1",
        levels=(0.0, 1.0),
        flow_widths=(3.0, 5.5),
        total_widths=(3.0, 5.5),
        main_width=4.0,
        fp1_width=1.5,
        fp2_width=0.5,
    )

    write_cross_section_definitions((definition,), target)

    text = target.read_text(encoding="utf-8")
    assert "mainWidth = 4.000000" in text
    assert "fp1Width = 1.500000" in text
    assert "fp2Width = 0.500000" in text
    assert "id = x1" in text
    assert "frictionIds = Main;FloodPlain1;FloodPlain2" in text
    assert "#" not in text


def test_write_cross_section_locations_uses_unquoted_string_values(tmp_path: Path) -> None:
    target = tmp_path / "CrossSectionLocations.ini"
    location = CrossSectionLocation(
        id="CS_INT_99938_001076",
        name="section",
        branch_id="99938",
        chainage=1076.0,
        definition_id="DEF_001",
        reference_level=1.25,
    )

    write_cross_section_locations((location,), target, branch_names={"99938": "NRHBR2"})

    text = target.read_text(encoding="utf-8")
    assert "id = CS_INT_99938_001076" in text
    assert "branchId = NRHBR2" in text
    assert "definitionId = DEF_001" in text
    assert "#" not in text
