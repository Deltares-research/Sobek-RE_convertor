from pathlib import Path
from configparser import ConfigParser

import pytest

from sre_convertor.io.fm.morphodynamics_writer import (
    format_morphodynamics_conversion_details,
    write_morphodynamics_files,
)
from sre_convertor.models import (
    ActiveLayerThicknessDefinition,
    Branch,
    BranchTransportParameters,
    CrossSectionLocation,
    LayerCompositionSample,
    MorphodynamicsSummary,
    NetworkModel,
    Node,
)


@pytest.mark.parametrize("thickness,nonuniform,expected", [(0.8, False, 0.8), (0.25, False, 0.25), (None, False, 1.0), (None, True, 1.0)])
def test_morphology_thresholds_and_audit(
    tmp_path: Path, thickness: float | None, nonuniform: bool, expected: float
) -> None:
    summary = MorphodynamicsSummary(
        branch_count_with_grainsize=1,
        has_morphology_switch=True,
        active_layer_thickness_m=thickness,
        active_layer_thicknesses=(
            ActiveLayerThicknessDefinition("b1", 0.0, 100.0, 0.5),
            ActiveLayerThicknessDefinition("b2", 0.0, 100.0, 0.8),
        ) if nonuniform else (),
        sediment_parameters=(("ALLUVIAL", "0.2"),),
    )
    mor_path, _, _, _ = write_morphodynamics_files(tmp_path, summary)
    config = ConfigParser()
    config.read(mor_path)
    assert config.getfloat("Morphology", "Thresh") == expected
    assert config.getfloat("Morphology", "Thresh") == config.getfloat("Underlayer", "ThTrLyr")
    assert config.getfloat("Morphology", "SedThr") == 0.1

    log = format_morphodynamics_conversion_details(summary, output_dir=tmp_path)
    assert f"Thresh = ThTrLyr = {expected:g} m" in log
    assert "not an exact mapping of SRE ALLUVIAL" in log
    assert "SedThr = 0.1 m" in log
    assert "no direct SRE sediment-specific depth threshold is mapped" in log
    assert "used in dflowfm/mor.mor Thresh (line" in log
    assert "used in dflowfm/mor.mor SedThr (line" in log


@pytest.mark.parametrize("method", ["PROPORTIONAL", "proportional", "EQUAL", "UNKNOWN"])
@pytest.mark.parametrize("morphology_written", [True, False])
def test_cross_section_update_method_audit(
    tmp_path: Path, method: str, morphology_written: bool
) -> None:
    summary = MorphodynamicsSummary(
        branch_count_with_grainsize=1,
        has_morphology_switch=True,
        morphology_parameters=(("METHOD", method),),
    )
    if morphology_written:
        mor_path, _, _, _ = write_morphodynamics_files(tmp_path, summary)
        config = ConfigParser()
        config.read(mor_path)
        assert config.getint("Morphology", "BedUpd") == 1
        assert not config.has_option("Morphology", "METHOD")

    log = format_morphodynamics_conversion_details(
        summary, output_dir=tmp_path,
        activation_requested=morphology_written, morphology_written=morphology_written,
    )
    assert f"$MORPAR METHOD: read at GRAINP.TXT line not found; value={method};" in log
    assert "built-in proportional updating for tabulated 1D (zwRiver) cross-sections" in log
    if method.upper() == "PROPORTIONAL":
        assert "bed-level changes scale with depth below the main-channel reference level" in log
        assert "No separate METHOD keyword is written" in log
        assert "not necessarily every SRE" in log
    else:
        assert f"METHOD={method} is not mapped" in log
    if morphology_written:
        assert "used in dflowfm/mor.mor BedUpd (line" in log
    else:
        assert "not written to dflowfm/mor.mor (BedUpd absent)" in log


