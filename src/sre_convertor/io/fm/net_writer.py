from __future__ import annotations

from pathlib import Path

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
        hydro_branch = HydroBranch(
            geometry=geometry,
            branch_offsets=np.array([0.0, branch.length], dtype=np.float64),
        )
        hydro_network.mesh1d_add_branch(
            hydro_branch,
            name=branch.id,
            long_name=branch.name or branch.id,
            force_midpoint=False,
        )

    hydro_network.to_file(target_path)
