from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import re
import shlex
import statistics

from ...models import BranchTransportParameters, LayerCompositionSample, MorphodynamicsSummary
from .records import load_records


@dataclass(frozen=True)
class _GrainpConfiguration:
    fractions: tuple[float, ...]
    layer_composition: tuple[LayerCompositionSample, ...]
    underlayer_count: int | None
    underlayer_thickness_m: float | None
    sediment_parameters: tuple[tuple[str, str], ...]
    morphology_parameters: tuple[tuple[str, str], ...]
    graded_sediment_options: tuple[tuple[str, str], ...]
    graded_sediment_parameters: tuple[tuple[str, str], ...]
    graded_sediment_flags: tuple[str, ...]


def read_morphodynamics_summary(input_dir: Path) -> tuple[MorphodynamicsSummary, list[str]]:
    warnings: list[str] = []

    mpin_records = load_records(input_dir, "DEFICN", {"MPIN"})
    sbst_records = load_records(input_dir, "DEFSUB", {"SBST"})
    trns_records = load_records(input_dir, "DEFTRN", {"TRNS"})

    branch_ids = {
        record.attrs.get("ci", "")
        for record in mpin_records
        if record.attrs.get("ci") and record.attrs.get("ci") != "-1"
    }
    has_morphology_switch = any(record.attrs.get("md") == "1" for record in sbst_records)
    grain_size_samples = _extract_grain_size_samples(mpin_records)
    representative_d50_m = statistics.median(grain_size_samples) if grain_size_samples else None
    grainp_config = _read_grainp_configuration(input_dir)
    sediment_fractions = grainp_config.fractions or _derive_sediment_fractions(grain_size_samples)
    branch_samples = _extract_branch_grain_size_samples(mpin_records)
    branch_composition = _compute_layer_branch_composition(
        grainp_config.layer_composition,
        grainp_config.underlayer_count,
    ) or _compute_branch_composition(branch_samples, sediment_fractions)

    if branch_ids and not has_morphology_switch:
        warnings.append("MPIN grain-size initialization found, but DEFSUB does not indicate active morphology switch.")

    summary = MorphodynamicsSummary(
        branch_count_with_grainsize=len(branch_ids),
        has_morphology_switch=has_morphology_switch,
        representative_d50_m=representative_d50_m,
        sediment_fractions_d50_m=sediment_fractions,
        grain_size_sample_count=len(grain_size_samples),
        sediment_parameters=grainp_config.sediment_parameters,
        morphology_parameters=grainp_config.morphology_parameters,
        graded_sediment_options=grainp_config.graded_sediment_options,
        graded_sediment_parameters=grainp_config.graded_sediment_parameters,
        graded_sediment_flags=grainp_config.graded_sediment_flags,
        transport_parameters=_read_transport_parameters(trns_records),
        branch_composition=branch_composition,
        underlayer_count=grainp_config.underlayer_count,
        underlayer_thickness_m=grainp_config.underlayer_thickness_m,
        layer_composition=grainp_config.layer_composition,
    )
    return summary, warnings


def _read_transport_parameters(records: list) -> tuple[BranchTransportParameters, ...]:
    parameters: list[BranchTransportParameters] = []
    for record in records:
        branch_id = record.attrs.get("ci")
        if not branch_id or branch_id == "-1":
            continue

        coefficients: list[tuple[str, float]] = []
        for key in ("au", "bu", "gu", "tc", "rf", "va", "e1", "e2", "e3", "e4", "e5", "e6", "e7"):
            value = _to_float(record.attrs.get(key, ""))
            if value is None or value >= 1.0e8:
                continue
            coefficients.append((key.upper(), value))

        parameters.append(
            BranchTransportParameters(
                branch_id=branch_id,
                formula_type=_to_int(record.attrs.get("ty", "")),
                calibration_factor=_to_float(record.attrs.get("mu", "")),
                coefficients=tuple(coefficients),
            )
        )

    return tuple(parameters)