def test_morphodynamics_audit_explains_unmapped_sre_options(tmp_path: Path) -> None:
    summary = MorphodynamicsSummary(
        branch_count_with_grainsize=1,
        has_morphology_switch=True,
        sediment_parameters=(("KINVIS", "0.000001"), ("ALLUVIAL", "0.2")),
        morphology_parameters=(
            ("REDUC", "1"),
            ("ITERMAX", "200"),
            ("STABGI", "1.01"),
            ("STABGT", "1.01"),
            ("ALPHADG", "1"),
            ("ALPHAEG", "1"),
        ),
        graded_sediment_options=(
            ("HEIOPT", "GILL"),
            ("LENOPT", "YALIN"),
            ("ROUOPT", "WHITE"),
            ("LATHIC", "INITIAL"),
            ("LAYERS", "1"),
            ("NUNLAY", "20"),
        ),
        graded_sediment_parameters=(
            ("BETA1", "0.5"),
            ("BETA2", "0.2"),
            ("THEXFA", "0.25"),
            ("FDI", "1"),
            ("DUNLEN", "10"),
            ("DZUNLA", "0.5"),
            ("REDFACMIL", "4"),
            ("ZBEPS", "0.05"),
        ),
        graded_sediment_flags=("ADNOML", "NNONGP", "SEDIM"),
    )

    log = format_morphodynamics_conversion_details(summary, output_dir=tmp_path)

    assert "Each entry names the SRE field, its meaning" in log
    assert "$MORPAR REDUC" in log
    assert "dummy parameter that should be 1" in log
    assert "$GSOPT LENOPT" in log
    assert "dune-length predictor" in log
    assert "$GSPAR REDFACMIL" in log
    assert "REDFACMIL * Dm" in log
    assert "$GSOPT ADNOML flag" in log
    assert "adapts non-moving-layer composition" in log


def test_write_morphodynamics_files_writes_mor_and_sed(tmp_path: Path) -> None:
    summary = MorphodynamicsSummary(
        branch_count_with_grainsize=3,
        has_morphology_switch=True,
        representative_d50_m=0.0017,
        sediment_fractions_d50_m=(0.0008, 0.0017, 0.0034),
        grain_size_sample_count=30,
        branch_composition=(
            ("7262", (0.2, 0.7, 0.1)),
            ("8127", (0.1, 0.6, 0.3)),
        ),
    )

    mor_path, sed_path, composition_path, bed_comp_path = write_morphodynamics_files(tmp_path, summary)

    assert mor_path.exists()
    assert sed_path.exists()
    assert composition_path.exists()
    assert bed_comp_path.exists()

    mor_text = mor_path.read_text(encoding="utf-8")
    sed_text = sed_path.read_text(encoding="utf-8")

    assert "[Morphology]" in mor_text
    assert "[Underlayer]" in mor_text
    assert "IniComp          = mini.ini" in mor_text
    assert "IUnderLyr        = 1" in mor_text
    assert sed_text.count("[Sediment]") == 3
    assert "SedDia           = 8.0000000e-04" in sed_text
    assert "SedDia           = 1.7000000e-03" in sed_text
    assert "SedDia           = 3.4000000e-03" in sed_text

    composition_text = composition_path.read_text(encoding="utf-8")
    assert "[BedCompositionFileInformation]" in composition_text
    assert "[Layer]" in composition_text
    assert "Type = volume fraction" in composition_text

    bed_comp_text = bed_comp_path.read_text(encoding="utf-8")
    assert "[BedCompositionFileInformation]" in bed_comp_text
    assert "Type = volume fraction" in bed_comp_text


def test_write_morphodynamics_files_uses_constant_ttlform_for_initial_layers(tmp_path: Path) -> None:
    summary = MorphodynamicsSummary(
        branch_count_with_grainsize=1,
        has_morphology_switch=True,
        graded_sediment_options=(("LATHIC", "INITIAL"),),
    )

    mor_path, _, _, _ = write_morphodynamics_files(tmp_path, summary)

    assert "TTLForm          = 1" in mor_path.read_text(encoding="utf-8")


