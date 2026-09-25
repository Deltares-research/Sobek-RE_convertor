from __future__ import annotations

from pathlib import Path

from .io.fm.boundary_writer import (
    write_boundary_conditions,
    write_external_forcing_file,
    write_lateral_bc_files,
)
from .io.fm.cross_section_writer import (
    write_cross_section_definitions,
    write_cross_section_locations,
)
from .io.fm.cross_section_interpolator import densify_cross_sections_for_grid
from .io.fm.conversion_log_writer import write_conversion_log
from .io.fm.dimr_writer import write_dimr_config
from .io.fm.initial_field_writer import (
    write_initial_water_depth,
    write_initial_fields_reference,
)
from .io.fm.mdu_writer import write_mdu
from .io.fm.morphodynamics_writer import write_morphodynamics_files
from .io.fm.net_writer import write_network_netcdf
from .io.fm.names import branch_names
from .io.fm.plot_writer import write_conversion_plots
from .io.fm.roughness_writer import write_roughness
from .io.fm.run_writer import write_run_dimr_bat
from .io.fm.rtc_writer import RtcCoupling, copy_rtc_package, write_native_rtc_package, write_sre_rtc_inventory
from .io.fm.structure_writer import write_structures
from .io.sre.condition_reader import read_conditions
from .io.sre.cross_section_reader import read_cross_sections
from .io.sre.friction_reader import read_friction
from .io.sre.initial_conditions_reader import read_initial_conditions
from .io.sre.input_diagnostics import collect_input_diagnostics
from .io.sre.value_diagnostics import collect_value_read_details
from .io.sre.morphodynamics_reader import read_morphodynamics_summary
from .io.sre.network_reader import read_sre_network
from .io.sre.runtime_reader import read_runtime_settings
from .io.sre.rtc_reader import read_sre_rtc
from .io.sre.structure_reader import read_structures
from .models import BoundaryCondition, ConversionOptions, ConversionReport, CrossSectionLocation, NetworkModel, SreCaseModel


def _validate_network(network: NetworkModel) -> list[str]:
    node_ids = {node.id for node in network.nodes}
    warnings: list[str] = []

    if len(node_ids) != len(network.nodes):
        warnings.append("Duplicate NODE ids detected in source network.")

    branch_ids = [branch.id for branch in network.branches]
    if len(set(branch_ids)) != len(branch_ids):
        warnings.append("Duplicate BRCH ids detected in source network.")

    for branch in network.branches:
        if branch.from_node_id not in node_ids or branch.to_node_id not in node_ids:
            raise ValueError(
                f"Branch {branch.id} references unknown nodes: "
                f"{branch.from_node_id}->{branch.to_node_id}."
            )
        if branch.length < 0:
            raise ValueError(f"Branch {branch.id} has a negative length.")

    return warnings


