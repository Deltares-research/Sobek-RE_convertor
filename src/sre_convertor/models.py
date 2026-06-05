from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Node:
    id: str
    name: str
    x: float
    y: float


@dataclass(frozen=True)
class Branch:
    id: str
    name: str
    from_node_id: str
    to_node_id: str
    length: float


@dataclass(frozen=True)
class NetworkModel:
    nodes: tuple[Node, ...]
    branches: tuple[Branch, ...]
    source_file: Path


@dataclass(frozen=True)
class ConversionOptions:
    model_name: str = "sre2fm_network"


@dataclass
class ConversionReport:
    input_dir: Path
    output_dir: Path
    model_name: str
    nodes_count: int
    branches_count: int
    warnings: list[str] = field(default_factory=list)
