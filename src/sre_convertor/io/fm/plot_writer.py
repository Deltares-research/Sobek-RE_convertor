from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from ...models import (
    BoundaryCondition,
    BranchInitialCondition,
    BranchRoughness,
    BranchTransportParameters,
    CrossSectionDefinition,
    CrossSectionLocation,
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
    roughness: tuple[BranchRoughness, ...] = (),
    transport_parameters: tuple[BranchTransportParameters, ...] = (),
    cross_section_definitions: tuple[CrossSectionDefinition, ...] = (),
    cross_section_locations: tuple[CrossSectionLocation, ...] = (),
) -> tuple[Path, ...]:
    target_dir.mkdir(parents=True, exist_ok=True)
    branch_names = {branch.id: branch.name for branch in network.branches}
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
        branch_names,
    )
    _write_sediment_composition_plot(
        paths[len(timeseries_paths) + 1], sediment_fractions, branch_composition, branch_names
    )
    paths = paths + _write_initial_condition_plots(target_dir, initial_conditions, branch_names)
    paths = paths + _write_friction_plots(target_dir, roughness, branch_names)
    paths = paths + _write_acal_plots(target_dir, network, transport_parameters, branch_names)
    paths = paths + _write_cross_section_width_plots(
        target_dir,
        cross_section_definitions,
        cross_section_locations,
        branch_names,
    )
    paths = paths + _write_cross_section_elevation_plots(
        target_dir,
        cross_section_definitions,
        cross_section_locations,
        branch_names,
    )
    return paths


def _write_timeseries_plots(
    target_dir: Path,
    boundaries: tuple[BoundaryCondition, ...],
    laterals: tuple[LateralDischarge, ...],
) -> tuple[Path, ...]:
    paths: list[Path] = []
    for boundary in boundaries:
        if boundary.series and boundary.quantity != "qhbnd":
            boundary_name = _entity_name(boundary.name, boundary.node_name)
            path = target_dir / f"timeseries_boundary_{_filename_name(boundary_name)}.png"
            _write_single_timeseries_plot(
                path,
                f"Boundary {boundary_name} ({boundary.quantity})",
                boundary.series,
                boundary.quantity,
            )
            paths.append(path)
    for lateral in laterals:
        if lateral.series:
            lateral_name = _entity_name(lateral.name)
            path = target_dir / f"timeseries_lateral_{_filename_name(lateral_name)}.png"
            _write_single_timeseries_plot(
                path,
                f"Lateral {lateral_name}",
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
    branch_names: dict[str, str],
) -> tuple[Path, ...]:
    conditions_by_branch: dict[str, list[BranchInitialCondition]] = {}
    for condition in initial_conditions:
        conditions_by_branch.setdefault(condition.branch_id, []).append(condition)

    paths: list[Path] = []
    for branch_id, conditions in sorted(conditions_by_branch.items()):
        branch_name = _entity_name(branch_names.get(branch_id, ""))
        conditions.sort(key=lambda condition: condition.chainage)
        figure, axis = plt.subplots(figsize=(11, 6))
        axis.plot(
            [condition.chainage for condition in conditions],
            [condition.water_level for condition in conditions],
            color="#2d5f73",
            marker="o",
            markersize=3,
        )
        axis.set_title(f"Initial condition: {branch_name}")
        axis.set_xlabel("Chainage")
        axis.set_ylabel("Water level")
        axis.grid(True, alpha=0.25)
        figure.tight_layout()
        path = target_dir / f"initial_condition_branch_{_filename_name(branch_name)}.png"
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


