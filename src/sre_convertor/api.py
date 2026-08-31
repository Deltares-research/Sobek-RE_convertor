from __future__ import annotations

from pathlib import Path

from .io.fm.structure_warning_audit import StructureWarningAuditResult, audit_structure_warnings
from .io.fm.runtime_validation import RuntimeValidationResult, run_and_validate_output, validate_dia_success
from .models import ConversionOptions, ConversionReport
from .orchestrator import convert_network_case


def convert_network(
    input_dir: str | Path,
    output_dir: str | Path,
    model_name: str = "sre2fm_network",
    test_duration_seconds: int = 7200,
) -> ConversionReport:
    """Convert only the SRE network into a minimal FM schematization."""
    options = ConversionOptions(
        model_name=model_name,
        network_only=True,
        test_duration_seconds=test_duration_seconds,
    )
    return convert_network_case(Path(input_dir), Path(output_dir), options)


def convert_case(
    input_dir: str | Path,
    output_dir: str | Path,
    model_name: str = "sre2fm_case",
    activate_cross_sections: bool = True,
    test_duration_seconds: int = 7200,
    activate_morphodynamics: bool = False,
) -> ConversionReport:
    """Convert an SRE case to a runnable FM schematization with supporting files."""
    options = ConversionOptions(
        model_name=model_name,
        network_only=False,
        activate_cross_sections=activate_cross_sections,
        test_duration_seconds=test_duration_seconds,
        activate_morphodynamics=activate_morphodynamics,
    )
    return convert_network_case(Path(input_dir), Path(output_dir), options)


def validate_conversion_success(
    output_dir: str | Path,
    model_name: str | None = None,
) -> RuntimeValidationResult:
    """Validate conversion success based on the expected marker in the FM .dia file."""
    return validate_dia_success(Path(output_dir), model_name=model_name)


def run_and_validate_conversion(
    output_dir: str | Path,
    model_name: str | None = None,
    timeout_seconds: int = 900,
) -> RuntimeValidationResult:
    """Run output/run_dimr.bat and validate success marker in the FM .dia file."""
    return run_and_validate_output(
        Path(output_dir),
        model_name=model_name,
        timeout_seconds=timeout_seconds,
    )


def audit_structure_parameter_warnings(
    output_dir: str | Path,
    model_name: str | None = None,
) -> StructureWarningAuditResult:
    """Summarize FM structure parameter auto-adjustment warnings from the latest .dia file."""
    return audit_structure_warnings(Path(output_dir), model_name=model_name)