def _read_grainp_configuration(input_dir: Path) -> _GrainpConfiguration:
    path = input_dir / "GRAINP.TXT"
    if not path.exists():
        return _GrainpConfiguration(tuple(), tuple(), None, None, tuple(), tuple(), tuple(), tuple(), tuple())

    branch_number_map = _read_branch_number_map(input_dir)
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    fractions: tuple[float, ...] = tuple()
    samples: list[LayerCompositionSample] = []
    underlayer_count: int | None = None
    underlayer_thickness_m: float | None = None
    sediment_parameters: dict[str, str] = {}
    morphology_parameters: dict[str, str] = {}
    graded_sediment_options: dict[str, str] = {}
    graded_sediment_parameters: dict[str, str] = {}
    graded_sediment_flags: set[str] = set()
    current_section: str | None = None
    current_branch_id: str | None = None
    current_chainage: float | None = None
    current_layers: dict[int, tuple[float, ...]] = {}

    def flush_current_sample() -> None:
        nonlocal current_branch_id, current_chainage, current_layers
        if current_branch_id is None or current_chainage is None or not current_layers:
            return

        max_layer = max(current_layers)
        layer_weights = tuple(current_layers.get(layer_idx, tuple()) for layer_idx in range(1, max_layer + 1))
        samples.append(
            LayerCompositionSample(
                branch_id=current_branch_id,
                chainage=current_chainage,
                layer_weights=layer_weights,
            )
        )

    for raw_line in lines:
        line = raw_line.split("!", 1)[0].strip()
        if not line:
            continue

        tokens = shlex.split(line)
        if tokens and tokens[0].startswith("$"):
            keyword = tokens[0].upper()
            current_section = keyword if keyword in {"$SEDPAR", "$MORPAR", "$GSOPT", "$GSPAR"} else None

        if tokens and tokens[0].upper() == "$FRACT":
            bounds = _to_float_tuple(tokens[1:])
            if len(bounds) >= 2:
                fractions = tuple(math.sqrt(bounds[idx] * bounds[idx + 1]) for idx in range(len(bounds) - 1))
            continue

        if current_section in {"$SEDPAR", "$MORPAR", "$GSOPT", "$GSPAR"}:
            payload = line.removeprefix(current_section).strip()
            if payload:
                _read_parameter_payload(
                    payload,
                    sediment_parameters,
                    morphology_parameters,
                    graded_sediment_options,
                    graded_sediment_parameters,
                    graded_sediment_flags,
                    current_section,
                )
                if line.upper().startswith("$GSOPT"):
                    continue

        count_match = re.match(r"^NUNLAY\s*=\s*(\d+)\b", line, flags=re.IGNORECASE)
        if count_match:
            underlayer_count = int(count_match.group(1))
            if current_section == "$GSOPT":
                graded_sediment_options["NUNLAY"] = count_match.group(1)
            continue

        thickness_match = re.match(r"^DZUNLA\s*=\s*([-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?)\b", line, flags=re.IGNORECASE)
        if thickness_match:
            underlayer_thickness_m = float(thickness_match.group(1))
            if current_section == "$GSPAR":
                graded_sediment_parameters["DZUNLA"] = thickness_match.group(1)
            continue

        if current_section == "$GSOPT" and re.match(r"^[A-Z][A-Z0-9_]*$", line, flags=re.IGNORECASE):
            graded_sediment_flags.add(line.upper())
            continue

        gsinit_match = re.match(
            r"^\$GSINIT\s+BRANCH\s+(\d+)\s+AT\s+([-+]?\d*\.?\d+(?:[Ee][-+]?\d+)?)\b",
            line,
            flags=re.IGNORECASE,
        )
        if gsinit_match:
            flush_current_sample()
            branch_number = int(gsinit_match.group(1))
            current_branch_id = branch_number_map.get(branch_number, str(branch_number))
            current_chainage = float(gsinit_match.group(2))
            current_layers = {}
            continue

        laynum_match = re.match(r"^LAYNUM\s*=\s*(\d+)\s+(.+)$", line, flags=re.IGNORECASE)
        if laynum_match and current_branch_id is not None:
            layer_idx = int(laynum_match.group(1))
            weights = _to_float_tuple(shlex.split(laynum_match.group(2)))
            if weights:
                current_layers[layer_idx] = weights

    flush_current_sample()
    return _GrainpConfiguration(
        fractions=fractions,
        layer_composition=tuple(samples),
        underlayer_count=underlayer_count,
        underlayer_thickness_m=underlayer_thickness_m,
        sediment_parameters=tuple(sorted(sediment_parameters.items())),
        morphology_parameters=tuple(sorted(morphology_parameters.items())),
        graded_sediment_options=tuple(sorted(graded_sediment_options.items())),
        graded_sediment_parameters=tuple(sorted(graded_sediment_parameters.items())),
        graded_sediment_flags=tuple(sorted(graded_sediment_flags)),
    )


def _read_parameter_payload(
    payload: str,
    sediment_parameters: dict[str, str],
    morphology_parameters: dict[str, str],
    graded_sediment_options: dict[str, str],
    graded_sediment_parameters: dict[str, str],
    graded_sediment_flags: set[str],
    section: str,
) -> None:
    target = {
        "$SEDPAR": sediment_parameters,
        "$MORPAR": morphology_parameters,
        "$GSOPT": graded_sediment_options,
        "$GSPAR": graded_sediment_parameters,
    }[section]
    for key, value in re.findall(r"\b([A-Z][A-Z0-9_]*)\s*=\s*([^\s!]+)", payload, flags=re.IGNORECASE):
        target[key.upper()] = value

    if section != "$GSOPT" or "=" in payload:
        return

    for token in shlex.split(payload):
        if re.match(r"^[A-Z][A-Z0-9_]*$", token, flags=re.IGNORECASE):
            graded_sediment_flags.add(token.upper())