def convert_network_case(
    input_dir: Path,
    output_dir: Path,
    options: ConversionOptions,
) -> ConversionReport:
    if options.network_only:
        return _convert_network_only(input_dir, output_dir, options)

    case_model, read_warnings = _read_sre_case(input_dir, options)

    warnings = list(read_warnings)
    warnings.extend(_validate_network(case_model.network))

    dflowfm_dir = output_dir / "dflowfm"
    dflowfm_dir.mkdir(parents=True, exist_ok=True)

    net_filename = f"{options.model_name}_net.nc"
    mdu_filename = f"{options.model_name}.mdu"
    ext_filename = f"{options.model_name}.ext"

    created_files: list[Path] = []

    write_network_netcdf(case_model.network, dflowfm_dir / net_filename)
    created_files.append(dflowfm_dir / net_filename)

    boundaries_for_fm, boundary_mapping_warnings = _map_boundaries_to_fm_node_ids(
        case_model.boundaries,
        case_model.network,
    )
    warnings.extend(boundary_mapping_warnings)

    cross_def_name = None
    cross_loc_name = None
    cross_locs_fm: tuple[CrossSectionLocation, ...] | None = None
    if case_model.cross_section_definitions and case_model.cross_section_locations:
        # For morphodynamics, create unique definitions per location to avoid FM errors.
        create_unique = options.activate_morphodynamics
        cross_defs_fm, cross_locs_fm, cross_interp_warnings = densify_cross_sections_for_grid(
            case_model.network,
            case_model.cross_section_definitions,
            case_model.cross_section_locations,
            create_unique_definitions=create_unique,
        )
        warnings.extend(cross_interp_warnings)
        cross_def_name = "CrossSectionDefinitions.ini"
        cross_loc_name = "CrossSectionLocations.ini"
        write_cross_section_definitions(
            cross_defs_fm,
            dflowfm_dir / cross_def_name,
        )
        write_cross_section_locations(
            cross_locs_fm,
            dflowfm_dir / cross_loc_name,
            branch_names=branch_names(case_model.network),
        )
        created_files.extend([dflowfm_dir / cross_def_name, dflowfm_dir / cross_loc_name])

    # Keep default behavior guarded for stability; activate explicitly when requested.
    if not options.activate_cross_sections:
        cross_def_name = None
        cross_loc_name = None

    boundary_file_name = "BoundaryConditions.bc"
    write_boundary_conditions(boundaries_for_fm, case_model.runtime, dflowfm_dir / boundary_file_name)
    created_files.append(dflowfm_dir / boundary_file_name)

    write_external_forcing_file(
        boundaries_for_fm,
        case_model.laterals,
        dflowfm_dir / ext_filename,
        data_path_prefix="",
        branch_names=branch_names(case_model.network),
    )
    created_files.append(dflowfm_dir / ext_filename)

    created_files.extend(write_lateral_bc_files(case_model.laterals, case_model.runtime, dflowfm_dir))

    structure_file_name = None
    valid_structures = tuple(structure for structure in case_model.structures if structure.branch_id)
    skipped_structures = len(case_model.structures) - len(valid_structures)
    if skipped_structures:
        warnings.append(
            f"Skipped {skipped_structures} structures without branchId because they are invalid for FM StructureFile."
        )

    if valid_structures:
        structure_file_name = "Structures.ini"
        write_structures(
            valid_structures,
            dflowfm_dir / structure_file_name,
            branch_names=branch_names(case_model.network),
        )
        created_files.append(dflowfm_dir / structure_file_name)

    roughness_file_name = "roughness-Main.ini"
    write_roughness(case_model.network, case_model.roughness, dflowfm_dir / roughness_file_name)
    created_files.append(dflowfm_dir / roughness_file_name)

    initial_water_depth_name = "InitialWaterDepth.ini"
    write_initial_water_depth(
        dflowfm_dir / initial_water_depth_name,
        case_model.initial_conditions,
    )
    created_files.append(dflowfm_dir / initial_water_depth_name)

    initial_fields_name = "initialFields.ini"
    write_initial_fields_reference(dflowfm_dir / initial_fields_name, initial_water_depth_name)
    created_files.append(dflowfm_dir / initial_fields_name)

    include_morphology = False
    if options.activate_morphodynamics:
        if case_model.morphodynamics.has_morphology_switch:
            mor_file, sed_file, composition_file, bed_comp_file = write_morphodynamics_files(
                dflowfm_dir,
                case_model.morphodynamics,
                network=case_model.network,
                cross_section_locations=cross_locs_fm,
            )
            created_files.extend([mor_file, sed_file, composition_file, bed_comp_file])
            include_morphology = True
        else:
            warnings.append(
                "activate_morphodynamics=True requested, but no active morphology switch was found in DEFSUB.*."
            )

    include_rtc = False
    rtc_coupling: RtcCoupling | None = None
    observation_file_name = None
    if options.activate_rtc:
        rtc_source_dir = options.rtc_source_dir or input_dir / "rtc"
        if rtc_source_dir.is_dir():
            rtc_dir, rtc_coupling = copy_rtc_package(rtc_source_dir, output_dir / "rtc")
            created_files.extend(path for path in rtc_dir.rglob("*") if path.is_file())
            include_rtc = True
        else:
            warnings.append(f"activate_rtc=True requested, but no RTC package was found at {rtc_source_dir}.")
            if case_model.rtc.controllers or case_model.rtc.triggers:
                inventory_path = write_sre_rtc_inventory(output_dir / "rtc_sre_inventory.json", case_model.rtc)
                created_files.append(inventory_path)
                rtc_dir, rtc_coupling, observation_path, native_rtc_warnings = write_native_rtc_package(
                    output_dir / "rtc",
                    case_model.rtc,
                    case_model.runtime,
                    branch_names=branch_names(case_model.network),
                )
                created_files.extend(path for path in rtc_dir.rglob("*") if path.is_file())
                if observation_path is not None:
                    observation_file_name = observation_path.name
                    created_files.append(observation_path)
                warnings.extend(native_rtc_warnings)
                warnings.append(
                    "Native SRE RTC CNTL/TRGR records were synthesized into an RTC package; "
                    "PID/trigger parity is approximate and should be reviewed against SOBEK behavior."
                )
                include_rtc = True

    write_mdu(
        dflowfm_dir / mdu_filename,
        model_name=options.model_name,
        net_file_name=net_filename,
        ext_file_name=ext_filename,
        cross_loc_file_name=cross_loc_name,
        cross_def_file_name=cross_def_name,
        structure_file_name=structure_file_name,
        roughness_file_names=(roughness_file_name,),
        ini_field_file_name=initial_fields_name,
        runtime=case_model.runtime,
        observation_file_name=observation_file_name,
        include_morphology=include_morphology,
    )
    created_files.append(dflowfm_dir / mdu_filename)

    write_dimr_config(
        output_dir / "dimr_config.xml",
        mdu_filename,
        include_rtc=include_rtc,
        rtc_coupling=rtc_coupling,
        start_time=case_model.runtime.tstart_seconds,
        stop_time=case_model.runtime.tstop_seconds,
    )
    created_files.append(output_dir / "dimr_config.xml")

    created_files.append(write_run_dimr_bat(output_dir))

    report = ConversionReport(
        input_dir=input_dir,
        output_dir=output_dir,
        model_name=options.model_name,
        nodes_count=len(case_model.network.nodes),
        branches_count=len(case_model.network.branches),
        files_created=created_files,
        warnings=warnings,
        network_diagnostics=case_model.network.diagnostics,
        input_diagnostics=collect_input_diagnostics(input_dir),
        value_read_details=collect_value_read_details(input_dir, case_model),
    )
    if options.create_plots:
        report.files_created.extend(
            write_conversion_plots(
                output_dir / "fig",
                case_model.network,
                boundaries=case_model.boundaries,
                laterals=case_model.laterals,
                sediment_fractions=case_model.morphodynamics.sediment_fractions_d50_m,
                branch_composition=case_model.morphodynamics.branch_composition,
                layer_composition=case_model.morphodynamics.layer_composition,
                layer_count=case_model.morphodynamics.underlayer_count,
                initial_conditions=case_model.initial_conditions,
                roughness=case_model.roughness,
            )
        )
    log_path = write_conversion_log(
        output_dir / "conversion.log",
        input_dir,
        options,
        report,
        network_only=False,
    )
    report.files_created.append(log_path)
    return report


