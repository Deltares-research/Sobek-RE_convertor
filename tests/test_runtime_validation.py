from pathlib import Path
import subprocess

from sre_convertor import run_and_validate_conversion, validate_conversion_success


def test_validate_conversion_success_true_when_marker_present(tmp_path: Path) -> None:
    dflowfm_dir = tmp_path / "dflowfm"
    dflowfm_dir.mkdir(parents=True)

    dia_path = dflowfm_dir / "demo.dia"
    dia_path.write_text(
        "\n".join(
            [
                "line 1",
                "** INFO   : Done writing initial output to file(s).",
                "line 3",
            ]
        ),
        encoding="utf-8",
    )

    result = validate_conversion_success(tmp_path, model_name="demo")

    assert result.success is True
    assert result.dia_file == dia_path


def test_validate_conversion_success_false_when_marker_missing(tmp_path: Path) -> None:
    dflowfm_dir = tmp_path / "dflowfm"
    dflowfm_dir.mkdir(parents=True)

    dia_path = dflowfm_dir / "demo.dia"
    dia_path.write_text("No success marker here", encoding="utf-8")

    result = validate_conversion_success(tmp_path, model_name="demo")

    assert result.success is False
    assert result.dia_file == dia_path
    assert "Success marker not found" in result.message


def test_validate_conversion_success_finds_nested_dia(tmp_path: Path) -> None:
    nested = tmp_path / "dflowfm" / "DFM_OUTPUT_demo"
    nested.mkdir(parents=True)

    dia_path = nested / "demo.dia"
    dia_path.write_text(
        "** INFO   : Done writing initial output to file(s).",
        encoding="utf-8",
    )

    result = validate_conversion_success(tmp_path, model_name="demo")

    assert result.success is True
    assert result.dia_file == dia_path


def test_run_and_validate_conversion_detects_stale_dia(tmp_path: Path, monkeypatch) -> None:
    dflowfm_dir = tmp_path / "dflowfm"
    dflowfm_dir.mkdir(parents=True)

    dia_path = dflowfm_dir / "demo.dia"
    dia_path.write_text(
        "** INFO   : Done writing initial output to file(s).",
        encoding="utf-8",
    )

    run_script = tmp_path / "run_dimr.bat"
    run_script.write_text("@echo off\nexit /b 1\n", encoding="utf-8")

    def _fake_run(*_args, **_kwargs):
        return subprocess.CompletedProcess(args=["run_dimr.bat"], returncode=1)

    monkeypatch.setattr("sre_convertor.io.fm.runtime_validation.subprocess.run", _fake_run)

    result = run_and_validate_conversion(tmp_path, model_name="demo")

    assert result.success is False
    assert result.dia_file == dia_path
    assert "No fresh .dia update detected" in result.message
