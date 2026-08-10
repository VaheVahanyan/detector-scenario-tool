from __future__ import annotations

from dataclasses import dataclass

from detector_scenario_tool.i18n import tr
from detector_scenario_tool.utils.labels import category_short, message_code, message_label
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
    #: Repeat period in ms for a cyclic send, so the view can mark the cadence. 0 means one shot.
    repeat_period_ms: int = 0


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
                    repeat_period_ms=(
                        step.cyclic.period_ms if step.repeats else 0
                    ),
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
                    title=tr("timeline.wait"),
                    subtitle=tr("scenario.step.ms", value=step.delay_ms),
                    tooltip=f'{tr("timeline.wait")} {tr("scenario.step.ms", value=step.delay_ms)}',
                    status=row_statuses.get(row_index, "neutral"),
                )
            )
            cursor_ms += duration_ms

    return TimelineBuildResult(items=items, total_duration_ms=cursor_ms)


def _build_send_titles(step: SendMessageStep) -> tuple[str, str, str]:
    if step.message is None or step.message.msg_id is None:
        return tr("timeline.send"), "", tr("label.no_message")

    title = message_code(step.message.category, step.message.msg_id)
    subtitle = ""
    tooltip = message_label(step.message.category, step.message.msg_id, step.message.name)
    if step.repeats:
        tooltip += " | " + tr(
            "timeline.repeats_every", seconds=step.cyclic.period_ms // 1000
        )

    return title, subtitle, tooltip


def _build_wait_ts_titles(step: WaitForTsStep) -> tuple[str, str, str]:
    if step.expected is None or step.expected.msg_id is None:
        return f"{category_short('TS')} ?", "", tr("label.no_message")

    title = message_code(step.expected.category, step.expected.msg_id)
    subtitle = ""
    tooltip = message_label(step.expected.category, step.expected.msg_id, step.expected.name)

    if step.expected.msg_id == 0x0201 and step.bind_to_previous_ku:
        tooltip += " | " + tr("timeline.ack_for_previous", category=category_short("KU"))

    return title, subtitle, tooltip
