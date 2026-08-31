from pathlib import Path
import json

import xarray as xr

from sre_convertor import convert_case, convert_network


def test_convert_network_writes_minimum_fm_artifacts(tmp_path: Path) -> None:
    input_dir = tmp_path / "sre"
    output_dir = tmp_path / "fm"
    input_dir.mkdir()

    (input_dir / "DEFTOP.1").write_text(
        "\n".join(
            [
                "NODE id '0' nm 'us' px 0.0 py 0.0 node",
                "NODE id '1' nm 'ds' px 1000.0 py 0.0 node",
                "BRCH id '101' nm 'main' bn '0' en '1' al 1000.0 brch",
            ]
        ),
        encoding="utf-8",
    )

    report = convert_network(input_dir, output_dir, model_name="demo")

    assert report.nodes_count == 2
    assert report.branches_count == 1

    dimr_path = output_dir / "dimr_config.xml"
    mdu_path = output_dir / "dflowfm" / "demo.mdu"
    net_path = output_dir / "dflowfm" / "demo_net.nc"

    assert dimr_path.exists()
    assert mdu_path.exists()
    assert net_path.exists()

    dimr = dimr_path.read_text(encoding="utf-8")
    assert "<workingDir>dflowfm</workingDir>" in dimr
    assert "<inputFile>demo.mdu</inputFile>" in dimr

    mdu = mdu_path.read_text(encoding="utf-8")
    assert "demo_net.nc" in mdu

    ds = xr.open_dataset(net_path)
    try:
        assert int(ds.sizes["network1d_nNodes"]) == 2
        assert int(ds.sizes["network1d_nEdges"]) == 1
        assert float(ds["network1d_edge_length"].values[0]) == 1000.0
        assert "projected_coordinate_system" in ds.variables
        assert "Deltares-0.10" in str(ds.attrs.get("Conventions", ""))
    finally:
        ds.close()


def test_convert_case_activates_laterals_structures_and_initial_fields(tmp_path: Path) -> None:
    input_dir = Path(__file__).resolve().parents[1] / "data" / "sre_simulation"
    output_dir = tmp_path / "fm_case"

    report = convert_case(input_dir, output_dir, model_name="demo_case")

    assert report.nodes_count > 0
    assert report.branches_count > 0

    dflowfm_dir = output_dir / "dflowfm"
    mdu = (dflowfm_dir / "demo_case.mdu").read_text(encoding="utf-8")
    ext = (dflowfm_dir / "demo_case.ext").read_text(encoding="utf-8")

    assert "StructureFile                     = " in mdu
    assert "IniFieldFile                      = initialFields.ini" in mdu
    assert "CrossLocFile                      = CrossSectionLocations.ini" in mdu
    assert "CrossDefFile                      = CrossSectionDefinitions.ini" in mdu

    assert "[lateral]" in ext
    assert (dflowfm_dir / "initialFields.ini").exists()

    roughness = (dflowfm_dir / "roughness-Main.ini").read_text(encoding="utf-8")
    assert "frictionType          = Chezy" in roughness


def test_convert_case_can_disable_cross_sections(tmp_path: Path) -> None:
    input_dir = Path(__file__).resolve().parents[1] / "data" / "sre_simulation"
    output_dir = tmp_path / "fm_case_cross"

    convert_case(
        input_dir,
        output_dir,
        model_name="demo_case_cross",
        activate_cross_sections=False,
    )

    mdu = (output_dir / "dflowfm" / "demo_case_cross.mdu").read_text(encoding="utf-8")
    assert "CrossLocFile                      = " in mdu
    assert "CrossDefFile                      = " in mdu


def test_convert_case_can_reduce_runtime_for_testing(tmp_path: Path) -> None:
    input_dir = Path(__file__).resolve().parents[1] / "data" / "sre_simulation"
    output_dir = tmp_path / "fm_case_short"

    convert_case(
        input_dir,
        output_dir,
        model_name="demo_case_short",
        test_duration_seconds=3600,
    )

    mdu = (output_dir / "dflowfm" / "demo_case_short.mdu").read_text(encoding="utf-8")
    assert "TStop                             = 3600" in mdu


