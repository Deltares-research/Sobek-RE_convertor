from pathlib import Path

from sre_convertor.io.fm.run_writer import (
    DEFAULT_RUN_DIMR_PATH,
    write_run_dimr_bat,
)


def test_write_run_dimr_bat_uses_x64_fm_suite_runner(tmp_path: Path) -> None:
    target = write_run_dimr_bat(tmp_path)

    content = target.read_text(encoding="utf-8")

    assert f"set RUN_DIMR={DEFAULT_RUN_DIMR_PATH}" in content
    assert f'call "%RUN_DIMR%" dimr_config.xml' in content
