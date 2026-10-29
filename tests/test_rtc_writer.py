from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from sre_convertor import convert_case
from sre_convertor.io.fm.rtc_writer import (
    FEWS_NAMESPACE,
    OPENDA_NAMESPACE,
    RtcConversionError,
    compile_sre_rtc,
    write_sre_rtc_package,
)
from sre_convertor.io.sre.rtc_reader import (
    SreRtcComparison,
    SreRtcController,
    SreRtcControllerType,
    SreRtcControlledParameter,
    SreRtcSummary,
    SreRtcTableMetadata,
    SreRtcTableRole,
    SreRtcTrigger,
    SreRtcTriggerCondition,
    SreRtcTriggerSlot,
    SreRtcTriggerType,
)
from sre_convertor.models import (
    Branch,
    NetworkModel,
    Node,
    RuntimeSettings,
    Structure,
)


_FEWS = {"f": FEWS_NAMESPACE}
_OPENDA = {"o": OPENDA_NAMESPACE}


def test_compile_and_write_sre_rtc_package_for_supported_time_control(
    tmp_path: Path,
) -> None:
    summary, network, structures, runtime = _synthetic_case()

    compilation = compile_sre_rtc(summary, network, structures, runtime)
    created_files = write_sre_rtc_package(
        compilation,
        tmp_path / "rtc",
        tmp_path / "dflowfm",
    )

    tools_path = tmp_path / "rtc" / "xml_dir" / "rtcToolsConfig.xml"
    data_path = tmp_path / "rtc" / "xml_dir" / "rtcDataConfig.xml"
    state_path = tmp_path / "rtc" / "xml_dir" / "state_import.xml"
    observation_path = tmp_path / "dflowfm" / "rtc_observations.xyn"
    schedule_path = tmp_path / "rtc" / "xml_dir" / "time_schedule_import.xml"
    assert tools_path in created_files
    assert data_path in created_files
    assert state_path in created_files
    assert observation_path in created_files
    assert schedule_path in created_files
    assert (tmp_path / "rtc" / "xsd_dir" / "rtcToolsConfig.xsd").exists()
    assert observation_path.read_text(encoding="utf-8") == (
        "50.000 0.000 rtc_obs_bB1_s50\n"
    )
    schedule = ET.parse(schedule_path).getroot()
    time_step = schedule.find(
        "./p:series/p:header/p:timeStep",
        {"p": "http://www.wldelft.nl/fews/PI"},
    )
    assert time_step is not None
    assert time_step.attrib == {
        "unit": "minute",
        "multiplier": "10",
        "divider": "1",
    }

    tools = ET.parse(tools_path).getroot()
    time_absolute = tools.find("./f:rules/f:rule/f:timeAbsolute", _FEWS)
    assert time_absolute is not None
    assert time_absolute.findtext("f:input/f:x", namespaces=_FEWS) == (
        "time_schedule_controller_10"
    )
    assert time_absolute.findtext("f:output/f:y", namespaces=_FEWS) == (
        "output_ST_1_crest_level"
    )
    standard = tools.find("./f:triggers/f:trigger/f:standard", _FEWS)
    assert standard is not None
    assert standard.findtext(
        "f:condition/f:relationalOperator",
        namespaces=_FEWS,
    ) == "LessEqual"
    assert standard.find("f:false", _FEWS) is None

    data = ET.parse(data_path).getroot()
    assert data.findtext(
        "./f:importSeries/f:PITimeSeriesFile/f:timeSeriesFile",
        namespaces=_FEWS,
    ) == "time_schedule_import.xml"
    assert data.findtext(
        "./f:importSeries/f:timeSeries/f:PITimeSeries/f:locationId",
        namespaces=_FEWS,
    ) == "time_schedule_controller_10"
    assert data.findtext(
        "./f:importSeries/f:timeSeries/f:OpenMIExchangeItem/f:quantityId",
        namespaces=_FEWS,
    ) == "water_level"
    assert data.findtext(
        "./f:exportSeries/f:timeSeries/f:OpenMIExchangeItem/f:quantityId",
        namespaces=_FEWS,
    ) == "crestlevel"

    state = ET.parse(state_path).getroot()
    assert state.findtext(
        "./o:treeVector/o:treeVectorLeaf/o:vector",
        namespaces=_OPENDA,
    ) == "1.5"

    assert compilation.rtc_coupling.flow_to_rtc[0].source_name == (
        "observations/rtc_obs_bB1_s50/water_level"
    )
    assert compilation.rtc_coupling.flow_to_rtc[0].target_name == (
        "input_rtc_obs_bB1_s50_water_level"
    )
    assert compilation.rtc_coupling.rtc_to_flow[0].source_name == (
        "output_ST_1_crest_level"
    )
    assert compilation.rtc_coupling.rtc_to_flow[0].target_name == (
        "weirs/weir1/crestlevel"
    )


