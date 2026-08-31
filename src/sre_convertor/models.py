from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
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
    grid_chainages: tuple[float, ...] = ()


@dataclass(frozen=True)
class NetworkModel:
    nodes: tuple[Node, ...]
    branches: tuple[Branch, ...]
    source_file: Path


@dataclass(frozen=True)
class TimeSeriesPoint:
    time: str
    value: float


@dataclass(frozen=True)
class CrossSectionDefinition:
    id: str
    name: str
    levels: tuple[float, ...]
    flow_widths: tuple[float, ...]
    total_widths: tuple[float, ...]


@dataclass(frozen=True)
class CrossSectionLocation:
    id: str
    name: str
    branch_id: str
    chainage: float
    definition_id: str
    reference_level: float


@dataclass(frozen=True)
class BoundaryCondition:
    id: str
    name: str
    node_id: str
    node_name: str
    quantity: str
    series: tuple[TimeSeriesPoint, ...]


@dataclass(frozen=True)
class LateralDischarge:
    id: str
    name: str
    branch_id: str
    chainage: float
    series: tuple[TimeSeriesPoint, ...]


@dataclass(frozen=True)
class Structure:
    id: str
    name: str
    branch_id: str
    chainage: float
    structure_type: str
    crest_level: float
    crest_width: float
    gate_opening_width: float | None = None
    gate_lower_edge_level: float | None = None


@dataclass(frozen=True)
class RuntimeSettings:
    refdate: datetime
    tstart_seconds: int
    tstop_seconds: int


@dataclass(frozen=True)
class SreCaseModel:
    network: NetworkModel
    cross_section_definitions: tuple[CrossSectionDefinition, ...]
    cross_section_locations: tuple[CrossSectionLocation, ...]
    boundaries: tuple[BoundaryCondition, ...]
    laterals: tuple[LateralDischarge, ...]
    structures: tuple[Structure, ...]
    runtime: RuntimeSettings


@dataclass(frozen=True)
class ConversionOptions:
    model_name: str = "sre2fm_network"
    network_only: bool = False
    activate_cross_sections: bool = True
    test_duration_seconds: int = 7200


@dataclass
class ConversionReport:
    input_dir: Path
    output_dir: Path
    model_name: str
    nodes_count: int
    branches_count: int
    files_created: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
