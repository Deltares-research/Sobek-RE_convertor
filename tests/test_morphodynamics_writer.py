from pathlib import Path

from sre_convertor.io.fm.morphodynamics_writer import write_morphodynamics_files
from sre_convertor.models import MorphodynamicsSummary


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
    assert sed_text.count("[Sediment]") == 3
    assert "SedDia           = 8.0000000e-04" in sed_text
    assert "SedDia           = 1.7000000e-03" in sed_text
    assert "SedDia           = 3.4000000e-03" in sed_text

    composition_text = composition_path.read_text(encoding="utf-8")
    assert "[BedCompositionFileInformation]" in composition_text
    assert "[Layer]" in composition_text
    assert "Type = volume fraction" in composition_text
    # Should have Thick and Fraction references when no spatial data provided
    # (falls back to per-branch format in bed_comp_path instead)

    bed_comp_text = bed_comp_path.read_text(encoding="utf-8")
    assert "[BedCompositionFileInformation]" in bed_comp_text
    assert "Type = volume fraction" in bed_comp_text
