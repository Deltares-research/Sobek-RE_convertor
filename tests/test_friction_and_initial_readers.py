from pathlib import Path

from sre_convertor.io.sre.friction_reader import read_friction
from sre_convertor.io.sre.initial_conditions_reader import read_initial_conditions
from sre_convertor.io.sre.morphodynamics_reader import read_morphodynamics_summary


def test_read_friction_extracts_branch_chezy_values() -> None:
    input_dir = Path(__file__).resolve().parents[1] / "data" / "sre_simulation"

    roughness, warnings = read_friction(input_dir)

    assert warnings == []
    by_branch = {item.branch_id: item for item in roughness}
    assert "7262" in by_branch
    assert by_branch["7262"].friction_type == "Chezy"
    assert by_branch["7262"].value > 40.0


def test_read_initial_conditions_extracts_flin_levels() -> None:
    input_dir = Path(__file__).resolve().parents[1] / "data" / "sre_simulation"

    initial_conditions, warnings = read_initial_conditions(input_dir)

    assert warnings == []
    assert initial_conditions
    by_branch = {item.branch_id: item for item in initial_conditions}
    assert "7262" in by_branch
    assert by_branch["7262"].water_level > 0.0


def test_read_morphodynamics_summary_detects_source_signals() -> None:
    input_dir = Path(__file__).resolve().parents[1] / "data" / "sre_simulation"

    summary, warnings = read_morphodynamics_summary(input_dir)

    assert warnings == []
    assert summary.has_morphology_switch is True
    assert summary.branch_count_with_grainsize > 0
    assert summary.representative_d50_m is not None
    assert summary.representative_d50_m > 0.0
    assert summary.grain_size_sample_count > 0
    assert len(summary.sediment_fractions_d50_m) == 5
    assert all(value > 0.0 for value in summary.sediment_fractions_d50_m)
    assert summary.branch_composition
    assert summary.underlayer_count == 20
    assert summary.underlayer_thickness_m == 0.5
    assert dict(summary.sediment_parameters) == {
        "ALLUVIAL": "0.2",
        "KINVIS": "0.000001",
        "PACFAC": "0.30",
        "RELDEN": "1.65",
    }
    assert dict(summary.morphology_parameters)["METHOD"] == "PROPORTIONAL"
    assert dict(summary.graded_sediment_options) == {
        "HEIOPT": "GILL",
        "LATHIC": "INITIAL",
        "LAYERS": "1",
        "LENOPT": "YALIN",
        "NUNLAY": "20",
        "ROUOPT": "WHITE",
    }
    assert dict(summary.graded_sediment_parameters)["ZBEPS"] == "0.05"
    assert summary.graded_sediment_flags == ("NONNGP",)
    assert len(summary.transport_parameters) == 7
    first_transport = summary.transport_parameters[0]
    assert first_transport.branch_id == "453"
    assert first_transport.formula_type == 1
    assert first_transport.calibration_factor == 0.7
    assert ("E1", 0.4) in first_transport.coefficients
    assert len(summary.layer_composition) == 1084
    assert len(summary.layer_composition[0].layer_weights) == 20
    first_branch, first_weights = summary.branch_composition[0]
    assert first_branch
    assert len(first_weights) == len(summary.sediment_fractions_d50_m)
    assert abs(sum(first_weights) - 1.0) < 1e-6
