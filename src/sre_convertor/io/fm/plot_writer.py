from __future__ import annotations

from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from ...models import (
    BoundaryCondition,
    BranchInitialCondition,
    LayerCompositionSample,
    LateralDischarge,
    NetworkModel,
)


def write_conversion_plots(
    target_dir: Path,
    network: NetworkModel,
    boundaries: tuple[BoundaryCondition, ...] = (),
    laterals: tuple[LateralDischarge, ...] = (),
    sediment_fractions: tuple[float, ...] = (),
    branch_composition: tuple[tuple[str, tuple[float, ...]], ...] = (),
    layer_composition: tuple[LayerCompositionSample, ...] = (),
    layer_count: int | None = None,
    initial_conditions: tuple[BranchInitialCondition, ...] = (),
) -> tuple[Path, ...]:
    target_dir.mkdir(parents=True, exist_ok=True)
    timeseries_paths = _write_timeseries_plots(target_dir, boundaries, laterals)
    paths = timeseries_paths + (
        target_dir / "grid.png",
        target_dir / "initial_sediment_composition.png",
    )
    _write_grid_plot(paths[-2], network)
    paths = paths + _write_branch_composition_plots(
        target_dir,
        sediment_fractions,
        layer_composition,
        layer_count,
    )
    _write_sediment_composition_plot(paths[len(timeseries_paths) + 1], sediment_fractions, branch_composition)
    paths = paths + _write_initial_condition_plots(target_dir, initial_conditions)
    return paths


def _write_timeseries_plots(
    target_dir: Path,
    boundaries: tuple[BoundaryCondition, ...],
    laterals: tuple[LateralDischarge, ...],
) -> tuple[Path, ...]:
    paths: list[Path] = []
    for boundary in boundaries:
        if boundary.series:
            path = target_dir / f"timeseries_boundary_{boundary.id}.png"
            _write_single_timeseries_plot(
                path,
                f"Boundary {boundary.name or boundary.id} ({boundary.quantity})",
                boundary.series,
                boundary.quantity,
            )
            paths.append(path)
    for lateral in laterals:
        if lateral.series:
            path = target_dir / f"timeseries_lateral_{lateral.id}.png"
            _write_single_timeseries_plot(
                path,
                f"Lateral {lateral.name or lateral.id}",
                lateral.series,
                "Value",
            )
            paths.append(path)

    if not paths:
        path = target_dir / "timeseries.png"
        figure, axis = plt.subplots(figsize=(11, 6))
        axis.text(0.5, 0.5, "No time series found", ha="center", va="center", transform=axis.transAxes)
        axis.set_axis_off()
        figure.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(figure)
        paths.append(path)
    return tuple(paths)


def _write_single_timeseries_plot(path: Path, title: str, series, ylabel: str) -> None:
    figure, axis = plt.subplots(figsize=(11, 6))
    axis.plot(_time_values(series), [point.value for point in series], color="#2d5f73")
    axis.set_title(title)
    axis.set_xlabel("Time")
    axis.set_ylabel(ylabel)
    axis.grid(True, alpha=0.25)
    figure.autofmt_xdate()
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def _write_initial_condition_plots(
    target_dir: Path,
    initial_conditions: tuple[BranchInitialCondition, ...],
) -> tuple[Path, ...]:
    conditions_by_branch: dict[str, list[BranchInitialCondition]] = {}
    for condition in initial_conditions:
        conditions_by_branch.setdefault(condition.branch_id, []).append(condition)

    paths: list[Path] = []
    for branch_id, conditions in sorted(conditions_by_branch.items()):
        conditions.sort(key=lambda condition: condition.chainage)
        figure, axis = plt.subplots(figsize=(11, 6))
        axis.plot(
            [condition.chainage for condition in conditions],
            [condition.water_level for condition in conditions],
            color="#2d5f73",
            marker="o",
            markersize=3,
        )
        axis.set_title(f"Initial condition: branch {branch_id}")
        axis.set_xlabel("Chainage")
        axis.set_ylabel("Water level")
        axis.grid(True, alpha=0.25)
        figure.tight_layout()
        path = target_dir / f"initial_condition_branch_{branch_id}.png"
        figure.savefig(path, dpi=150)
        plt.close(figure)
        paths.append(path)

    if paths:
        return tuple(paths)

    path = target_dir / "initial_condition.png"
    figure, axis = plt.subplots(figsize=(11, 6))
    axis.text(0.5, 0.5, "No initial conditions found", ha="center", va="center", transform=axis.transAxes)
    axis.set_axis_off()
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)
    return (path,)


