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


def _relative_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _network_read_lines(report: ConversionReport) -> list[str]:
    diagnostics = report.network_diagnostics
    lines = ["Network input read details", "--------------------------"]
    lines.append(f"DEFTOP source records: {len(diagnostics.topology_node_lines) + len(diagnostics.topology_branch_lines)}")
    lines.extend(f"- DEFTOP line {line}: NODE {node_id}" for node_id, line in diagnostics.topology_node_lines)
    lines.extend(f"- DEFTOP line {line}: BRCH {branch_id}" for branch_id, line in diagnostics.topology_branch_lines)

    grid_points = 0
    grid_edges = 0
    branch_by_id = {
        branch_id: (from_node_id, to_node_id, length, chainages)
        for branch_id, from_node_id, to_node_id, length, chainages in diagnostics.branch_connectivity
    }
    for filename, start, end, branch_id, chainages in diagnostics.grid_records:
        branch = branch_by_id.get(branch_id)
        point_count = len(chainages)
        if branch is not None:
            point_count = len(_grid_offsets(chainages, branch[2]))
        grid_points += point_count
        grid_edges += max(point_count - 1, 0)
        lines.append(
            f"- {filename} lines {start}-{end}: GRID branch {branch_id}; "
            f"chainages={', '.join(_format_number(value) for value in chainages)}; "
            f"grid points={point_count}; grid edges={max(point_count - 1, 0)}"
        )
    lines.append(f"Source network nodes: {len(diagnostics.topology_node_lines)}")
    lines.append(f"Generated grid points: {grid_points}")
    lines.append(f"Generated grid edges: {grid_edges}")
    lines.append("Grid connectivity:")
    for branch_id, from_node_id, to_node_id, length, chainages in diagnostics.branch_connectivity:
        point_count = len(_grid_offsets(chainages, length))
        lines.append(
            f"- branch {branch_id}: {from_node_id} -> {to_node_id}; "
            f"points={point_count}; edges={max(point_count - 1, 0)}"
        )
    return lines


def _input_read_lines(report: ConversionReport) -> list[str]:
    lines = ["All input file read details", "---------------------------"]
    for diagnostic in report.input_diagnostics:
        relative_path = diagnostic.source_file.as_posix()
        lines.append(f"- {relative_path}: read {diagnostic.line_count} line(s)")
        for key, start, end in diagnostic.records:
            lines.append(f"  - {relative_path} lines {start}-{end}: read {key} record")
    return lines


def _value_read_lines(report: ConversionReport) -> list[str]:
    return ["Parsed values read", "------------------", *[f"- {detail}" for detail in report.value_read_details]]


def _format_number(value: float) -> str:
    return f"{value:g}"


def _grid_offsets(chainages: tuple[float, ...], branch_length: float) -> tuple[float, ...]:
    offsets = [value for value in chainages if 0.0 <= value <= branch_length]
    if not offsets or offsets[0] != 0.0:
        offsets.insert(0, 0.0)
    if offsets[-1] != branch_length:
        offsets.append(branch_length)
    return tuple(sorted(set(offsets)))


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
        f"create_plots = {options.create_plots}",
        f"activate_morphodynamics = {options.activate_morphodynamics}",
        f"activate_rtc = {options.activate_rtc}",
        f"rtc_source_dir = {options.rtc_source_dir}",
        "",
        "Input files discovered",
        "---------------------",
        f"{len(input_files)} input file(s) found under {input_dir}.",
    ]
    lines.extend(f"- {_relative_path(path, input_dir)}" for path in input_files)

    lines.extend(
        [
            "",
            *_input_read_lines(report),
            "",
            *_value_read_lines(report),
            "",
            *_network_read_lines(report),
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
    lines.extend(f"- {_relative_path(path, report.output_dir)}" for path in output_files)

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
