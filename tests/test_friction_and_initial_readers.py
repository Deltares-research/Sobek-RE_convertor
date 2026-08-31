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
    assert len(summary.sediment_fractions_d50_m) >= 3
    assert all(value > 0.0 for value in summary.sediment_fractions_d50_m)
    assert summary.branch_composition
    first_branch, first_weights = summary.branch_composition[0]
    assert first_branch
    assert len(first_weights) == len(summary.sediment_fractions_d50_m)
    assert abs(sum(first_weights) - 1.0) < 1e-6
