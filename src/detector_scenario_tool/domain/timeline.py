from __future__ import annotations

from dataclasses import dataclass

from detector_scenario_tool.domain.scenario import (
    ScenarioDocument,
    SendMessageStep,
    WaitForTsStep,
    WaitTimeStep,
)

DEFAULT_KU_TX_DURATION_MS = 120
DEFAULT_KT_TX_DURATION_MS = 120


@dataclass
class TimelineItem:
    step_id: str
    row_index: int
    lane: str  # "tx" | "rx" | "wait"
    start_ms: int
    duration_ms: int
    title: str
    subtitle: str
    tooltip: str
    status: str  # "neutral" | "ok" | "error" | "warning" | "pending"


@dataclass
class TimelineBuildResult:
    items: list[TimelineItem]
    total_duration_ms: int


def build_timeline(
        document: ScenarioDocument,
        row_statuses: dict[int, str] | None = None,
) -> TimelineBuildResult:
    items: list[TimelineItem] = []
    cursor_ms = 0
    row_statuses = row_statuses or {}

    for row_index, step in enumerate(document.steps):
        if isinstance(step, SendMessageStep):
            title, subtitle, tooltip = _build_send_titles(step)

            if step.kind.value == "send_ku":
                duration_ms = DEFAULT_KU_TX_DURATION_MS
            elif step.kind.value == "send_kt":
                duration_ms = DEFAULT_KT_TX_DURATION_MS
            else:
                duration_ms = 120

            items.append(
                TimelineItem(
                    step_id=step.id,
                    row_index=row_index,
                    lane="tx",
                    start_ms=cursor_ms,
                    duration_ms=duration_ms,
                    title=title,
                    subtitle=subtitle,
                    tooltip=tooltip,
                    status=row_statuses.get(row_index, "neutral"),
                )
            )
            cursor_ms += duration_ms

        elif isinstance(step, WaitForTsStep):
            title, subtitle, tooltip = _build_wait_ts_titles(step)
            duration_ms = max(1, step.timeout_ms)

            items.append(
                TimelineItem(
                    step_id=step.id,
                    row_index=row_index,
                    lane="rx",
                    start_ms=cursor_ms,
                    duration_ms=duration_ms,
                    title=title,
                    subtitle=subtitle,
                    tooltip=tooltip,
                    status=row_statuses.get(row_index, "neutral"),
                )
            )
            cursor_ms += duration_ms

        elif isinstance(step, WaitTimeStep):
            duration_ms = max(1, step.delay_ms)
            items.append(
                TimelineItem(
                    step_id=step.id,
                    row_index=row_index,
                    lane="wait",
                    start_ms=cursor_ms,
                    duration_ms=duration_ms,
                    title="WAIT",
                    subtitle=f"{step.delay_ms} ms",
                    tooltip=f"WAIT {step.delay_ms} ms",
                    status=row_statuses.get(row_index, "neutral"),
                )
            )
            cursor_ms += duration_ms

    return TimelineBuildResult(items=items, total_duration_ms=cursor_ms)


def _build_send_titles(step: SendMessageStep) -> tuple[str, str, str]:
    if step.message is None or step.message.msg_id is None:
        return "SEND", "", "No message"

    title = f"{_category_label(step.message.category)} {_short_msg_number(step.message.category, step.message.msg_id)}"
    subtitle = ""
    tooltip = f"{step.message.category} 0x{step.message.msg_id:04X} {step.message.name}"

    return title, subtitle, tooltip


def _build_wait_ts_titles(step: WaitForTsStep) -> tuple[str, str, str]:
    if step.expected is None or step.expected.msg_id is None:
        return "ТС ?", "", "No TS selected"

    title = f"ТС {_short_msg_number(step.expected.category, step.expected.msg_id)}"
    subtitle = ""
    tooltip = f"{step.expected.category} 0x{step.expected.msg_id:04X} {step.expected.name}"

    if step.expected.msg_id == 0x0201 and step.bind_to_previous_ku:
        tooltip += " | ACK for previous KU"

    return title, subtitle, tooltip


def _category_label(category: str) -> str:
    if category == "KU":
        return "КУ"
    if category == "KT":
        return "КТ"
    if category == "TS":
        return "ТС"
    return category


def _short_msg_number(category: str, msg_id: int) -> int:
    if category == "KU":
        return msg_id
    if category == "KT":
        return msg_id - 0x0100 + 1
    if category == "TS":
        return msg_id - 0x0200 + 1
    return msg_id