def test_convert_case_can_enable_morphodynamics_block(tmp_path: Path) -> None:
    input_dir = Path(__file__).resolve().parents[1] / "data" / "sre_simulation"
    output_dir = tmp_path / "fm_case_mor"

    convert_case(
        input_dir,
        output_dir,
        model_name="demo_case_mor",
        activate_morphodynamics=True,
    )

    dflowfm_dir = output_dir / "dflowfm"
    mdu = (dflowfm_dir / "demo_case_mor.mdu").read_text(encoding="utf-8")
    assert "[sediment]" in mdu
    assert "MorFile                           = mor.mor" in mdu
    assert "SedFile                           = sed.sed" in mdu
    assert "BedlevType                        = 1" in mdu
    assert (dflowfm_dir / "mor.mor").exists()
    assert (dflowfm_dir / "sed.sed").exists()
    assert (dflowfm_dir / "mor_composition.ini").exists()
    mor_text = (dflowfm_dir / "mor.mor").read_text(encoding="utf-8")
    assert "IUnderLyr        = 2" in mor_text
    assert "MxNULyr          = 19" in mor_text
    assert "ThUnLyr          = 5.0000000e-01" in mor_text
    assert (dflowfm_dir / "gsd_ini_str" / "lyr20_thk.xyz").exists()


def test_convert_case_can_enable_rtc_with_supplied_package(tmp_path: Path) -> None:
    input_dir = Path(__file__).resolve().parents[1] / "data" / "sre_simulation"
    rtc_source_dir = Path(__file__).resolve().parents[1] / "data" / "fm" / "rtc"
    output_dir = tmp_path / "fm_case_rtc"

    report = convert_case(
        input_dir,
        output_dir,
        model_name="demo_case_rtc",
        activate_rtc=True,
        rtc_source_dir=rtc_source_dir,
    )

    dimr_text = (output_dir / "dimr_config.xml").read_text(encoding="utf-8")
    assert (output_dir / "rtc" / "rtcDataConfig.xml").exists()
    assert any(path.name == "rtcToolsConfig.xml" for path in report.files_created)
    assert "<component name=\"RTC\">" in dimr_text
    assert "<coupler name=\"flowfm_to_rtc\">" in dimr_text
    assert "<coupler name=\"rtc_to_flowfm\">" in dimr_text
    assert "<time>0 600 7200</time>" in dimr_text
    assert "<sourceName>observations/LMW.Drielboven/water_level</sourceName>" in dimr_text
    assert "<targetName>weirs/ST_Driel_zom/CrestLevel</targetName>" in dimr_text


def test_convert_case_warns_when_rtc_requested_without_package(tmp_path: Path) -> None:
    input_dir = Path(__file__).resolve().parents[1] / "data" / "sre_simulation"
    output_dir = tmp_path / "fm_case_missing_rtc"

    report = convert_case(input_dir, output_dir, model_name="demo_case_no_rtc", activate_rtc=True)

    dimr_text = (output_dir / "dimr_config.xml").read_text(encoding="utf-8")
    mdu_text = (output_dir / "dflowfm" / "demo_case_no_rtc.mdu").read_text(encoding="utf-8")
    inventory_path = output_dir / "rtc_sre_inventory.json"
    assert any("activate_rtc=True requested" in warning for warning in report.warnings)
    assert any("Native SRE RTC CNTL/TRGR records" in warning for warning in report.warnings)
    assert "<component name=\"RTC\">" in dimr_text
    assert "ObsFile                           = ObservationPoints_rtc.ini" in mdu_text
    assert (output_dir / "rtc" / "rtcToolsConfig.xml").exists()
    assert (output_dir / "dflowfm" / "ObservationPoints_rtc.ini").exists()
    assert inventory_path.exists()
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    assert len(inventory["controllers"]) == 8
    assert len(inventory["triggers"]) == 6
