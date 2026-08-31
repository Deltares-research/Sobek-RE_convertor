from __future__ import annotations

from pathlib import Path

import netCDF4
import numpy as np
from hydrolib.core.dflowfm.net.models import Branch as HydroBranch
from hydrolib.core.dflowfm.net.models import Network

from ...models import NetworkModel


def write_network_netcdf(network: NetworkModel, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)

    node_by_id = {node.id: node for node in network.nodes}
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
            name=branch.id,
            long_name=branch.name or branch.id,
            force_midpoint=False,
        )

    hydro_network.to_file(target_path)
    _ensure_quickplot_metadata(target_path)


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
