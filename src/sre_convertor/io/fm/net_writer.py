from __future__ import annotations

import os
from pathlib import Path
from tempfile import NamedTemporaryFile

import netCDF4
import numpy as np
from hydrolib.core.dflowfm.net.models import Branch as HydroBranch
from hydrolib.core.dflowfm.net.models import Network

from ...models import NetworkModel
from .names import branch_names


def write_network_netcdf(network: NetworkModel, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)

    node_by_id = {node.id: node for node in network.nodes}
    display_names = branch_names(network)
    hydro_network = Network()

    # Build 1D branch geometries from branch endpoints in deterministic order.
    for branch in network.branches:
        start = node_by_id[branch.from_node_id]
        end = node_by_id[branch.to_node_id]

        geometry = np.array(
            [[start.x, start.y], [end.x, end.y]],
            dtype=np.float64,
        )

        offsets = _branch_offsets(branch.grid_chainages, branch.length)
        hydro_branch = HydroBranch(
            geometry=geometry,
            branch_offsets=offsets,
        )
        hydro_network.mesh1d_add_branch(
            hydro_branch,
            name=display_names[branch.id],
            long_name=display_names[branch.id],
            force_midpoint=False,
        )

    hydro_network.to_file(target_path)
    _ensure_quickplot_metadata(target_path)
    _rewrite_legacy_network_schema(target_path)
    _write_sre_node_names(network, target_path)


def _branch_offsets(chainages: tuple[float, ...], branch_length: float) -> np.ndarray:
    if chainages:
        offsets = [value for value in chainages if 0.0 <= value <= branch_length]
        if not offsets or offsets[0] != 0.0:
            offsets.insert(0, 0.0)
        if offsets[-1] != branch_length:
            offsets.append(branch_length)
        return np.array(sorted(set(offsets)), dtype=np.float64)

    return np.array([0.0, branch_length], dtype=np.float64)


def _ensure_quickplot_metadata(target_path: Path) -> None:
    with netCDF4.Dataset(target_path, mode="a") as ds:
        conventions = getattr(ds, "Conventions", "")
        if "Deltares-0.10" not in conventions:
            if conventions:
                ds.Conventions = f"{conventions} Deltares-0.10"
            else:
                ds.Conventions = "CF-1.8 UGRID-1.0 Deltares-0.10"

        if "projected_coordinate_system" not in ds.variables:
            crs = ds.createVariable("projected_coordinate_system", "i4")
            crs.assignValue(0)
            crs.setncattr("projection_name", "Unknown projected")
            crs.setncattr("long_name", "Unknown projected")
            crs.setncattr("epsg", np.int32(0))
            crs.setncattr("grid_mapping_name", "Unknown projected")
            crs.setncattr("latitude_of_projection_origin", np.float64(0.0))
            crs.setncattr("longitude_of_prime_meridian", np.float64(0.0))
            crs.setncattr("semi_major_axis", np.float64(6378137.0))
            crs.setncattr("semi_minor_axis", np.float64(6356752.314245))
            crs.setncattr("inverse_flattening", np.float64(298.257223563))
            crs.setncattr("scale_factor_at_projection_origin", np.float64(0.0))
            crs.setncattr("false_easting", np.float64(0.0))
            crs.setncattr("false_northing", np.float64(0.0))
            crs.setncattr("EPSG_code", "EPSG:0")
            crs.setncattr("proj4_params", "")
            crs.setncattr("value", "value is equal to EPSG code")


def _write_sre_node_names(network: NetworkModel, target_path: Path) -> None:
    """Use SRE node names for the public IDs and labels of network nodes."""
    names_by_coordinates = {
        (node.x, node.y): node.name
        for node in network.nodes
        if node.name
    }
    if not names_by_coordinates:
        return

    with netCDF4.Dataset(target_path, mode="a") as ds:
        for id_name, long_name, x_name, y_name in (
            (
                "network1d_node_id",
                "network1d_node_long_name",
                "network1d_node_x",
                "network1d_node_y",
            ),
        ):
            if any(name not in ds.variables for name in (id_name, long_name, x_name, y_name)):
                continue
            id_variable = ds.variables[id_name]
            long_name_variable = ds.variables[long_name]
            id_width = id_variable.shape[1]
            long_name_width = long_name_variable.shape[1]
            for index, (x, y) in enumerate(zip(ds.variables[x_name][:], ds.variables[y_name][:])):
                name = names_by_coordinates.get((float(x), float(y)))
                if name:
                    id_variable[index, :] = np.array(list(name[:id_width].ljust(id_width)), dtype="S1")
                    long_name_variable[index, :] = np.array(
                        list(name[:long_name_width].ljust(long_name_width)),
                        dtype="S1",
                    )


