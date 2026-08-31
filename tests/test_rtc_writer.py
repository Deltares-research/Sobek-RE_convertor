from pathlib import Path

from sre_convertor.io.fm.dimr_writer import write_dimr_config
from sre_convertor.io.fm.rtc_writer import copy_rtc_package, read_rtc_coupling


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