def _read_branch_number_map(input_dir: Path) -> dict[int, str]:
    for path in sorted(input_dir.glob("DEFTOP.*")):
        if not path.is_file():
            continue

        branch_ids: list[str] = []
        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line.startswith("BRCH "):
                continue
            tokens = shlex.split(line)
            for idx, token in enumerate(tokens):
                if token.lower() == "id" and idx + 1 < len(tokens):
                    branch_ids.append(tokens[idx + 1])
                    break

        if branch_ids:
            return {idx: branch_id for idx, branch_id in enumerate(branch_ids, start=1)}

    return {}


def _to_float_tuple(tokens: list[str]) -> tuple[float, ...]:
    values: list[float] = []
    for token in tokens:
        try:
            values.append(float(token))
        except ValueError:
            continue
    return tuple(values)


def _to_float(raw: str) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _to_int(raw: str) -> int | None:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _compute_layer_branch_composition(
    samples: tuple[LayerCompositionSample, ...],
    underlayer_count: int | None,
) -> tuple[tuple[str, tuple[float, ...]], ...]:
    if not samples:
        return tuple()

    top_layer_idx = max((underlayer_count or 1) - 1, 0)
    by_branch: dict[str, list[tuple[float, ...]]] = {}
    for sample in samples:
        if top_layer_idx >= len(sample.layer_weights):
            continue
        weights = sample.layer_weights[top_layer_idx]
        if weights:
            by_branch.setdefault(sample.branch_id, []).append(weights)

    composition: list[tuple[str, tuple[float, ...]]] = []
    for branch_id in sorted(by_branch.keys()):
        branch_weights = by_branch[branch_id]
        fraction_count = len(branch_weights[0])
        averaged = tuple(
            sum(weights[idx] for weights in branch_weights if len(weights) == fraction_count) / len(branch_weights)
            for idx in range(fraction_count)
        )
        composition.append((branch_id, averaged))

    return tuple(composition)


def _extract_grain_size_samples(mpin_records: list) -> list[float]:
    d50_values: list[float] = []
    for record in mpin_records:
        raw = record.attrs.get("c5")
        if raw is None:
            raw = ""
        value = _to_grainsize(raw)
        if value is not None:
            d50_values.append(value)

        for table in record.tables:
            for row in table:
                sample = _sample_from_row(row)
                if sample is not None:
                    d50_values.append(sample)

    return d50_values


def _extract_branch_grain_size_samples(mpin_records: list) -> dict[str, list[float]]:
    per_branch: dict[str, list[float]] = {}
    for record in mpin_records:
        branch_id = record.attrs.get("ci")
        if not branch_id or branch_id == "-1":
            continue

        values: list[float] = []
        attr_value = _to_grainsize(record.attrs.get("c5", ""))
        if attr_value is not None:
            values.append(attr_value)

        for table in record.tables:
            for row in table:
                sample = _sample_from_row(row)
                if sample is not None:
                    values.append(sample)

        if values:
            per_branch[branch_id] = values

    return per_branch


def _sample_from_row(row: tuple[str, ...]) -> float | None:
    if len(row) < 2:
        return None

    candidates = [_to_grainsize(token) for token in row[1:]]
    clean = [value for value in candidates if value is not None]
    if not clean:
        return None

    # MPIN rows contain multiple grain-size descriptors; use the smallest
    # valid class-scale value as a stable D50 proxy.
    return min(clean)


def _to_grainsize(raw: str) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None

    if value <= 0.0:
        return None
    if value >= 1.0e8:
        return None
    # Grain diameters in meters; filter physically implausible outliers.
    if value > 0.5:
        return None
    return value


def _derive_sediment_fractions(samples: list[float]) -> tuple[float, ...]:
    if not samples:
        return tuple()

    sorted_values = sorted(samples)
    percentiles = (5.0, 20.0, 35.0, 50.0, 65.0, 80.0, 95.0)
    candidates = [_percentile(sorted_values, p) for p in percentiles]

    unique: list[float] = []
    for value in candidates:
        rounded = round(value, 7)
        if rounded <= 0.0:
            continue
        if unique and abs(unique[-1] - rounded) < 1e-7:
            continue
        unique.append(rounded)

    if not unique:
        unique = [round(statistics.median(sorted_values), 7)]

    return tuple(unique)


def _compute_branch_composition(
    branch_samples: dict[str, list[float]],
    fractions: tuple[float, ...],
) -> tuple[tuple[str, tuple[float, ...]], ...]:
    if not branch_samples or not fractions:
        return tuple()

    composition: list[tuple[str, tuple[float, ...]]] = []
    for branch_id in sorted(branch_samples.keys()):
        samples = branch_samples[branch_id]
        counts = [0 for _ in fractions]
        for sample in samples:
            idx = min(range(len(fractions)), key=lambda i: abs(fractions[i] - sample))
            counts[idx] += 1

        total = sum(counts)
        if total <= 0:
            continue
        weights = tuple(count / total for count in counts)
        composition.append((branch_id, weights))

    return tuple(composition)


def _percentile(sorted_values: list[float], percentile: float) -> float:
    if len(sorted_values) == 1:
        return sorted_values[0]

    rank = (len(sorted_values) - 1) * percentile / 100.0
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    weight = rank - low
    return sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight
