from pathlib import Path

from sre_convertor.io.sre.rtc_reader import read_sre_rtc


def test_read_sre_rtc_extracts_native_controllers_and_triggers() -> None:
    input_dir = Path(__file__).resolve().parents[1] / "data" / "sre_simulation"

    summary, warnings = read_sre_rtc(input_dir)

    assert warnings == []
    assert len(summary.controllers) == 8
    assert len(summary.triggers) == 6

    by_name = {controller.name: controller for controller in summary.controllers}
    driel_pid = by_name["Driel PID"]
    assert driel_pid.id == "73321"
    assert driel_pid.controller_type == "pid"
    assert driel_pid.controlled_parameter == "crest_level"
    assert driel_pid.controlled_structure_id == "ST_73326"
    assert driel_pid.trigger_ids == ("73317", "73389")
    assert driel_pid.observation_branch_id == "99938"
    assert driel_pid.observation_chainage == 34000.0
    assert dict(driel_pid.parameters)["VA"] == "0.0025"

    by_trigger = {trigger.name: trigger for trigger in summary.triggers}
    driel_open = by_trigger["Driel open"]
    assert driel_open.id == "73316"
    assert driel_open.trigger_type == "time"
    assert driel_open.branch_id == "99938"
    assert driel_open.chainage == 34000.0
    assert driel_open.tables[0][0][0] == "1985/01/01;00:00:00"