def test_write_morphodynamics_files_uses_sre_sediment_density_parameters(tmp_path: Path) -> None:
    summary = MorphodynamicsSummary(
        branch_count_with_grainsize=1,
        has_morphology_switch=True,
        sediment_fractions_d50_m=(0.001,),
        grain_size_sample_count=1,
        sediment_parameters=(("RELDEN", "1.65"), ("PACFAC", "0.30")),
        graded_sediment_options=(("HEIOPT", "GILL"), ("LENOPT", "YALIN")),
        graded_sediment_flags=("NONNGP",),
    )

    mor_path, sed_path, _, _ = write_morphodynamics_files(tmp_path, summary)

    mor_text = mor_path.read_text(encoding="utf-8")
    sed_text = sed_path.read_text(encoding="utf-8")
    assert "# SRE $GSOPT HEIOPT = GILL" not in mor_text
    assert "# SRE $GSOPT NONNGP" not in sed_text
    assert "{source_comments}" not in sed_text
    assert "RhoSol           = 2.6500000e+03" in sed_text
    assert "CDryB            = 1.8550000e+03" in sed_text


def test_write_morphodynamics_files_writes_spatial_layer_composition(tmp_path: Path) -> None:
    summary = MorphodynamicsSummary(
        branch_count_with_grainsize=1,
        has_morphology_switch=True,
        sediment_fractions_d50_m=(0.0008, 0.0017),
        grain_size_sample_count=2,
        branch_composition=(("b1", (0.25, 0.75)),),
        underlayer_count=3,
        underlayer_thickness_m=0.25,
    )
    network = NetworkModel(
        nodes=(
            Node(id="n1", name="n1", x=10.0, y=20.0),
            Node(id="n2", name="n2", x=30.0, y=20.0),
        ),
        branches=(Branch(id="b1", name="b1", from_node_id="n1", to_node_id="n2", length=20.0),),
        source_file=Path("DEFTOP.1"),
    )
    locations = (
        CrossSectionLocation(
            id="cs1",
            name="cs1",
            branch_id="b1",
            chainage=0.0,
            definition_id="d1",
            reference_level=0.0,
        ),
        CrossSectionLocation(
            id="cs2",
            name="cs2",
            branch_id="b1",
            chainage=20.0,
            definition_id="d2",
            reference_level=0.0,
        ),
    )

    mor_path, _, composition_path, _ = write_morphodynamics_files(tmp_path, summary, network, locations)

    mor_text = mor_path.read_text(encoding="utf-8")
    assert "IUnderLyr        = 2" in mor_text
    assert "MxNULyr          = 2" in mor_text
    assert "ThUnLyr          = 2.5000000e-01" in mor_text

    composition_text = composition_path.read_text(encoding="utf-8")
    assert composition_path.name == "mini.ini"
    assert "Thick = gsd_ini_str/lyr01_thk.xyz" in composition_text
    assert "Thick = gsd_ini_str/lyr03_thk.xyz" in composition_text
    assert "Fraction1 = gsd_ini_str/lyr01_frac01.xyz" in composition_text
    assert "Fraction2 = gsd_ini_str/lyr01_frac02.xyz" in composition_text
    assert composition_text.count("[Layer]") == 3

    assert (tmp_path / "mor.ini").exists() is False
    assert (tmp_path / "mor.composition.ini").exists() is False
    assert (tmp_path / "gsd_ini_str" / "lyr01_thk.xyz").read_text(encoding="utf-8").splitlines() == [
        "1.000000000000000E+01 2.000000000000000E+01 2.500000000000000E-01",
        "3.000000000000000E+01 2.000000000000000E+01 2.500000000000000E-01",
    ]
    assert (tmp_path / "gsd_ini_str" / "lyr03_thk.xyz").exists()
    assert (tmp_path / "gsd_ini_str" / "lyr01_frac02.xyz").read_text(encoding="utf-8").splitlines() == [
        "1.000000000000000E+01 2.000000000000000E+01 7.500000000000000E-01",
        "3.000000000000000E+01 2.000000000000000E+01 7.500000000000000E-01",
    ]