def _write_grid_plot(path: Path, network: NetworkModel) -> None:
    figure, axis = plt.subplots(figsize=(10, 7))
    nodes = {node.id: node for node in network.nodes}
    for branch in network.branches:
        from_node = nodes.get(branch.from_node_id)
        to_node = nodes.get(branch.to_node_id)
        if from_node is None or to_node is None:
            continue
        offsets = _grid_offsets(branch.grid_chainages, branch.length)
        x_values = [from_node.x + (to_node.x - from_node.x) * offset / branch.length for offset in offsets]
        y_values = [from_node.y + (to_node.y - from_node.y) * offset / branch.length for offset in offsets]
        axis.plot(x_values, y_values, color="#2d5f73", linewidth=1.0)
        axis.scatter(x_values, y_values, color="#e07a5f", s=9, zorder=2)
        axis.annotate(
            branch.name,
            (x_values[len(x_values) // 2], y_values[len(y_values) // 2]),
            xytext=(0, 5),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
            color="#2d5f73",
            rotation=90,
        )

    axis.scatter([node.x for node in network.nodes], [node.y for node in network.nodes], color="#19323c", s=18, zorder=3)
    for node in network.nodes:
        axis.annotate(
            node.name,
            (node.x, node.y),
            xytext=(5, 5),
            textcoords="offset points",
            ha="left",
            va="bottom",
            fontsize=8,
            color="#19323c",
        )
    axis.set_title("Converted simulation grid")
    axis.set_xlabel("X")
    axis.set_ylabel("Y")
    axis.set_aspect("equal", adjustable="datalim")
    axis.grid(True, alpha=0.2)
    figure.tight_layout()
    figure.savefig(path, dpi=150)
    plt.close(figure)


def _write_sediment_composition_plot(
    path: Path,
    sediment_fractions: tuple[float, ...],
    branch_composition: tuple[tuple[str, tuple[float, ...]], ...],
) -> None:
    figure, axis = plt.subplots(figsize=(11, 6))
    if branch_composition:
        fraction_count = max(len(sediment_fractions), max(len(weights) for _, weights in branch_composition))
        fractions = sediment_fractions or tuple(float(index + 1) for index in range(fraction_count))
        fractions = fractions + (0.0,) * max(0, fraction_count - len(fractions))
        x_values = list(range(len(branch_composition)))
        weights = [_normalized_weights(values, fraction_count) for _, values in branch_composition]
        layers = list(zip(*weights))
        axis.stackplot(x_values, layers, labels=[f"D50 {value:g} m" for value in fractions[:fraction_count]])
        axis.set_xticks(x_values, [branch_id for branch_id, _ in branch_composition], rotation=45, ha="right")
        axis.set_ylim(0.0, 1.0)
        axis.set_ylabel("Volume fraction")
        axis.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize="small")
    else:
        axis.text(0.5, 0.5, "No initial sediment composition found", ha="center", va="center", transform=axis.transAxes)
    axis.set_title("Initial sediment composition")
    axis.set_xlabel("Branch")
    axis.grid(True, axis="y", alpha=0.25)
    figure.tight_layout()
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)


def _write_branch_composition_plots(
    target_dir: Path,
    sediment_fractions: tuple[float, ...],
    samples: tuple[LayerCompositionSample, ...],
    layer_count: int | None,
) -> tuple[Path, ...]:
    samples_by_branch: dict[str, list[LayerCompositionSample]] = {}
    for sample in samples:
        samples_by_branch.setdefault(sample.branch_id, []).append(sample)

    paths: list[Path] = []
    top_layer_index = max((layer_count or 1) - 1, 0)
    for branch_id, branch_samples in sorted(samples_by_branch.items()):
        branch_samples.sort(key=lambda sample: sample.chainage)
        layer_weights = [
            sample.layer_weights[top_layer_index]
            for sample in branch_samples
            if top_layer_index < len(sample.layer_weights)
        ]
        if not layer_weights:
            continue

        fraction_count = max(len(sediment_fractions), max(len(weights) for weights in layer_weights))
        fractions = sediment_fractions or tuple(float(index + 1) for index in range(fraction_count))
        fractions = fractions + (0.0,) * max(0, fraction_count - len(fractions))
        normalized = [_normalized_weights(weights, fraction_count) for weights in layer_weights]
        figure, axis = plt.subplots(figsize=(11, 6))
        axis.stackplot(
            [sample.chainage for sample in branch_samples[:len(normalized)]],
            list(zip(*normalized)),
            labels=[f"D50 {value:g} m" for value in fractions[:fraction_count]],
        )
        axis.set_title(f"Initial sediment composition: branch {branch_id}")
        axis.set_xlabel("Chainage")
        axis.set_ylabel("Volume fraction")
        axis.set_ylim(0.0, 1.0)
        axis.grid(True, axis="y", alpha=0.25)
        axis.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize="small")
        figure.tight_layout()
        path = target_dir / f"initial_sediment_composition_branch_{branch_id}.png"
        figure.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(figure)
        paths.append(path)

    return tuple(paths)


def _time_values(series) -> list[datetime | float | int]:
    values: list[datetime | float | int] = []
    for index, point in enumerate(series):
        raw_time = point.time.replace(";", "T").replace("/", "-")
        try:
            values.append(datetime.fromisoformat(raw_time))
        except ValueError:
            try:
                values.append(float(point.time))
            except ValueError:
                values.append(index)
    return values


def _grid_offsets(chainages: tuple[float, ...], branch_length: float) -> tuple[float, ...]:
    offsets = [value for value in chainages if 0.0 <= value <= branch_length]
    if not offsets or offsets[0] != 0.0:
        offsets.insert(0, 0.0)
    if not offsets or offsets[-1] != branch_length:
        offsets.append(branch_length)
    return tuple(sorted(set(offsets)))


def _normalized_weights(values: tuple[float, ...], count: int) -> tuple[float, ...]:
    weights = tuple(max(value, 0.0) for value in values[:count]) + (0.0,) * max(0, count - len(values))
    total = sum(weights)
    if total <= 0.0:
        return (1.0,) + (0.0,) * (count - 1)
    return tuple(value / total for value in weights)
