from __future__ import annotations

import shlex
from pathlib import Path

from ...models import Branch, NetworkModel, Node

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

    for line in source_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("NODE "):
            attrs = _parse_key_values(stripped)
            try:
                nodes.append(
                    Node(
                        id=attrs["id"],
                        name=attrs.get("nm", ""),
                        x=float(attrs["px"]),
                        y=float(attrs["py"]),
                    )
                )
            except KeyError as e:
                raise SreParseError(f"Missing NODE field {e!s} in line: {stripped}") from e
            except ValueError as e:
                raise SreParseError(f"Invalid NODE numeric field in line: {stripped}") from e
            continue

        if stripped.startswith("BRCH "):
            attrs = _parse_key_values(stripped)
            try:
                branches.append(
                    Branch(
                        id=attrs["id"],
                        name=attrs.get("nm", ""),
                        from_node_id=attrs["bn"],
                        to_node_id=attrs["en"],
                        length=float(attrs["al"]),
                    )
                )
            except KeyError as e:
                raise SreParseError(f"Missing BRCH field {e!s} in line: {stripped}") from e
            except ValueError as e:
                raise SreParseError(f"Invalid BRCH numeric field in line: {stripped}") from e

    if not nodes:
        raise SreParseError(f"No NODE records found in {source_file.name}.")
    if not branches:
        raise SreParseError(f"No BRCH records found in {source_file.name}.")

    return NetworkModel(nodes=tuple(nodes), branches=tuple(branches), source_file=source_file)
