from pathlib import Path

from sre_convertor import audit_structure_parameter_warnings


def test_audit_structure_warnings_summarizes_adjustments(tmp_path: Path) -> None:
    dflowfm_dir = tmp_path / "dflowfm"
    dflowfm_dir.mkdir(parents=True)

    dia_path = dflowfm_dir / "demo.dia"
    dia_path.write_text(
        "\n".join(
            [
                "** WARNING: The crest width for 'ST_73330' is changed from   790.00 into   105.49.",
                "Dimr [2026-08-31 09:53:47.705] #0 >> kernel: The crest width for 'ST_73330' is changed from   790.00 into   105.49.",
                "** WARNING: The crest width for 'ST_73330' is changed from   790.00 into   105.49.",
                "** WARNING: The gate opening width for 'ST_73330' is changed from   790.00 into   105.49.",
                "** WARNING: The crest width for 'ST_78759' is changed from   600.00 into   146.06.",
            ]
        ),
        encoding="utf-8",
    )

    result = audit_structure_parameter_warnings(tmp_path, model_name="demo")

    assert result.success is True
    assert result.dia_file == dia_path
    assert result.total_events == 4
    assert len(result.summaries) == 3

    by_key = {
        (item.structure_id, item.parameter, item.from_value, item.to_value): item.count for item in result.summaries
    }
    assert by_key[("ST_73330", "crest width", 790.0, 105.49)] == 2
    assert by_key[("ST_73330", "gate opening width", 790.0, 105.49)] == 1
    assert by_key[("ST_78759", "crest width", 600.0, 146.06)] == 1


def test_audit_structure_warnings_returns_failure_when_missing_dia(tmp_path: Path) -> None:
    (tmp_path / "dflowfm").mkdir(parents=True)

    result = audit_structure_parameter_warnings(tmp_path, model_name="demo")

    assert result.success is False
    assert result.dia_file is None
    assert result.total_events == 0
    assert result.summaries == ()
