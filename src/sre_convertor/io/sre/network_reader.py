from __future__ import annotations

import shlex
from pathlib import Path

from ...models import Branch, NetworkModel, NetworkReadDiagnostics, Node
from .records import load_records

class SreParseError(ValueError):
    pass


def _normalize_value(value: str) -> str:
    value = value.strip()
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    return value


def _parse_key_values(line: str) -> dict[str, str]:
    # SRE topology records are key/value pairs with optional trailing type tokens.
    # Using shlex keeps quoted identifiers intact.
    tokens = shlex.split(line)
    attrs: dict[str, str] = {}

    i = 1
    while i + 1 < len(tokens):
        key = tokens[i].lower()
        value = tokens[i + 1]
        attrs[key] = _normalize_value(value)
        i += 2

    return attrs


def _find_topology_file(input_dir: Path) -> Path:
    for candidate in sorted(input_dir.glob("DEFTOP.*")):
        if not candidate.is_file():
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "NODE id" in text or "BRCH id" in text:
            return candidate
    raise FileNotFoundError("No DEFTOP.* file with NODE/BRCH records found.")


def read_sre_network(input_dir: Path) -> NetworkModel:
    source_file = _find_topology_file(input_dir)
    nodes: list[Node] = []
    branches: list[Branch] = []
    node_lines: list[tuple[str, int]] = []
    branch_lines: list[tuple[str, int]] = []

    for line_number, line in enumerate(
        source_file.read_text(encoding="utf-8", errors="ignore").splitlines(),
        start=1,
    ):
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("NODE "):
            attrs = _parse_key_values(stripped)
            try:
                node_id = attrs["id"]
                nodes.append(
                    Node(id=node_id, name=attrs.get("nm", ""), x=float(attrs["px"]), y=float(attrs["py"])),
                )
                node_lines.append((node_id, line_number))
            except KeyError as e:
                raise SreParseError(f"Missing NODE field {e!s} in line: {stripped}") from e
            except ValueError as e:
                raise SreParseError(f"Invalid NODE numeric field in line: {stripped}") from e
            continue

        if stripped.startswith("BRCH "):
            attrs = _parse_key_values(stripped)
            try:
                branch_id = attrs["id"]
                branches.append(
                    Branch(
                        id=branch_id,
                        name=attrs.get("nm", ""),
                        from_node_id=attrs["bn"],
                        to_node_id=attrs["en"],
                        length=float(attrs["al"]),
                    )
                )
                branch_lines.append((branch_id, line_number))
            except KeyError as e:
                raise SreParseError(f"Missing BRCH field {e!s} in line: {stripped}") from e
            except ValueError as e:
                raise SreParseError(f"Invalid BRCH numeric field in line: {stripped}") from e

    if not nodes:
        raise SreParseError(f"No NODE records found in {source_file.name}.")
    if not branches:
        raise SreParseError(f"No BRCH records found in {source_file.name}.")

    branch_grid_chainages, grid_records = _read_branch_grid_chainages(input_dir)
    branches = [
        Branch(
            id=branch.id,
            name=branch.name,
            from_node_id=branch.from_node_id,
            to_node_id=branch.to_node_id,
            length=branch.length,
            grid_chainages=branch_grid_chainages.get(branch.id, tuple()),
        )
        for branch in branches
    ]

    return NetworkModel(
        nodes=tuple(nodes),
        branches=tuple(branches),
        source_file=source_file,
        diagnostics=NetworkReadDiagnostics(
            topology_node_lines=tuple(node_lines),
            topology_branch_lines=tuple(branch_lines),
            grid_records=tuple(grid_records),
            branch_connectivity=tuple(
                (branch.id, branch.from_node_id, branch.to_node_id, branch.length, branch.grid_chainages)
                for branch in branches
            ),
        ),
    )


def _read_branch_grid_chainages(
    input_dir: Path,
) -> tuple[dict[str, tuple[float, ...]], list[tuple[str, int, int, str, tuple[float, ...]]]]:
    records = load_records(input_dir, "DEFGRD", {"GRID"})
    chainages_by_branch: dict[str, tuple[float, ...]] = {}
    grid_records: list[tuple[str, int, int, str, tuple[float, ...]]] = []

    for record in records:
        branch_id = record.attrs.get("ci")
        if not branch_id:
            continue

        values: list[float] = []
        if record.tables:
            for row in record.tables[0]:
                if not row:
                    continue
                try:
                    values.append(float(row[0]))
                except ValueError:
                    continue

        if values:
            chainages = _normalize_chainages(values)
            chainages_by_branch[branch_id] = chainages
            grid_records.append(
                (
                    record.source_file.name,
                    record.source_line_start,
                    record.source_line_end,
                    branch_id,
                    chainages,
                )
            )

    return chainages_by_branch, grid_records


def _normalize_chainages(values: list[float]) -> tuple[float, ...]:
    uniq_sorted = sorted(set(v for v in values if v >= 0.0))
    if not uniq_sorted:
        return tuple()
    return tuple(uniq_sorted)
