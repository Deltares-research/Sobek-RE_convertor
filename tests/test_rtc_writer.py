from pathlib import Path
import xml.etree.ElementTree as ET

from sre_convertor.io.fm.dimr_writer import write_dimr_config
from sre_convertor.io.fm.rtc_writer import copy_rtc_package, read_rtc_coupling, write_native_rtc_package
from sre_convertor.io.sre.rtc_reader import read_sre_rtc
from sre_convertor.models import RuntimeSettings
from datetime import datetime


def test_read_rtc_coupling_derives_items_from_reference_package() -> None:
    rtc_config = Path(__file__).resolve().parents[1] / "data" / "fm" / "rtc" / "rtcDataConfig.xml"

    coupling = read_rtc_coupling(rtc_config)

    assert len(coupling.flow_to_rtc) == 8
    assert len(coupling.rtc_to_flow) == 6
    assert coupling.flow_to_rtc[0].source_name == "observations/LMW.Drielboven/water_level"
    assert coupling.flow_to_rtc[0].target_name == "[Input]LMW.Drielboven/Water level (op)"
    assert coupling.rtc_to_flow[0].source_name == "[Output]ST_Driel_zom/Crest level (s)"
    assert coupling.rtc_to_flow[0].target_name == "weirs/ST_Driel_zom/CrestLevel"


def test_copy_rtc_package_and_write_dimr_config_with_couplers(tmp_path: Path) -> None:
    rtc_source = Path(__file__).resolve().parents[1] / "data" / "fm" / "rtc"
    rtc_target, coupling = copy_rtc_package(rtc_source, tmp_path / "rtc")

    write_dimr_config(
        tmp_path / "dimr_config.xml",
        "demo.mdu",
        include_rtc=True,
        rtc_coupling=coupling,
        start_time=100,
        stop_time=700,
    )

    dimr_text = (tmp_path / "dimr_config.xml").read_text(encoding="utf-8")
    assert rtc_target.is_dir()
    assert (rtc_target / "rtcDataConfig.xml").exists()
    assert "<time>100 600 700</time>" in dimr_text
    assert "<component name=\"RTC\">" in dimr_text
    assert "<library>FBCTools_BMI</library>" in dimr_text
    assert "<sourceName>[Output]ST_Driel_zom/Crest level (s)</sourceName>" in dimr_text
    assert "<targetName>weirs/ST_Driel_zom/CrestLevel</targetName>" in dimr_text
    assert "<sourceName>observations/LMW.Drielboven/water_level</sourceName>" in dimr_text
    assert "<targetName>[Input]LMW.Drielboven/Water level (op)</targetName>" in dimr_text


def test_write_native_rtc_package_from_sre_inventory(tmp_path: Path) -> None:
    input_dir = Path(__file__).resolve().parents[1] / "data" / "sre_simulation"
    summary, warnings = read_sre_rtc(input_dir)
    assert warnings == []

    _, coupling, observation_path, package_warnings = write_native_rtc_package(
        tmp_path / "rtc",
        summary,
        RuntimeSettings(refdate=datetime(1985, 1, 1), tstart_seconds=0, tstop_seconds=7200),
    )

    tools_text = (tmp_path / "rtc" / "rtcToolsConfig.xml").read_text(encoding="utf-8")
    data_text = (tmp_path / "rtc" / "rtcDataConfig.xml").read_text(encoding="utf-8")
    ET.parse(tmp_path / "rtc" / "rtcToolsConfig.xml")
    ET.parse(tmp_path / "rtc" / "rtcDataConfig.xml")
    assert observation_path is not None
    assert "SRE_RTC_99938_34000" in observation_path.read_text(encoding="utf-8")
    assert "[RelativeTimeRule]SRE/Driel_open" not in tools_text
    assert "[LookupSignal]SRE/Driel PID" in tools_text
    assert "[Input]SRE_RTC_99938_34000/Water level (op)" in data_text
    assert "[Output]ST_73326/Crest level (s)" in data_text
    assert any(item.source_name == "observations/SRE_RTC_99938_34000/water_level" for item in coupling.flow_to_rtc)
    assert any(item.target_name == "weirs/ST_73326/CrestLevel" for item in coupling.rtc_to_flow)
    assert any("unsupported parameter gate_height" in warning for warning in package_warnings)
    assert any("73319" in warning and "73321" in warning for warning in package_warnings)