def _write_friction_plots(
    target_dir: Path,
    roughness: tuple[BranchRoughness, ...],
    branch_names: dict[str, str],
) -> tuple[Path, ...]:
    paths: list[Path] = []
    for branch_roughness in roughness:
        branch_name = _entity_name(branch_names.get(branch_roughness.branch_id, ""))
        profiles = branch_roughness.section_profiles or (
            ("Main channel", branch_roughness.chainages, branch_roughness.values),
        )
        profiles = tuple(profile for profile in profiles if profile[1] and profile[2])
        if not profiles:
            continue

        figure, axis = plt.subplots(figsize=(11, 6))
        for section_index, (section_name, chainages, values) in enumerate(profiles):
            axis.plot(chainages, values, marker="o", markersize=3, label=section_name)
        axis.set_title(f"Friction coefficient: {branch_name}")
        axis.set_xlabel("Chainage")
        axis.set_ylabel(branch_roughness.friction_type)
        axis.grid(True, alpha=0.25)
        axis.legend(loc="best")
        figure.tight_layout()
        path = target_dir / f"friction_branch_{_filename_name(branch_name)}.png"
        figure.savefig(path, dpi=150)
        plt.close(figure)
        paths.append(path)

    if paths:
        return tuple(paths)

    path = target_dir / "friction.png"
    figure, axis = plt.subplots(figsize=(11, 6))
    axis.text(0.5, 0.5, "No friction profiles found", ha="center", va="center", transform=axis.transAxes)
    axis.set_axis_off()
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)
    return (path,)


def _write_acal_plots(
    target_dir: Path,
    network: NetworkModel,
    transport_parameters: tuple[BranchTransportParameters, ...],
    branch_names: dict[str, str],
) -> tuple[Path, ...]:
    branch_lengths = {branch.id: branch.length for branch in network.branches}
    paths: list[Path] = []
    for parameters in transport_parameters:
        if parameters.calibration_factor is None or parameters.branch_id not in branch_lengths:
            continue

        branch_name = _entity_name(branch_names.get(parameters.branch_id, ""))
        figure, axis = plt.subplots(figsize=(11, 6))
        axis.plot(
            (0.0, branch_lengths[parameters.branch_id]),
            (parameters.calibration_factor, parameters.calibration_factor),
            color="#5b4b8a",
            marker="o",
            markersize=4,
            label="acal",
        )
        axis.set_title(f"Sediment transport calibration factor: {branch_name}")
        axis.set_xlabel("Chainage")
        axis.set_ylabel("acal")
        axis.grid(True, alpha=0.25)
        axis.legend(loc="best")
        figure.tight_layout()
        path = target_dir / f"acal_branch_{_filename_name(branch_name)}.png"
        figure.savefig(path, dpi=150)
        plt.close(figure)
        paths.append(path)

    if paths:
        return tuple(paths)

    path = target_dir / "acal.png"
    figure, axis = plt.subplots(figsize=(11, 6))
    axis.text(0.5, 0.5, "No sediment transport calibration factors found", ha="center", va="center", transform=axis.transAxes)
    axis.set_axis_off()
    figure.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(figure)
    return (path,)


def _cross_section_profiles(
    definitions: tuple[CrossSectionDefinition, ...],
    locations: tuple[CrossSectionLocation, ...],
) -> dict[str, list[tuple[float, CrossSectionDefinition]]]:
    definitions_by_id = {definition.id: definition for definition in definitions}
    profiles: dict[str, list[tuple[float, CrossSectionDefinition]]] = {}
    for location in locations:
        definition = definitions_by_id.get(location.definition_id)
        if definition is not None:
            profiles.setdefault(location.branch_id, []).append((location.chainage, definition))
    for branch_profiles in profiles.values():
        branch_profiles.sort(key=lambda item: item[0])
    return profiles


