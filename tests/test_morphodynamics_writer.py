from pathlib import Path

from sre_convertor.io.fm.morphodynamics_writer import write_morphodynamics_files
from sre_convertor.models import (
    Branch,
    BranchTransportParameters,
    CrossSectionLocation,
    LayerCompositionSample,
    MorphodynamicsSummary,
    NetworkModel,
    Node,
)


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
    assert "IniComp          = mor_composition.ini" in mor_text
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
    assert "# SRE $GSOPT HEIOPT = GILL" in mor_text
    assert "# SRE $GSOPT NONNGP" in sed_text
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
    assert composition_path.name == "mor_composition.ini"
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
    assert "# SRE DEFTRN branch b1 MU = 0.7" in sed_text
    assert (tmp_path / "acal_01.xyz").read_text(encoding="utf-8").splitlines() == [
        "0.000000000000000E+00 0.000000000000000E+00 7.000000000000000E-01",
    ]
    assert (tmp_path / "acal_02.xyz").exists()
    assert (tmp_path / "acal_99.xyz").exists() is False
