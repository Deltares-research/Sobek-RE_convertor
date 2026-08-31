from __future__ import annotations

import re

from ...models import Branch, CrossSectionDefinition, CrossSectionLocation, NetworkModel


def densify_cross_sections_for_grid(
    network: NetworkModel,
    definitions: tuple[CrossSectionDefinition, ...],
    locations: tuple[CrossSectionLocation, ...],
    create_unique_definitions: bool = True,
) -> tuple[tuple[CrossSectionDefinition, ...], tuple[CrossSectionLocation, ...], list[str]]:
    warnings: list[str] = []
    defs_by_id = {definition.id: definition for definition in definitions}

    by_branch: dict[str, list[CrossSectionLocation]] = {}
    for location in locations:
        by_branch.setdefault(location.branch_id, []).append(location)

    for branch_id in by_branch:
        by_branch[branch_id].sort(key=lambda item: (item.chainage, item.id))

    generated_definitions: dict[str, CrossSectionDefinition] = {}
    output_locations: list[CrossSectionLocation] = []
    def_counter = 0

    for branch in network.branches:
        branch_locations = by_branch.get(branch.id, [])
        if not branch_locations:
            continue

        target_chainages = _branch_target_chainages(branch)
        if not target_chainages:
            for location in branch_locations:
                output_loc, out_def = _process_location_with_unique_copy(
                    location, defs_by_id, create_unique_definitions, branch, def_counter
                )
                output_locations.append(output_loc)
                if out_def:
                    generated_definitions[out_def.id] = out_def
                    def_counter += 1
            continue

        for chainage in target_chainages:
            exact = _find_exact_location(branch_locations, chainage)
            if exact is not None:
                output_loc, out_def = _process_location_with_unique_copy(
                    exact, defs_by_id, create_unique_definitions, branch, def_counter
                )
                output_locations.append(output_loc)
                if out_def:
                    generated_definitions[out_def.id] = out_def
                    def_counter += 1
                continue

            lower, upper = _find_bounds(branch_locations, chainage)
            if lower is not None and upper is not None and lower.chainage != upper.chainage:
                lower_def = defs_by_id.get(lower.definition_id)
                upper_def = defs_by_id.get(upper.definition_id)
                if lower_def is not None and upper_def is not None and _compatible_for_interpolation(lower_def, upper_def):
                    ratio = (chainage - lower.chainage) / (upper.chainage - lower.chainage)
                    synthetic_id = f"CS_INT_{_sanitize_id(branch.id)}_{def_counter:06d}"

                    interpolated_definition = _interpolate_definition(
                        synthetic_id,
                        lower_def,
                        upper_def,
                        ratio,
                    )
                    generated_definitions[synthetic_id] = interpolated_definition
                    def_counter += 1

                    output_locations.append(
                        CrossSectionLocation(
                            id=synthetic_id,
                            name=synthetic_id,
                            branch_id=branch.id,
                            chainage=chainage,
                            definition_id=synthetic_id,
                            reference_level=_interpolate_value(
                                lower.reference_level,
                                upper.reference_level,
                                ratio,
                            ),
                        )
                    )
                    continue

            # Fallback: map to nearest with optional unique copy for morphodynamics
            nearest = _nearest_location(branch_locations, chainage)
            output_loc, out_def = _process_mapped_location_with_unique_copy(
                nearest, defs_by_id, create_unique_definitions, branch, def_counter
            )
            # Update output location to use the target chainage, not the nearest's original chainage
            output_loc = CrossSectionLocation(
                id=output_loc.id,
                name=output_loc.name,
                branch_id=output_loc.branch_id,
                chainage=chainage,
                definition_id=output_loc.definition_id,
                reference_level=output_loc.reference_level,
            )
            output_locations.append(output_loc)
            if out_def:
                generated_definitions[out_def.id] = out_def
                def_counter += 1

            if lower is not None and upper is not None:
                warnings.append(
                    f"Cross-section interpolation fallback on branch {branch.id} at chainage {chainage:.3f}: incompatible definition shapes."
                )

    all_definitions = {definition.id: definition for definition in definitions}
    all_definitions.update(generated_definitions)

    selected_definitions = tuple(sorted(all_definitions.values(), key=lambda d: d.id))
    selected_locations = tuple(sorted(output_locations, key=lambda item: (item.branch_id, item.chainage, item.id)))

    return selected_definitions, selected_locations, warnings


def _branch_target_chainages(branch: Branch) -> tuple[float, ...]:
    valid = [chainage for chainage in branch.grid_chainages if 0.0 <= chainage <= branch.length]
    return tuple(sorted(set(valid)))


