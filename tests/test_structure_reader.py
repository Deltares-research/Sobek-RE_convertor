from pathlib import Path

from sre_convertor.io.sre.structure_reader import read_structures


def test_read_structures_maps_via_stcm_and_ignores_aux_stru_records(tmp_path: Path) -> None:
    # Location STRU records with ci/lc.
    (tmp_path / "DEFSTR.1").write_text(
        "\n".join(
            [
                "STRU id '100' nm 'Driel_Z' ci '-1' lc 9.9999e+009 stru",
                "STCM id '200' nm 'Driel' ci '7262' lc 13000 stcm",
            ]
        ),
        encoding="utf-8",
    )

    # Definition link and auxiliary STRU without ci/lc (must not overwrite location).
    (tmp_path / "DEFSTR.2").write_text(
        "STRU id '100' dd '300' ca 0 0 0 0 stru\n",
        encoding="utf-8",
    )
    (tmp_path / "DEFSTR.6").write_text(
        "STRU id '100' sy 0 el 9.9999e+009 stru\n",
        encoding="utf-8",
    )

    # Structure type/shape definition.
    (tmp_path / "DEFSTR.3").write_text(
        "STDS id '300' nm 'Driel_zom_gen' ty 2 w1 102 wl 95 zs 2.7 stds\n",
        encoding="utf-8",
    )

    # STCM membership list linking structure 100 to compound 200.
    (tmp_path / "DEFSTR.7").write_text(
        "\n".join(
            [
                "STCM id '200' st",
                "DLST",
                "'100'",
                "dlst",
                "stcm",
            ]
        ),
        encoding="utf-8",
    )

    structures, warnings = read_structures(tmp_path)

    assert not warnings
    assert len(structures) == 1
    structure = structures[0]
    assert structure.id == "ST_100"
    assert structure.branch_id == "7262"
    assert structure.chainage == 13000.0
    assert structure.structure_type == "orifice"


def test_read_structures_maps_using_dlst_when_names_do_not_match(tmp_path: Path) -> None:
    (tmp_path / "DEFSTR.1").write_text(
        "\n".join(
            [
                "STRU id '78754' nm 'Amero_W' ci '-1' lc 9.9999e+009 stru",
                "STCM id '78761' nm 'Amerongen' ci '7262' lc 44000 stcm",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "DEFSTR.2").write_text(
        "STRU id '78754' dd '73312' ca 0 0 0 0 stru\n",
        encoding="utf-8",
    )
    (tmp_path / "DEFSTR.3").write_text(
        "STDS id '73312' nm 'Driel winter' ty 0 cl 8.8 cw 790 stds\n",
        encoding="utf-8",
    )
    (tmp_path / "DEFSTR.7").write_text(
        "\n".join(
            [
                "STCM id '78761' st",
                "DLST",
                "'78754'",
                "dlst",
                "stcm",
            ]
        ),
        encoding="utf-8",
    )

    structures, warnings = read_structures(tmp_path)

    assert not warnings
    assert len(structures) == 1
    assert structures[0].branch_id == "7262"
    assert structures[0].chainage == 44000.0
