from pathlib import Path

import xarray as xr

from sre_convertor import convert_network


def test_convert_network_writes_minimum_fm_artifacts(tmp_path: Path) -> None:
    input_dir = tmp_path / "sre"
    output_dir = tmp_path / "fm"
    input_dir.mkdir()

    (input_dir / "DEFTOP.1").write_text(
        "\n".join(
            [
                "NODE id '0' nm 'us' px 0.0 py 0.0 node",
                "NODE id '1' nm 'ds' px 1000.0 py 0.0 node",
                "BRCH id '101' nm 'main' bn '0' en '1' al 1000.0 brch",
            ]
        ),
        encoding="utf-8",
    )

    report = convert_network(input_dir, output_dir, model_name="demo")

    assert report.nodes_count == 2
    assert report.branches_count == 1

    dimr_path = output_dir / "dimr_config.xml"
    mdu_path = output_dir / "dflowfm" / "demo.mdu"
    net_path = output_dir / "dflowfm" / "demo_net.nc"

    assert dimr_path.exists()
    assert mdu_path.exists()
    assert net_path.exists()

    dimr = dimr_path.read_text(encoding="utf-8")
    assert "dflowfm/demo.mdu" in dimr

    mdu = mdu_path.read_text(encoding="utf-8")
    assert "demo_net.nc" in mdu

    ds = xr.open_dataset(net_path)
    try:
        assert int(ds.sizes["network1d_nNodes"]) == 2
        assert int(ds.sizes["network1d_nEdges"]) == 1
        assert float(ds["network1d_edge_length"].values[0]) == 1000.0
    finally:
        ds.close()
