from __future__ import annotations

from ...models import NetworkModel


def branch_names(network: NetworkModel) -> dict[str, str]:
    return {branch.id: (branch.name or branch.id) for branch in network.branches}