def test_compile_sre_rtc_matches_low_trigger_at_equal_threshold() -> None:
    summary, network, structures, runtime = _synthetic_case()
    first_controller = summary.controllers[0]
    second_controller = replace(
        first_controller,
        id="11",
        name="High level",
        trigger_slots=(
            SreRtcTriggerSlot(index=0, trigger_id="21", active=True),
            *first_controller.trigger_slots[1:],
        ),
    )
    high_trigger = _synthetic_trigger(
        trigger_id="21",
        comparison=SreRtcComparison.GREATER_THAN,
        threshold=10.0,
    )
    summary = SreRtcSummary(
        controllers=(first_controller, second_controller),
        triggers=(summary.triggers[0], high_trigger),
    )

    compilation = compile_sre_rtc(summary, network, structures, runtime)
    tools = ET.fromstring(
        dict(compilation.file_contents)["xml_dir/rtcToolsConfig.xml"]
    )
    comparisons = [
        element.text
        for element in tools.findall(
            ".//f:condition/f:relationalOperator",
            _FEWS,
        )
    ]
    assert comparisons == ["LessEqual", "Greater"]


def test_compile_sre_rtc_selects_hydraulic_controller_table_and_block_extrapolation() -> None:
    summary, network, structures, runtime = _synthetic_case()
    controller = replace(
        summary.controllers[0],
        type_code=1,
        controller_type=SreRtcControllerType.HYDRAULIC,
        tables=(
            (("1", "99"), ("2", "98")),
            (("6", "8.8"), ("10", "2.5")),
        ),
        table_metadata=(
            SreRtcTableMetadata(
                role=SreRtcTableRole.STEER_TABLE,
                axis_labels=("Water Level [m]", "Crest Level [m]"),
                interpolation_code=0,
                periodicity_code=0,
            ),
            SreRtcTableMetadata(
                role=SreRtcTableRole.HYDRAULIC_CONTROLLER,
                axis_labels=("Water Level [m]", "Crest Level [m]"),
                interpolation_code=0,
                periodicity_code=0,
            ),
        ),
    )
    compilation = compile_sre_rtc(
        replace(summary, controllers=(controller,)),
        network,
        structures,
        runtime,
    )
    tools = ET.fromstring(
        dict(compilation.file_contents)["xml_dir/rtcToolsConfig.xml"]
    )
    lookup = tools.find("./f:rules/f:rule/f:lookupTable", _FEWS)

    assert lookup is not None
    records = lookup.findall("./f:table/f:record", _FEWS)
    assert [(record.attrib["x"], record.attrib["y"]) for record in records] == [
        ("6", "8.8"),
        ("10", "2.5"),
    ]
    assert lookup.findtext("f:interpolationOption", namespaces=_FEWS) == "LINEAR"
    assert lookup.findtext("f:extrapolationOption", namespaces=_FEWS) == "BLOCK"
    state = ET.fromstring(dict(compilation.file_contents)["xml_dir/state_import.xml"])
    assert state.findtext(
        "./o:treeVector/o:treeVectorLeaf/o:vector",
        namespaces=_OPENDA,
    ) == "8.8"


