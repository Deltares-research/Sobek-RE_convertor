from pathlib import Path
import json

from netCDF4 import Dataset, chartostring
import pytest
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

    with Dataset(net_path) as netcdf:
        assert "time" not in netcdf.dimensions
        assert "strLengthIds" in netcdf.dimensions
        assert "strLengthLongNames" in netcdf.dimensions
        assert "idstrlength" not in netcdf.dimensions
        assert "longstrlength" not in netcdf.dimensions
        assert {
            "mesh1d_edge_x",
            "mesh1d_edge_y",
            "mesh1d_node_x",
            "mesh1d_node_y",
        }.intersection(netcdf.variables)
        assert {"network", "network_node_x", "network_edge_nodes"}.issubset(netcdf.variables)
        assert int(netcdf.variables["mesh1d_edge_nodes"].start_index) == 0
        assert int(netcdf.variables["mesh1d_edge_branch"].start_index) == 0
        assert netcdf.variables["network_branch_order"].mesh == "network"
        assert netcdf.variables["network_branch_order"].dimensions == ("network_nEdges",)
        assert [value.strip() for value in chartostring(netcdf.variables["network1d_node_id"][:])] == ["us", "ds"]
        assert [value.strip() for value in chartostring(netcdf.variables["network1d_node_long_name"][:])] == ["us", "ds"]
        assert [value.strip() for value in chartostring(netcdf.variables["network1d_branch_id"][:])] == ["main"]
        assert [value.strip() for value in chartostring(netcdf.variables["network1d_branch_long_name"][:])] == ["main"]


@pytest.mark.integration
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


@pytest.mark.integration
def test_convert_case_creates_requested_plots(tmp_path: Path) -> None:
    input_dir = Path(__file__).resolve().parents[1] / "data" / "sre_simulation"
    output_dir = tmp_path / "fm_case_figures"

    report = convert_case(input_dir, output_dir, model_name="demo_case_figures", create_plots=True)

    figure_paths = {
        output_dir / "fig" / "grid.png",
        output_dir / "fig" / "initial_sediment_composition.png",
    }
    timeseries_paths = tuple((output_dir / "fig").glob("timeseries_*.png"))
    branch_figure_paths = tuple((output_dir / "fig").glob("initial_sediment_composition_branch_*.png"))
    initial_condition_paths = tuple((output_dir / "fig").glob("initial_condition_branch_*.png"))
    friction_paths = tuple((output_dir / "fig").glob("friction_branch_*.png"))
    assert figure_paths.issubset(set(report.files_created))
    assert all(path.exists() and path.stat().st_size > 0 for path in figure_paths)
    assert timeseries_paths
    assert all(path in report.files_created and path.stat().st_size > 0 for path in timeseries_paths)
    assert len(branch_figure_paths) == 7
    assert all(path in report.files_created and path.stat().st_size > 0 for path in branch_figure_paths)
    assert initial_condition_paths
    assert all(path in report.files_created and path.stat().st_size > 0 for path in initial_condition_paths)
    assert friction_paths
    assert all(path in report.files_created and path.stat().st_size > 0 for path in friction_paths)


@pytest.mark.integration
def test_convert_case_writes_detailed_conversion_log(tmp_path: Path) -> None:
    input_dir = Path(__file__).resolve().parents[1] / "data" / "sre_simulation"
    output_dir = tmp_path / "fm_case_log"

    report = convert_case(input_dir, output_dir, model_name="demo_case_log")

    log_path = output_dir / "conversion.log"
    log_text = log_path.read_text(encoding="utf-8")

    assert log_path in report.files_created
    assert "Conversion flags and options" in log_text
    assert "model_name = demo_case_log" in log_text
    assert "network_only = False" in log_text
    assert "activate_cross_sections = True" in log_text
    assert "test_duration_seconds = 7200" in log_text
    assert "activate_morphodynamics = False" in log_text
    assert "activate_rtc = False" in log_text
    assert "DEFTOP.1" in log_text
    assert "read_cross_sections" in log_text
    assert "Network input read details" in log_text
    assert "All input file read details" in log_text
    assert "DEFCND.1: read " in log_text
    assert "DEFCRS.1 lines " in log_text
    assert "DEFICN.1: read " in log_text
    assert "GRAINP.TXT: read " in log_text
    assert "Parsed values read" in log_text
    assert "lateral id=" in log_text
    assert "time_start=" in log_text
    assert "time_end=" in log_text
    assert "minimum=" in log_text
    assert "maximum=" in log_text
    assert "time_series=[" not in log_text
    assert "cross-section definition id=" in log_text
    assert "levels_count=" in log_text
    assert "levels_min=" in log_text
    assert "levels_max=" in log_text
    assert "levels=[" not in log_text
    assert "roughness branch=" in log_text
    assert "initial condition branch=" in log_text
    assert "structure id=" in log_text
    assert "DEFTOP source records:" in log_text
    assert "Grid connectivity:" in log_text
    assert "Generated grid points:" in log_text
    assert "start=" in log_text
    assert "end=" in log_text
    assert "length=" in log_text
    assert "average_step=" in log_text
    assert "minimum_step=" in log_text
    assert "maximum_step=" in log_text
    assert "chainages=" not in log_text
    assert "dflowfm/demo_case_log_net.nc" in log_text
    assert "dflowfm/demo_case_log.mdu" in log_text
    assert "conversion.log" not in log_text
    assert f"Network nodes: {report.nodes_count}" in log_text
    assert f"Network branches: {report.branches_count}" in log_text


def test_convert_network_writes_network_only_conversion_log(tmp_path: Path) -> None:
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

    convert_network(input_dir, output_dir, model_name="network_log")

    log_text = (output_dir / "conversion.log").read_text(encoding="utf-8")

    assert "network_only = True" in log_text
    assert "read_sre_network: DEFTOP.1 and DEFGRD.* -> network model" in log_text
    assert "Grid connectivity:" in log_text
    assert "branch 101: 0 -> 1" in log_text
    assert "dflowfm/network_log_net.nc" in log_text
    assert "dflowfm/network_log.mdu" in log_text
    assert "dimr_config.xml" in log_text


@pytest.mark.integration
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


@pytest.mark.integration
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


@pytest.mark.integration
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


@pytest.mark.integration
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


@pytest.mark.integration
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
