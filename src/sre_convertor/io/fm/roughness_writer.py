from __future__ import annotations

from pathlib import Path

from ...models import NetworkModel


def write_default_roughness(network: NetworkModel, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)

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
        lines.extend(
            [
                "[Branch]",
                f"    branchId              = #{branch.id}#",
                "    frictionType          = Manning",
                "    functionType          = constant",
                "    numLocations          = 1",
                "    chainage              = 0.000",
                "    frictionValues        = 0.03000",
                "",
            ]
        )

    target_path.write_text("\n".join(lines), encoding="utf-8")
