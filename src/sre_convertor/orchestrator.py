from __future__ import annotations

from pathlib import Path

from .io.fm.dimr_writer import write_dimr_config
from .io.fm.mdu_writer import write_mdu
from .io.fm.net_writer import write_network_netcdf
from .io.sre.network_reader import read_sre_network
from .models import ConversionOptions, ConversionReport, NetworkModel


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
    network = read_sre_network(input_dir)
    warnings = _validate_network(network)

    dflowfm_dir = output_dir / "dflowfm"
    dflowfm_dir.mkdir(parents=True, exist_ok=True)

    net_filename = f"{options.model_name}_net.nc"
    mdu_filename = f"{options.model_name}.mdu"

    write_network_netcdf(network, dflowfm_dir / net_filename)
    write_mdu(dflowfm_dir / mdu_filename, net_filename)
    write_dimr_config(output_dir / "dimr_config.xml", f"dflowfm/{mdu_filename}")

    return ConversionReport(
        input_dir=input_dir,
        output_dir=output_dir,
        model_name=options.model_name,
        nodes_count=len(network.nodes),
        branches_count=len(network.branches),
        warnings=warnings,
    )
