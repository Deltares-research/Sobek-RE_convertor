from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .runtime_validation import select_dia_file


WARNING_PATTERN = re.compile(
    r"The (?P<parameter>crest width|gate opening width) for '(?P<structure_id>[^']+)' "
    r"is changed from\s*(?P<from_value>-?\d+(?:\.\d+)?) into\s*(?P<to_value>-?\d+(?:\.\d+)?)\."
)


@dataclass(frozen=True)
class StructureWarningSummary:
    structure_id: str
    parameter: str
    from_value: float
    to_value: float
    count: int


@dataclass(frozen=True)
class StructureWarningAuditResult:
    success: bool
    message: str
    dia_file: Path | None
    total_events: int
    summaries: tuple[StructureWarningSummary, ...]


def audit_structure_warnings(output_dir: Path, model_name: str | None = None) -> StructureWarningAuditResult:
    dflowfm_dir = output_dir / "dflowfm"
    if not dflowfm_dir.exists():
        return StructureWarningAuditResult(
            success=False,
            message="Missing dflowfm directory in output.",
            dia_file=None,
            total_events=0,
            summaries=(),
        )

    dia_file = select_dia_file(dflowfm_dir, model_name=model_name)
    if dia_file is None:
        return StructureWarningAuditResult(
            success=False,
            message="No .dia file found in output/dflowfm.",
            dia_file=None,
            total_events=0,
            summaries=(),
        )

    text = dia_file.read_text(encoding="utf-8", errors="ignore")
    counts: dict[tuple[str, str, float, float], int] = {}

    for line in text.splitlines():
        # DIMR can repeat FM warnings prefixed with "kernel:"; skip mirrored lines.
        if "kernel:" in line:
            continue

        match = WARNING_PATTERN.search(line)
        if match is None:
            continue

        key = (
            match.group("structure_id"),
            match.group("parameter"),
            float(match.group("from_value")),
            float(match.group("to_value")),
        )
        counts[key] = counts.get(key, 0) + 1

    summaries = tuple(
        StructureWarningSummary(
            structure_id=structure_id,
            parameter=parameter,
            from_value=from_value,
            to_value=to_value,
            count=count,
        )
        for (structure_id, parameter, from_value, to_value), count in sorted(counts.items())
    )
    total_events = sum(item.count for item in summaries)

    message = f"Found {total_events} structure-parameter warning event(s) across {len(summaries)} unique adjustment(s)."
    return StructureWarningAuditResult(
        success=True,
        message=message,
        dia_file=dia_file,
        total_events=total_events,
        summaries=summaries,
    )
