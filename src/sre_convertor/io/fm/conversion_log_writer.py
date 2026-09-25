from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ...models import ConversionOptions, ConversionReport


_READ_STAGES = (
    ("read_sre_network", "DEFTOP.1 and DEFGRD.*", "Network model"),
    ("read_cross_sections", "DEFCRS.*", "Cross-section definitions and locations"),
    ("read_conditions", "DEFCND.*", "Boundary conditions and lateral discharges"),
    ("read_runtime_settings", "DEFRUN.*", "Runtime settings"),
    ("read_friction", "DEFFRC.*", "Branch roughness"),
    ("read_initial_conditions", "DEFICN.*", "Initial conditions"),
    ("read_morphodynamics_summary", "DEFICN.*, DEFSUB.*, GRAINP.TXT", "Morphodynamics summary"),
    ("read_structures", "DEFSTR.*", "Structures"),
    ("read_sre_rtc", "DEFSTR.*", "RTC controllers and triggers"),
)


def write_conversion_log(
    output_path: Path,
    input_dir: Path,
    options: ConversionOptions,
    report: ConversionReport,
    *,
    network_only: bool,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    input_files = sorted(path for path in input_dir.rglob("*") if path.is_file())
    output_files = [path for path in report.files_created if path != output_path]

    lines = [
        "SRE to D-Flow FM conversion log",
        "=" * 36,
        f"Status: SUCCESS (conversion completed at {datetime.now(timezone.utc).isoformat()})",
        f"Input directory: {input_dir}",
        f"Output directory: {report.output_dir}",
        f"Model name: {report.model_name}",
        "",
        "Conversion flags and options",
        "---------------------------",
        f"model_name = {options.model_name}",
        f"network_only = {options.network_only}",
        f"activate_cross_sections = {options.activate_cross_sections}",
        f"test_duration_seconds = {options.test_duration_seconds}",
        f"activate_morphodynamics = {options.activate_morphodynamics}",
        f"activate_rtc = {options.activate_rtc}",
        f"rtc_source_dir = {options.rtc_source_dir}",
        "",
        "Input files discovered",
        "---------------------",
        f"{len(input_files)} input file(s) found under {input_dir}.",
    ]
    lines.extend(f"- {path.relative_to(input_dir)}" for path in input_files)

    lines.extend(
        [
            "",
            "Conversion stages",
            "-----------------",
        ]
    )
    if network_only:
        lines.append("- read_sre_network: DEFTOP.1 and DEFGRD.* -> network model")
        lines.append("- write_network_netcdf: network model -> dflowfm/<model>_net.nc")
        lines.append("- write_mdu: network model -> dflowfm/<model>.mdu")
        lines.append("- write_dimr_config: model configuration -> dimr_config.xml")
    else:
        for name, inputs, result in _READ_STAGES:
            lines.append(f"- {name}: {inputs} -> {result}")
        lines.extend(
            [
                "- write_network_netcdf: network model -> dflowfm/<model>_net.nc",
                "- write_boundary_conditions: boundaries -> dflowfm/BoundaryConditions.bc",
                "- write_external_forcing_file: boundaries/laterals -> dflowfm/<model>.ext",
                "- write_lateral_bc_files: laterals -> dflowfm/lateral_*.bc (when present)",
                "- write_cross_section_* : cross sections -> dflowfm/CrossSection*.ini (when active)",
                "- write_structures: valid structures -> dflowfm/Structures.ini (when present)",
                "- write_roughness: friction data -> dflowfm/roughness-Main.ini",
                "- write_initial_*: initial conditions -> dflowfm/InitialWaterDepth.ini and initialFields.ini",
                "- write_morphodynamics_files: morphology data -> dflowfm/mor.mor and related files (when active)",
                "- copy/write RTC package: RTC data -> rtc/* (when active and available)",
                "- write_mdu: converted model settings -> dflowfm/<model>.mdu",
                "- write_dimr_config: FM/RTC configuration -> dimr_config.xml",
                "- write_run_dimr_bat: run configuration -> run_dimr.bat",
            ]
        )

    lines.extend(
        [
            "",
            "Output files created",
            "--------------------",
            f"{len(output_files)} output file(s) created by the conversion.",
        ]
    )
    lines.extend(f"- {path.relative_to(report.output_dir)}" for path in output_files)

    lines.extend(
        [
            "",
            "Conversion summary",
            "------------------",
            f"Network nodes: {report.nodes_count}",
            f"Network branches: {report.branches_count}",
            f"Output files: {len(output_files)}",
            f"Warnings: {len(report.warnings)}",
        ]
    )
    if report.warnings:
        lines.append("Warnings:")
        lines.extend(f"- {warning}" for warning in report.warnings)
    else:
        lines.append("Warnings: none")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path