def _rewrite_legacy_network_schema(target_path: Path) -> None:
    """Write the network file layout expected by legacy QUICKPLOT readers."""
    variable_order = (
        "projected_coordinate_system",
        "network1d",
        "network1d_node_id",
        "network1d_node_long_name",
        "network1d_node_x",
        "network1d_node_y",
        "network1d_branch_id",
        "network1d_branch_long_name",
        "network1d_edge_length",
        "network1d_branch_order",
        "network1d_edge_nodes",
        "network1d_geometry",
        "network1d_geom_node_count",
        "network1d_geom_x",
        "network1d_geom_y",
        "mesh1d",
        "mesh1d_node_id",
        "mesh1d_node_long_name",
        "mesh1d_edge_nodes",
        "mesh1d_node_branch",
        "mesh1d_node_offset",
        "mesh1d_edge_branch",
        "mesh1d_edge_offset",
    )
    dimension_order = (
        "network_nEdges",
        "network_nNodes",
        "network_nGeometryNodes",
        "network1d_nNodes",
        "network1d_nGeometryNodes",
        "network1d_nEdges",
        "idstrlength",
        "longstrlength",
        "mesh1d_nEdges",
        "mesh1d_nNodes",
        "Two",
    )
    dimension_names = {
        "idstrlength": "strLengthIds",
        "longstrlength": "strLengthLongNames",
    }

    with NamedTemporaryFile(dir=target_path.parent, suffix=".nc", delete=False) as temporary:
        temporary_path = Path(temporary.name)

    try:
        with netCDF4.Dataset(target_path, mode="r") as source, netCDF4.Dataset(
            temporary_path, mode="w", format="NETCDF3_CLASSIC"
        ) as destination:
            for name, value in source.__dict__.items():
                destination.setncattr(name, value)

            for name in dimension_order:
                if name.startswith("network_"):
                    source_name = {
                        "network_nEdges": "network1d_nEdges",
                        "network_nNodes": "network1d_nNodes",
                        "network_nGeometryNodes": "network1d_nGeometryNodes",
                    }[name]
                else:
                    source_name = name
                dimension = source.dimensions[source_name]
                destination.createDimension(dimension_names.get(name, name), len(dimension))

            for name in variable_order:
                variable = source.variables[name]
                dimensions = tuple(
                    dimension_names.get(dimension, dimension)
                    for dimension in variable.dimensions
                )
                fill_value = getattr(variable, "_FillValue", None)
                if fill_value is None:
                    copied = destination.createVariable(name, variable.datatype, dimensions)
                else:
                    copied = destination.createVariable(
                        name, variable.datatype, dimensions, fill_value=fill_value
                    )
                for attribute, value in variable.__dict__.items():
                    if attribute != "_FillValue":
                        copied.setncattr(attribute, value)
                copied[:] = variable[:]

            _write_plugin_compatibility_variables(source, destination, dimension_names)

        os.replace(temporary_path, target_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _write_plugin_compatibility_variables(source, destination, dimension_names: dict[str, str]) -> None:
    """Add the network schema consumed by the WeirImporter QGIS plugin."""
    def create(name: str, datatype: str, dimensions: tuple[str, ...], source_name: str | None = None):
        source_variable = source.variables[source_name or name]
        variable = destination.createVariable(name, datatype, dimensions)
        for attribute, value in source_variable.__dict__.items():
            if attribute != "_FillValue":
                variable.setncattr(attribute, value)
        return variable, source_variable

    network = destination.createVariable("network", "i4")
    network.assignValue(1)
    network.setncattr("cf_role", "mesh_topology")
    network.setncattr("long_name", "Topology data of 1D network")
    network.setncattr("edge_dimension", "network_nEdges")
    network.setncattr("edge_geometry", "network_geometry")
    network.setncattr("edge_node_connectivity", "network_edge_nodes")
    network.setncattr("node_coordinates", "network_node_x network_node_y")
    network.setncattr("node_dimension", "network_nNodes")
    network.setncattr("topology_dimension", np.int32(1))
    network.setncattr("node_id", "network_node_id")
    network.setncattr("node_long_name", "network_node_long_name")
    network.setncattr("branch_id", "network_branch_id")
    network.setncattr("branch_long_name", "network_branch_long_name")
    network.setncattr("edge_length", "network_edge_length")

    aliases = {
        "network_edge_nodes": ("i4", ("network_nEdges", "Two"), "network1d_edge_nodes"),
        "network_edge_length": ("f8", ("network_nEdges",), "network1d_edge_length"),
        "network_node_x": ("f8", ("network_nNodes",), "network1d_node_x"),
        "network_node_y": ("f8", ("network_nNodes",), "network1d_node_y"),
        "network_geom_node_count": ("i4", ("network_nEdges",), "network1d_geom_node_count"),
        "network_geom_x": ("f8", ("network_nGeometryNodes",), "network1d_geom_x"),
        "network_geom_y": ("f8", ("network_nGeometryNodes",), "network1d_geom_y"),
        "network_branch_order": ("i4", ("network_nEdges",), "network1d_branch_order"),
    }
    for name, (datatype, dimensions, source_name) in aliases.items():
        variable, source_variable = create(name, datatype, dimensions, source_name)
        variable[:] = source_variable[:]
    destination.variables["network_branch_order"].setncattr("mesh", "network")
    destination.variables["network_branch_order"].setncattr("location", "edge")
    destination.variables["network_edge_nodes"].setncattr("start_index", np.int32(0))
    destination.variables["network_edge_nodes"][:] = source.variables["network1d_edge_nodes"][:] - 1
    branch_type = destination.createVariable("network_branch_type", "i4", ("network_nEdges",))
    branch_type[:] = 0
    branch_type.setncattr("long_name", "Type of branches")
    branch_type.setncattr("mesh", "network")
    branch_type.setncattr("location", "edge")
    geometry = destination.createVariable("network_geometry", "i4")
    geometry.assignValue(1)
    geometry.setncattr("geometry_type", "line")
    geometry.setncattr("long_name", "1D Geometry")
    geometry.setncattr("node_count", "network_geom_node_count")
    geometry.setncattr("node_coordinates", "network_geom_x network_geom_y")

    for target, source_name, dimension in (
        ("network_branch_id", "network1d_branch_id", "network_nEdges"),
        ("network_branch_long_name", "network1d_branch_long_name", "network_nEdges"),
        ("network_node_id", "network1d_node_id", "network_nNodes"),
        ("network_node_long_name", "network1d_node_long_name", "network_nNodes"),
    ):
        variable, source_variable = create(
            target,
            "c",
            (dimension, dimension_names["idstrlength" if "long_name" not in target else "longstrlength"]),
            source_name,
        )
        variable[:] = source_variable[:]

    mesh = destination.variables["mesh1d"]
    mesh.setncattr("node_coordinates", "mesh1d_node_branch mesh1d_node_offset mesh1d_node_x mesh1d_node_y")
    mesh.setncattr("edge_coordinates", "mesh1d_edge_branch mesh1d_edge_offset mesh1d_edge_x mesh1d_edge_y")
    for name, source_name in (
        ("mesh1d_node_x", "mesh1d_node_x"),
        ("mesh1d_node_y", "mesh1d_node_y"),
        ("mesh1d_edge_x", "mesh1d_edge_x"),
        ("mesh1d_edge_y", "mesh1d_edge_y"),
    ):
        dimension = "mesh1d_nNodes" if "node" in name else "mesh1d_nEdges"
        variable, source_variable = create(name, "f8", (dimension,), source_name)
        variable[:] = source_variable[:]

    for name in ("mesh1d_edge_nodes", "mesh1d_edge_branch", "mesh1d_node_branch"):
        destination.variables[name].setncattr("start_index", np.int32(0))
        destination.variables[name][:] = source.variables[name][:] - 1