def _convert_network_only(
    input_dir: Path,
    output_dir: Path,
    options: ConversionOptions,
) -> ConversionReport:
    network = read_sre_network(input_dir)
    warnings = _validate_network(network)

    dflowfm_dir = output_dir / "dflowfm"
    dflowfm_dir.mkdir(parents=True, exist_ok=True)

    net_filename = f"{options.model_name}_net.nc"
    mdu_filename = f"{options.model_name}.mdu"

    write_network_netcdf(network, dflowfm_dir / net_filename)
    from datetime import datetime

    from .models import RuntimeSettings

    write_mdu(
        dflowfm_dir / mdu_filename,
        model_name=options.model_name,
        net_file_name=net_filename,
        ext_file_name="",
        cross_loc_file_name=None,
        cross_def_file_name=None,
        structure_file_name=None,
        roughness_file_names=tuple(),
        ini_field_file_name=None,
        runtime=RuntimeSettings(refdate=datetime(2000, 1, 1), tstart_seconds=0, tstop_seconds=86400),
    )
    write_dimr_config(output_dir / "dimr_config.xml", mdu_filename)

    report = ConversionReport(
        input_dir=input_dir,
        output_dir=output_dir,
        model_name=options.model_name,
        nodes_count=len(network.nodes),
        branches_count=len(network.branches),
        files_created=[dflowfm_dir / net_filename, dflowfm_dir / mdu_filename, output_dir / "dimr_config.xml"],
        warnings=warnings,
        network_diagnostics=network.diagnostics,
        input_diagnostics=collect_input_diagnostics(input_dir),
    )
    if options.create_plots:
        report.files_created.extend(write_conversion_plots(output_dir / "fig", network))
    log_path = write_conversion_log(
        output_dir / "conversion.log",
        input_dir,
        options,
        report,
        network_only=True,
    )
    report.files_created.append(log_path)
    return report