def _find_exact_location(
    locations: list[CrossSectionLocation],
    chainage: float,
    tol: float = 1e-6,
) -> CrossSectionLocation | None:
    for location in locations:
        if abs(location.chainage - chainage) <= tol:
            return location
    return None


def _find_bounds(
    locations: list[CrossSectionLocation],
    chainage: float,
) -> tuple[CrossSectionLocation | None, CrossSectionLocation | None]:
    lower: CrossSectionLocation | None = None
    upper: CrossSectionLocation | None = None

    for location in locations:
        if location.chainage <= chainage:
            lower = location
        if location.chainage >= chainage:
            upper = location
            break

    return lower, upper


def _nearest_location(locations: list[CrossSectionLocation], chainage: float) -> CrossSectionLocation:
    return min(locations, key=lambda location: (abs(location.chainage - chainage), location.chainage))


def _compatible_for_interpolation(
    left: CrossSectionDefinition,
    right: CrossSectionDefinition,
) -> bool:
    return (
        len(left.levels) == len(right.levels)
        and len(left.flow_widths) == len(right.flow_widths)
        and len(left.total_widths) == len(right.total_widths)
    )


def _interpolate_definition(
    definition_id: str,
    left: CrossSectionDefinition,
    right: CrossSectionDefinition,
    ratio: float,
) -> CrossSectionDefinition:
    return CrossSectionDefinition(
        id=definition_id,
        name=definition_id,
        levels=_interpolate_series(left.levels, right.levels, ratio),
        flow_widths=_interpolate_series(left.flow_widths, right.flow_widths, ratio),
        total_widths=_interpolate_series(left.total_widths, right.total_widths, ratio),
    )


def _interpolate_series(left: tuple[float, ...], right: tuple[float, ...], ratio: float) -> tuple[float, ...]:
    return tuple(_interpolate_value(lv, rv, ratio) for lv, rv in zip(left, right))


def _interpolate_value(left: float, right: float, ratio: float) -> float:
    return left + (right - left) * ratio


def _sanitize_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", value)


def _process_location_with_unique_copy(
    location: CrossSectionLocation,
    defs_by_id: dict[str, CrossSectionDefinition],
    create_unique: bool,
    branch: Branch,
    counter: int,
) -> tuple[CrossSectionLocation, CrossSectionDefinition | None]:
    if not create_unique:
        return location, None

    source_def = defs_by_id.get(location.definition_id)
    if not source_def:
        return location, None

    unique_id = f"CS_UNQ_{_sanitize_id(branch.id)}_{counter:06d}"
    unique_def = CrossSectionDefinition(
        id=unique_id,
        name=unique_id,
        levels=source_def.levels,
        flow_widths=source_def.flow_widths,
        total_widths=source_def.total_widths,
    )
    return (
        CrossSectionLocation(
            id=location.id,
            name=location.name,
            branch_id=location.branch_id,
            chainage=location.chainage,
            definition_id=unique_id,
            reference_level=location.reference_level,
        ),
        unique_def,
    )


def _process_mapped_location_with_unique_copy(
    location: CrossSectionLocation,
    defs_by_id: dict[str, CrossSectionDefinition],
    create_unique: bool,
    branch: Branch,
    counter: int,
) -> tuple[CrossSectionLocation, CrossSectionDefinition | None]:
    source_def = defs_by_id.get(location.definition_id)
    new_location_id = f"CS_MAP_{_sanitize_id(branch.id)}_{counter:06d}"

    if not source_def:
        new_location = CrossSectionLocation(
            id=new_location_id,
            name=new_location_id,
            branch_id=branch.id,
            chainage=location.chainage,
            definition_id=location.definition_id,
            reference_level=location.reference_level,
        )
        return new_location, None

    if not create_unique:
        new_location = CrossSectionLocation(
            id=new_location_id,
            name=new_location_id,
            branch_id=branch.id,
            chainage=location.chainage,
            definition_id=location.definition_id,
            reference_level=location.reference_level,
        )
        return new_location, None

    unique_id = f"CS_UNQ_{_sanitize_id(branch.id)}_{counter:06d}"
    unique_def = CrossSectionDefinition(
        id=unique_id,
        name=unique_id,
        levels=source_def.levels,
        flow_widths=source_def.flow_widths,
        total_widths=source_def.total_widths,
    )
    new_location = CrossSectionLocation(
        id=new_location_id,
        name=new_location_id,
        branch_id=branch.id,
        chainage=location.chainage,
        definition_id=unique_id,
        reference_level=location.reference_level,
    )
    return new_location, unique_def
