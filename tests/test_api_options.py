from pathlib import Path

import sre_convertor.api as api


def test_convert_case_propagates_cross_section_activation_flag(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_convert_network_case(input_dir: Path, output_dir: Path, options):
        captured["input_dir"] = input_dir
        captured["output_dir"] = output_dir
        captured["options"] = options
        return object()

    monkeypatch.setattr(api, "convert_network_case", _fake_convert_network_case)

    api.convert_case("in", "out", model_name="demo", activate_cross_sections=True)

    options = captured["options"]
    assert options.model_name == "demo"
    assert options.network_only is False
    assert options.activate_cross_sections is True


def test_convert_case_cross_sections_default_to_active(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_convert_network_case(input_dir: Path, output_dir: Path, options):
        captured["options"] = options
        return object()

    monkeypatch.setattr(api, "convert_network_case", _fake_convert_network_case)

    api.convert_case("in", "out", model_name="demo")

    options = captured["options"]
    assert options.activate_cross_sections is True


def test_convert_case_can_disable_cross_sections(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_convert_network_case(input_dir: Path, output_dir: Path, options):
        captured["options"] = options
        return object()

    monkeypatch.setattr(api, "convert_network_case", _fake_convert_network_case)

    api.convert_case("in", "out", model_name="demo", activate_cross_sections=False)

    options = captured["options"]
    assert options.activate_cross_sections is False


def test_convert_case_propagates_test_duration(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_convert_network_case(input_dir: Path, output_dir: Path, options):
        captured["options"] = options
        return object()

    monkeypatch.setattr(api, "convert_network_case", _fake_convert_network_case)

    api.convert_case("in", "out", model_name="demo", test_duration_seconds=900)

    options = captured["options"]
    assert options.test_duration_seconds == 900


def test_convert_case_propagates_morphodynamics_flag(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_convert_network_case(input_dir: Path, output_dir: Path, options):
        captured["options"] = options
        return object()

    monkeypatch.setattr(api, "convert_network_case", _fake_convert_network_case)

    api.convert_case("in", "out", model_name="demo", activate_morphodynamics=True)

    options = captured["options"]
    assert options.activate_morphodynamics is True


def test_audit_structure_parameter_warnings_delegates(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _Sentinel:
        pass

    sentinel = _Sentinel()

    def _fake_audit(output_dir: Path, model_name: str | None = None):
        captured["output_dir"] = output_dir
        captured["model_name"] = model_name
        return sentinel

    monkeypatch.setattr(api, "audit_structure_warnings", _fake_audit)

    result = api.audit_structure_parameter_warnings("out", model_name="demo")

    assert result is sentinel
    assert captured["output_dir"] == Path("out")
    assert captured["model_name"] == "demo"
