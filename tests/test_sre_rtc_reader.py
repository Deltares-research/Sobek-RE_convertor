from pathlib import Path

import pytest

from sre_convertor.io.sre.rtc_reader import (
    SreRtcComparison,
    SreRtcControllerType,
    SreRtcControlledParameter,
    SreRtcTableRole,
    SreRtcTriggerType,
    read_sre_rtc,
)


def test_read_sre_rtc_preserves_encoded_types_and_active_trigger_slots() -> None:
    input_dir = Path(__file__).resolve().parents[1] / "data" / "sre_simulation"

    summary, warnings = read_sre_rtc(input_dir)

    assert warnings == []
    assert len(summary.controllers) == 8
    assert len(summary.triggers) == 6

    controllers = {controller.id: controller for controller in summary.controllers}
    driel_hydraulic = controllers["73321"]
    assert driel_hydraulic.name == "Driel PID"
    assert driel_hydraulic.type_code == 1
    assert driel_hydraulic.controller_type is SreRtcControllerType.HYDRAULIC
    assert driel_hydraulic.parameter_code == 0
    assert driel_hydraulic.controlled_parameter is SreRtcControlledParameter.CREST_LEVEL
    assert driel_hydraulic.controlled_structure_id == "ST_73326"
    assert driel_hydraulic.active_trigger_ids == ("73317",)
    assert driel_hydraulic.trigger_slots[1].trigger_id == "73389"
    assert not driel_hydraulic.trigger_slots[1].active
    assert driel_hydraulic.observation_branch_id == "99938"
    assert driel_hydraulic.observation_chainage == 34000.0
    assert driel_hydraulic.tables[-1] == (
        ("6", "8.8"),
        ("8.7", "8.8"),
        ("9.2", "8.7"),
        ("9.9", "6"),
        ("10", "2.5"),
    )
    assert [table.role for table in driel_hydraulic.table_metadata] == [
        SreRtcTableRole.STEER_TABLE,
        SreRtcTableRole.HYDRAULIC_CONTROLLER,
    ]
    assert driel_hydraulic.table_metadata[-1].axis_labels == (
        "Water Level [m]",
        "Crest Level [m]",
    )
    assert driel_hydraulic.table_metadata[-1].interpolation_code == 0
    assert driel_hydraulic.table_metadata[-1].periodicity_code == 0

    driel_open = controllers["73319"]
    assert driel_open.controller_type is SreRtcControllerType.TIME
    assert driel_open.table_metadata[0].role is SreRtcTableRole.TIME_CONTROLLER
    assert driel_open.tables[0] == (
        ("1985/01/01;00:00:00", "0"),
        ("2000/01/01;00:00:00", "0"),
    )
    assert controllers["99474"].controlled_parameter is SreRtcControlledParameter.GATE_HEIGHT

    triggers = {trigger.id: trigger for trigger in summary.triggers}
    driel_open_trigger = triggers["73316"]
    assert driel_open_trigger.type_code == 1
    assert driel_open_trigger.trigger_type is SreRtcTriggerType.HYDRAULIC
    assert driel_open_trigger.branch_id == "99938"
    assert driel_open_trigger.chainage == 34000.0
    assert driel_open_trigger.conditions[0].comparison is SreRtcComparison.GREATER_THAN
    assert driel_open_trigger.conditions[0].threshold == 10.0


def test_read_sre_rtc_rejects_unknown_controller_type(tmp_path: Path) -> None:
    (tmp_path / "DEFSTR.4").write_text(
        "CNTL id '1' nm 'unknown' ta 1 0 0 0 gi '2' '-1' '-1' '-1' ct 9 ca 0 cntl\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="controller 1 has unknown ct code 9"):
        read_sre_rtc(tmp_path)


def test_read_sre_rtc_rejects_unknown_trigger_operation(tmp_path: Path) -> None:
    (tmp_path / "DEFSTR.5").write_text(
        "\n".join(
            [
                "TRGR id '1' nm 'bad op' ty 1 tb '10' tl 5 tt tr 'Trigger' TBLE",
                "'2000/01/01;00:00:00' -1 -1 9 10 <",
                "tble",
                "trgr",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="trigger 1 has unknown operation code 9"):
        read_sre_rtc(tmp_path)


def test_read_sre_rtc_rejects_missing_active_trigger_reference(tmp_path: Path) -> None:
    (tmp_path / "DEFSTR.4").write_text(
        "CNTL id '1' nm 'missing trigger' ta 1 0 0 0 gi '2' '-1' '-1' '-1' ct 0 ca 0 cntl\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="references missing active trigger\\(s\\): 2"):
        read_sre_rtc(tmp_path)
