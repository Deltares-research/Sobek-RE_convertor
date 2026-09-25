from pathlib import Path

from sre_convertor.io.fm.cross_section_interpolator import densify_cross_sections_for_grid
from sre_convertor.models import Branch, CrossSectionDefinition, CrossSectionLocation, NetworkModel, Node


def _network_with_single_branch(chainages: tuple[float, ...]) -> NetworkModel:
    return NetworkModel(
        nodes=(
            Node(id="n1", name="n1", x=0.0, y=0.0),
            Node(id="n2", name="n2", x=10.0, y=0.0),
        ),
        branches=(
            Branch(
                id="b1",
                name="b1",
                from_node_id="n1",
                to_node_id="n2",
                length=10.0,
                grid_chainages=chainages,
            ),
        ),
        source_file=Path("DEFTOP.1"),
    )


def test_densify_cross_sections_interpolates_between_known_profiles() -> None:
    network = _network_with_single_branch((0.0, 5.0, 10.0))
    definitions = (
        CrossSectionDefinition(
            id="d0",
            name="d0",
            levels=(0.0, 1.0),
            flow_widths=(2.0, 4.0),
            total_widths=(2.0, 4.0),
        ),
        CrossSectionDefinition(
            id="d1",
            name="d1",
            levels=(0.0, 1.0),
            flow_widths=(4.0, 8.0),
            total_widths=(4.0, 8.0),
        ),
    )
    locations = (
        CrossSectionLocation(
            id="cs0",
            name="cs0",
            branch_id="b1",
            chainage=0.0,
            definition_id="d0",
            reference_level=0.0,
        ),
        CrossSectionLocation(
            id="cs1",
            name="cs1",
            branch_id="b1",
            chainage=10.0,
            definition_id="d1",
            reference_level=2.0,
        ),
    )

    defs_out, locs_out, warnings = densify_cross_sections_for_grid(network, definitions, locations)

    assert len(locs_out) == 3
    assert warnings == []
    middle = next(location for location in locs_out if abs(location.chainage - 5.0) < 1e-9)
    middle_def = next(definition for definition in defs_out if definition.id == middle.definition_id)
    assert middle.reference_level == 1.0
    assert middle_def.flow_widths == (3.0, 6.0)


def test_densify_cross_sections_resamples_profiles_when_shapes_differ() -> None:
    network = _network_with_single_branch((0.0, 5.0, 10.0))
    definitions = (
        CrossSectionDefinition(
            id="d0",
            name="d0",
            levels=(0.0, 1.0),
            flow_widths=(2.0, 4.0),
            total_widths=(2.0, 4.0),
        ),
        CrossSectionDefinition(
            id="d1",
            name="d1",
            levels=(0.0, 0.5, 1.0),
            flow_widths=(4.0, 6.0, 8.0),
            total_widths=(4.0, 6.0, 8.0),
        ),
    )
    locations = (
        CrossSectionLocation(
            id="cs0",
            name="cs0",
            branch_id="b1",
            chainage=0.0,
            definition_id="d0",
            reference_level=0.0,
        ),
        CrossSectionLocation(
            id="cs1",
            name="cs1",
            branch_id="b1",
            chainage=10.0,
            definition_id="d1",
            reference_level=2.0,
        ),
    )

    defs_out, locs_out, warnings = densify_cross_sections_for_grid(network, definitions, locations)

    assert len(locs_out) == 3
    assert warnings == []
    middle = next(location for location in locs_out if abs(location.chainage - 5.0) < 1e-9)
    middle_def = next(definition for definition in defs_out if definition.id == middle.definition_id)
    assert middle_def.levels == (0.0, 0.5, 1.0)
    assert middle_def.flow_widths == (3.0, 4.5, 6.0)
    assert middle_def.total_widths == (3.0, 4.5, 6.0)
