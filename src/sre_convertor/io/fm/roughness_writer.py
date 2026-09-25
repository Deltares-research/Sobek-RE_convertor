from __future__ import annotations

from pathlib import Path

from ...models import BranchRoughness, NetworkModel
from .names import branch_names


def write_roughness(
    network: NetworkModel,
    roughness_by_branch: tuple[BranchRoughness, ...],
    target_path: Path,
) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)

    source_roughness = {item.branch_id: item for item in roughness_by_branch}
    display_names = branch_names(network)

    lines: list[str] = [
        "[General]",
        "    fileVersion           = 3.00",
        "    fileType              = roughness",
        "",
        "[Global]",
        "    frictionId            = #Main#",
        "    frictionType          = Manning",
        "    frictionValue         = 0.030",
        "",
    ]

    for branch in network.branches:
        roughness = source_roughness.get(branch.id)
        friction_type = "Manning"
        chainages = (0.0,)
        friction_values = (0.03,)
        if roughness is not None and roughness.friction_type.lower() == "chezy":
            friction_type = "Chezy"
            chainages = roughness.chainages
            friction_values = roughness.values

        lines.extend(
            [
                "[Branch]",
                f"    branchId              = #{display_names[branch.id]}#",
                f"    frictionType          = {friction_type}",
                "    functionType          = constant",
                f"    numLocations          = {len(chainages)}",
                f"    chainage              = {' '.join(f'{chainage:.3f}' for chainage in chainages)}",
                f"    frictionValues        = {' '.join(f'{value:.5f}' for value in friction_values)}",
                "",
            ]
        )

    target_path.write_text("\n".join(lines), encoding="utf-8")
