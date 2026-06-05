from pathlib import Path

from sre_convertor.io.sre.network_reader import read_sre_network


def test_read_sre_network_from_deftop(tmp_path: Path) -> None:
    source = tmp_path / "DEFTOP.1"
    source.write_text(
        "\n".join(
            [
                "NODE id 'n1' nm 'upstream' px 0.0 py 1.0 node",
                "NODE id 'n2' nm 'downstream' px 10.0 py 1.0 node",
                "BRCH id 'b1' nm 'reach1' bn 'n1' en 'n2' al 10.0 brch",
            ]
        ),
        encoding="utf-8",
    )

    network = read_sre_network(tmp_path)

    assert len(network.nodes) == 2
    assert len(network.branches) == 1
    assert network.nodes[0].id == "n1"
    assert network.branches[0].from_node_id == "n1"
    assert network.branches[0].to_node_id == "n2"