def _read_sre_case(input_dir: Path, options: ConversionOptions) -> tuple[SreCaseModel, list[str]]:
    warnings: list[str] = []

    network = read_sre_network(input_dir)

    cross_defs, cross_locs, cross_warnings = read_cross_sections(input_dir)
    warnings.extend(cross_warnings)

    boundaries, laterals, cnd_warnings = read_conditions(input_dir, network)
    warnings.extend(cnd_warnings)

    runtime, run_warnings = read_runtime_settings(
        input_dir,
        test_duration_seconds=options.test_duration_seconds,
    )
    warnings.extend(run_warnings)

    roughness, roughness_warnings = read_friction(input_dir)
    warnings.extend(roughness_warnings)

    initial_conditions, initial_condition_warnings = read_initial_conditions(input_dir)
    warnings.extend(initial_condition_warnings)

    morphodynamics, morphodynamics_warnings = read_morphodynamics_summary(input_dir)
    warnings.extend(morphodynamics_warnings)

    structures, structure_warnings = read_structures(input_dir)
    warnings.extend(structure_warnings)

    rtc, rtc_warnings = read_sre_rtc(input_dir)
    warnings.extend(rtc_warnings)

    return (
        SreCaseModel(
            network=network,
            cross_section_definitions=cross_defs,
            cross_section_locations=cross_locs,
            boundaries=boundaries,
            laterals=laterals,
            structures=structures,
            runtime=runtime,
            roughness=roughness,
            initial_conditions=initial_conditions,
            morphodynamics=morphodynamics,
            rtc=rtc,
        ),
        warnings,
    )


def _map_boundaries_to_fm_node_ids(
    boundaries: tuple[BoundaryCondition, ...],
    network: NetworkModel,
) -> tuple[tuple[BoundaryCondition, ...], list[str]]:
    node_by_id = {node.id: node for node in network.nodes}
    node_degree: dict[str, int] = {node.id: 0 for node in network.nodes}
    for branch in network.branches:
        if branch.from_node_id in node_degree:
            node_degree[branch.from_node_id] += 1
        if branch.to_node_id in node_degree:
            node_degree[branch.to_node_id] += 1

    mapped: list[BoundaryCondition] = []
    warnings: list[str] = []

    for boundary in boundaries:
        node = node_by_id.get(boundary.node_id)
        if node is None:
            warnings.append(f"Boundary {boundary.id} references unknown node {boundary.node_id}; keeping original nodeId.")
            mapped.append(boundary)
            continue

        if node_degree.get(boundary.node_id, 0) > 1:
            warnings.append(
                f"Boundary {boundary.id} at node {boundary.node_id} skipped because it is a bifurcation node in FM."
            )
            continue

        fm_node_id = node.name or node.id
        mapped.append(
            BoundaryCondition(
                id=boundary.id,
                name=boundary.name,
                node_id=fm_node_id,
                node_name=node.name or node.id,
                quantity=boundary.quantity,
                series=boundary.series,
            )
        )

    return tuple(mapped), warnings


def _format_fm_network_node_id(x: float, y: float) -> str:
    if abs(x) < 5e-7:
        x = 0.0
    if abs(y) < 5e-7:
        y = 0.0
    return f"{x:.6f}_{y:.6f}"