def test_activate_rtc_converts_bundled_sre_controls(
    tmp_path: Path,
) -> None:
    input_dir = Path(__file__).resolve().parents[1] / "data" / "sre_simulation"
    output_dir = tmp_path / "fm_case"

    report = convert_case(
        input_dir,
        output_dir,
        model_name="rtc_converted_case",
        activate_rtc=True,
    )

    tools = ET.parse(
        output_dir / "rtc" / "xml_dir" / "rtcToolsConfig.xml"
    ).getroot()
    assert tools.find("./f:rules/f:rule/f:timeAbsolute", _FEWS) is not None
    assert tools.find("./f:rules/f:rule/f:lookupTable", _FEWS) is not None
    assert (
        output_dir / "rtc" / "xml_dir" / "time_schedule_import.xml"
    ) in report.files_created
    assert "LessEqual" in (output_dir / "rtc" / "xml_dir" / "rtcToolsConfig.xml").read_text(
        encoding="utf-8"
    )
    assert (output_dir / "rtc" / "xml_dir" / "state_import.xml").exists()
    state = ET.parse(
        output_dir / "rtc" / "xml_dir" / "state_import.xml"
    ).getroot()
    gate_state = state.find(
        "./o:treeVector/o:treeVectorLeaf[@id='output_ST_99477_gate_height']/o:vector",
        _OPENDA,
    )
    assert gate_state is not None
    assert gate_state.text == "0"


def test_compile_sre_rtc_extends_and_preserves_time_schedule() -> None:
    summary, network, structures, runtime = _synthetic_case()
    controller = replace(
        summary.controllers[0],
        tables=(
            (
                ("2000/01/01;00:02:00", "1"),
                ("2000/01/01;00:08:00", "5"),
                ("2000/01/01;00:12:00", "9"),
            ),
        ),
    )
    summary = replace(summary, controllers=(controller,))

    compilation = compile_sre_rtc(summary, network, structures, runtime)
    schedule = ET.fromstring(
        dict(compilation.file_contents)["xml_dir/time_schedule_import.xml"]
    )
    events = schedule.findall("./p:series/p:event", {"p": "http://www.wldelft.nl/fews/PI"})
    assert schedule.find(
        "./p:series/p:header/p:timeStep",
        {"p": "http://www.wldelft.nl/fews/PI"},
    ).attrib == {
        "unit": "minute",
        "multiplier": "2",
        "divider": "1",
    }
    assert [
        (event.attrib["time"], event.attrib["value"]) for event in events
    ] == [
        ("00:00:00", "1"),
        ("00:02:00", "1"),
        ("00:04:00", "2.33333333333333"),
        ("00:06:00", "3.66666666666667"),
        ("00:08:00", "5"),
        ("00:10:00", "7"),
    ]
    state = ET.fromstring(dict(compilation.file_contents)["xml_dir/state_import.xml"])
    assert state.findtext(
        "./o:treeVector/o:treeVectorLeaf/o:vector",
        namespaces=_OPENDA,
    ) == "9"


def test_compile_sre_rtc_rejects_unmatched_interval() -> None:
    summary, network, structures, runtime = _synthetic_case()
    low_controller = summary.controllers[0]
    high_controller = replace(
        low_controller,
        id="11",
        name="High level",
        trigger_slots=(
            SreRtcTriggerSlot(index=0, trigger_id="21", active=True),
            *low_controller.trigger_slots[1:],
        ),
    )
    high_trigger = _synthetic_trigger(
        trigger_id="21",
        comparison=SreRtcComparison.GREATER_THAN,
        threshold=11.0,
    )
    summary = SreRtcSummary(
        controllers=(low_controller, high_controller),
        triggers=(summary.triggers[0], high_trigger),
    )

    with pytest.raises(RtcConversionError, match="10 < H <= 11"):
        compile_sre_rtc(summary, network, structures, runtime)