def test_write_morphodynamics_files_interpolates_gsinit_layer_composition(tmp_path: Path) -> None:
    summary = MorphodynamicsSummary(
        branch_count_with_grainsize=1,
        has_morphology_switch=True,
        sediment_fractions_d50_m=(0.001, 0.002),
        grain_size_sample_count=2,
        branch_composition=(("b1", (0.5, 0.5)),),
        underlayer_count=2,
        underlayer_thickness_m=0.5,
        layer_composition=(
            LayerCompositionSample(
                branch_id="b1",
                chainage=0.0,
                layer_weights=((0.2, 0.8), (0.6, 0.4)),
            ),
            LayerCompositionSample(
                branch_id="b1",
                chainage=10.0,
                layer_weights=((0.4, 0.6), (0.8, 0.2)),
            ),
        ),
    )
    network = NetworkModel(
        nodes=(
            Node(id="n1", name="n1", x=0.0, y=0.0),
            Node(id="n2", name="n2", x=10.0, y=0.0),
        ),
        branches=(Branch(id="b1", name="b1", from_node_id="n1", to_node_id="n2", length=10.0),),
        source_file=Path("DEFTOP.1"),
    )
    locations = (
        CrossSectionLocation(
            id="cs-mid",
            name="cs-mid",
            branch_id="b1",
            chainage=5.0,
            definition_id="d1",
            reference_level=0.0,
        ),
    )

    write_morphodynamics_files(tmp_path, summary, network, locations)

    assert (tmp_path / "gsd_ini_str" / "lyr01_frac01.xyz").read_text(encoding="utf-8").splitlines() == [
        "5.000000000000000E+00 0.000000000000000E+00 3.000000000000000E-01",
    ]
    assert (tmp_path / "gsd_ini_str" / "lyr02_frac02.xyz").read_text(encoding="utf-8").splitlines() == [
        "5.000000000000000E+00 0.000000000000000E+00 3.000000000000000E-01",
    ]


def test_write_morphodynamics_files_writes_spatial_acal_from_transport_mu(tmp_path: Path) -> None:
    (tmp_path / "acal_99.xyz").write_text("stale\n", encoding="utf-8")
    summary = MorphodynamicsSummary(
        branch_count_with_grainsize=1,
        has_morphology_switch=True,
        sediment_fractions_d50_m=(0.001, 0.002),
        grain_size_sample_count=2,
        branch_composition=(("b1", (0.5, 0.5)),),
        transport_parameters=(BranchTransportParameters(branch_id="b1", formula_type=1, calibration_factor=0.7),),
    )
    network = NetworkModel(
        nodes=(
            Node(id="n1", name="n1", x=0.0, y=0.0),
            Node(id="n2", name="n2", x=10.0, y=0.0),
        ),
        branches=(Branch(id="b1", name="b1", from_node_id="n1", to_node_id="n2", length=10.0),),
        source_file=Path("DEFTOP.1"),
    )
    locations = (
        CrossSectionLocation(
            id="cs1",
            name="cs1",
            branch_id="b1",
            chainage=0.0,
            definition_id="d1",
            reference_level=0.0,
        ),
    )

    _, sed_path, _, _ = write_morphodynamics_files(tmp_path, summary, network, locations)

    sed_text = sed_path.read_text(encoding="utf-8")
    assert "ACal             = #acal_01.xyz#" in sed_text
    assert "# SRE DEFTRN branch b1 MU = 0.7" not in sed_text
    assert (tmp_path / "acal_01.xyz").read_text(encoding="utf-8").splitlines() == [
        "0.000000000000000E+00 0.000000000000000E+00 7.000000000000000E-01",
    ]
    assert (tmp_path / "acal_02.xyz").exists()
    assert (tmp_path / "acal_99.xyz").exists() is False
