from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess


SUCCESS_MARKER = "** INFO   : Done writing initial output to file(s)."


@dataclass(frozen=True)
class RuntimeValidationResult:
    success: bool
    message: str
    dia_file: Path | None = None


def validate_dia_success(output_dir: Path, model_name: str | None = None) -> RuntimeValidationResult:
    dflowfm_dir = output_dir / "dflowfm"
    if not dflowfm_dir.exists():
        return RuntimeValidationResult(
            success=False,
            message="Missing dflowfm directory in output.",
            dia_file=None,
        )

    dia_file = _select_dia_file(dflowfm_dir, model_name=model_name)
    if dia_file is None:
        return RuntimeValidationResult(
            success=False,
            message="No .dia file found in output/dflowfm.",
            dia_file=None,
        )

    text = dia_file.read_text(encoding="utf-8", errors="ignore")
    if SUCCESS_MARKER in text:
        return RuntimeValidationResult(
            success=True,
            message=f"Success marker found in {dia_file.name}.",
            dia_file=dia_file,
        )

    return RuntimeValidationResult(
        success=False,
        message=(
            "Success marker not found in dia file. "
            f"Expected line: {SUCCESS_MARKER}"
        ),
        dia_file=dia_file,
    )


def run_and_validate_output(
    output_dir: Path,
    model_name: str | None = None,
    timeout_seconds: int = 900,
) -> RuntimeValidationResult:
    run_script = output_dir / "run_dimr.bat"
    if not run_script.exists():
        return RuntimeValidationResult(
            success=False,
            message="Missing run_dimr.bat in output directory.",
            dia_file=None,
        )

    previous_dia = _select_dia_file(output_dir / "dflowfm", model_name=model_name)
    previous_mtime_ns = previous_dia.stat().st_mtime_ns if previous_dia and previous_dia.exists() else None

    try:
        completed = subprocess.run(
            [str(run_script)],
            cwd=str(output_dir),
            check=False,
            timeout=timeout_seconds,
            shell=True,
        )
    except subprocess.TimeoutExpired:
        return RuntimeValidationResult(
            success=False,
            message=f"run_dimr.bat timed out after {timeout_seconds} seconds.",
            dia_file=None,
        )

    result = validate_dia_success(output_dir, model_name=model_name)
    if result.dia_file is None:
        return result

    current_mtime_ns = result.dia_file.stat().st_mtime_ns
    if previous_dia is not None and result.dia_file.resolve() == previous_dia.resolve():
        if previous_mtime_ns is not None and current_mtime_ns <= previous_mtime_ns:
            return RuntimeValidationResult(
                success=False,
                message=(
                    "No fresh .dia update detected after running run_dimr.bat; "
                    "result may be from a previous run."
                ),
                dia_file=result.dia_file,
            )

    if completed.returncode != 0 and result.success:
        return RuntimeValidationResult(
            success=True,
            message=(
                f"Success marker found in {result.dia_file.name}, "
                f"but run_dimr.bat exited with code {completed.returncode}."
            ),
            dia_file=result.dia_file,
        )

    return result


def _select_dia_file(dflowfm_dir: Path, model_name: str | None) -> Path | None:
    dia_files = sorted(dflowfm_dir.glob("*.dia"))
    if not dia_files:
        dia_files = sorted(dflowfm_dir.glob("**/*.dia"))
    if not dia_files:
        return None

    if model_name:
        for candidate in dia_files:
            if candidate.name.lower() == f"{model_name}.dia".lower():
                return candidate

    return max(dia_files, key=lambda path: path.stat().st_mtime)
