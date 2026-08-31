from pathlib import Path

from sre_convertor.io.fm.morphodynamics_writer import write_morphodynamics_files
from sre_convertor.models import MorphodynamicsSummary


def test_write_morphodynamics_files_writes_mor_and_sed(tmp_path: Path) -> None:
    summary = MorphodynamicsSummary(
        branch_count_with_grainsize=3,
        has_morphology_switch=True,
        representative_d50_m=0.0017,
    )

    mor_path, sed_path = write_morphodynamics_files(tmp_path, summary)

    assert mor_path.exists()
    assert sed_path.exists()

    mor_text = mor_path.read_text(encoding="utf-8")
    sed_text = sed_path.read_text(encoding="utf-8")

    assert "[Morphology]" in mor_text
    assert "[Sediment]" in sed_text
    assert "SedDia           = 1.7000000e-03" in sed_text