def _synthetic_case() -> tuple[
    SreRtcSummary,
    NetworkModel,
    tuple[Structure, ...],
    RuntimeSettings,
]:
    condition = SreRtcTriggerCondition(
        time=None,
        enable_code=None,
        combination_code=None,
        comparison=SreRtcComparison.LESS_THAN,
        threshold=10.0,
        raw_values=(
            "2000/01/01;00:00:00",
            "-1",
            "-1",
            "0",
            "10",
        ),
    )
    trigger = SreRtcTrigger(
        id="20",
        name="low level",
        type_code=1,
        trigger_type=SreRtcTriggerType.HYDRAULIC,
        branch_id="B1",
        chainage=50.0,
        tables=((condition.raw_values,),),
        conditions=(condition,),
        source_file=Path("DEFSTR.5"),
        source_line=1,
        raw_lines=(),
    )
    controller = SreRtcController(
        id="10",
        name="constant crest",
        type_code=0,
        controller_type=SreRtcControllerType.TIME,
        parameter_code=0,
        controlled_parameter=SreRtcControlledParameter.CREST_LEVEL,
        controlled_structure_id="ST_1",
        trigger_slots=(
            SreRtcTriggerSlot(index=0, trigger_id="20", active=True),
            SreRtcTriggerSlot(index=1, trigger_id=None, active=False),
            SreRtcTriggerSlot(index=2, trigger_id=None, active=False),
            SreRtcTriggerSlot(index=3, trigger_id=None, active=False),
        ),
        observation_branch_id="B1",
        observation_chainage=50.0,
        tables=(
            (
                ("2000/01/01;00:00:00", "0"),
                ("2000/01/01;00:10:00", "0"),
            ),
        ),
        table_metadata=(
            SreRtcTableMetadata(
                role=SreRtcTableRole.TIME_CONTROLLER,
                axis_labels=("Time", "Crest Level [m]"),
                interpolation_code=0,
                periodicity_code=0,
            ),
        ),
        source_file=Path("DEFSTR.4"),
        source_line=1,
        raw_lines=(),
    )
    network = NetworkModel(
        nodes=(
            Node(id="A", name="upstream", x=0.0, y=0.0),
            Node(id="B", name="downstream", x=100.0, y=0.0),
        ),
        branches=(
            Branch(
                id="B1",
                name="branch",
                from_node_id="A",
                to_node_id="B",
                length=100.0,
            ),
        ),
        source_file=Path("DEFTOP.1"),
    )
    structures = (
        Structure(
            id="ST_1",
            name="weir1",
            branch_id="B1",
            chainage=50.0,
            structure_type="weir",
            crest_level=1.5,
            crest_width=1.0,
        ),
    )
    runtime = RuntimeSettings(
        refdate=datetime(2000, 1, 1),
        tstart_seconds=0,
        tstop_seconds=600,
    )
    return SreRtcSummary(controllers=(controller,), triggers=(trigger,)), network, structures, runtime


def _synthetic_trigger(
    *,
    trigger_id: str,
    comparison: SreRtcComparison,
    threshold: float,
) -> SreRtcTrigger:
    operation = "0" if comparison is SreRtcComparison.LESS_THAN else "1"
    condition = SreRtcTriggerCondition(
        time=None,
        enable_code=None,
        combination_code=None,
        comparison=comparison,
        threshold=threshold,
        raw_values=("2000/01/01;00:00:00", "-1", "-1", operation, str(threshold)),
    )
    return SreRtcTrigger(
        id=trigger_id,
        name=trigger_id,
        type_code=1,
        trigger_type=SreRtcTriggerType.HYDRAULIC,
        branch_id="B1",
        chainage=50.0,
        tables=((condition.raw_values,),),
        conditions=(condition,),
        source_file=Path("DEFSTR.5"),
        source_line=1,
        raw_lines=(),
    )