def _write_cross_section_width_plots(
    target_dir: Path,
    definitions: tuple[CrossSectionDefinition, ...],
    locations: tuple[CrossSectionLocation, ...],
    branch_names: dict[str, str],
) -> tuple[Path, ...]:
    paths: list[Path] = []
    for branch_id, profiles in sorted(_cross_section_profiles(definitions, locations).items()):
        branch_name = _entity_name(branch_names.get(branch_id, ""))
        chainages = [chainage for chainage, _ in profiles]
        figure, axis = plt.subplots(figsize=(11, 6))
        axis.stackplot(
            chainages,
            [
                [definition.main_width for _, definition in profiles],
                [definition.fp1_width for _, definition in profiles],
                [definition.fp2_width for _, definition in profiles],
            ],
            labels=("Main channel", "Floodplain width 1", "Floodplain width 2"),
            colors=("#2d5f73", "#e07a5f", "#81b29a"),
        )
        axis.set_title(f"Cross-section widths: {branch_name}")
        axis.set_xlabel("Chainage")
        axis.set_ylabel("Width")
        axis.grid(True, alpha=0.25)
        axis.legend(loc="best")
        figure.tight_layout()
        path = target_dir / f"cross_section_widths_{_filename_name(branch_name)}.png"
        figure.savefig(path, dpi=150)
        plt.close(figure)
        paths.append(path)
    return tuple(paths)


def _write_cross_section_elevation_plots(
    target_dir: Path,
    definitions: tuple[CrossSectionDefinition, ...],
    locations: tuple[CrossSectionLocation, ...],
    branch_names: dict[str, str],
) -> tuple[Path, ...]:
    paths: list[Path] = []
    for branch_id, profiles in sorted(_cross_section_profiles(definitions, locations).items()):
        branch_name = _entity_name(branch_names.get(branch_id, ""))
        statistics = []
        for chainage, definition in profiles:
            levels = sorted(definition.levels)
            if not levels:
                continue
            statistics.append(
                (
                    chainage,
                    min(levels),
                    max(levels),
                    sum(levels) / len(levels),
                    _percentile(levels, 0.25),
                    _percentile(levels, 0.75),
                )
            )
        if not statistics:
            continue

        figure, axis = plt.subplots(figsize=(11, 6))
        chainages = [item[0] for item in statistics]
        labels = ("Minimum", "Maximum", "Mean", "25th percentile", "75th percentile")
        for index, label in enumerate(labels, start=1):
            axis.plot(chainages, [item[index] for item in statistics], label=label)
        axis.set_title(f"Cross-section elevations: {branch_name}")
        axis.set_xlabel("Chainage")
        axis.set_ylabel("Elevation")
        axis.grid(True, alpha=0.25)
        axis.legend(loc="best")
        figure.tight_layout()
        path = target_dir / f"cross_section_elevations_{_filename_name(branch_name)}.png"
        figure.savefig(path, dpi=150)
        plt.close(figure)
        paths.append(path)
    return tuple(paths)


def _percentile(values: list[float], fraction: float) -> float:
    if len(values) == 1:
        return values[0]
    position = (len(values) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    weight = position - lower
    return values[lower] + (values[upper] - values[lower]) * weight


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
    branch_names: dict[str, str],
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
        axis.set_xticks(
            x_values,
            [_entity_name(branch_names.get(branch_id, "")) for branch_id, _ in branch_composition],
            rotation=45,
            ha="right",
        )
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
    branch_names: dict[str, str],
) -> tuple[Path, ...]:
    samples_by_branch: dict[str, list[LayerCompositionSample]] = {}
    for sample in samples:
        samples_by_branch.setdefault(sample.branch_id, []).append(sample)

    paths: list[Path] = []
    top_layer_index = max((layer_count or 1) - 1, 0)
    for branch_id, branch_samples in sorted(samples_by_branch.items()):
        branch_name = _entity_name(branch_names.get(branch_id, ""))
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
        axis.set_title(f"Initial sediment composition: {branch_name}")
        axis.set_xlabel("Chainage")
        axis.set_ylabel("Volume fraction")
        axis.set_ylim(0.0, 1.0)
        axis.grid(True, axis="y", alpha=0.25)
        axis.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize="small")
        figure.tight_layout()
        path = target_dir / f"initial_sediment_composition_branch_{_filename_name(branch_name)}.png"
        figure.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(figure)
        paths.append(path)

    return tuple(paths)


def _entity_name(name: str, fallback: str = "") -> str:
    for candidate in (name, fallback):
        if candidate and candidate.strip() and candidate.strip().lower() != "(null)":
            return candidate.strip()
    return "unnamed"


def _filename_name(name: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return sanitized or "unnamed"


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
