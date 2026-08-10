from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

#: A period shorter than this is not a cadence, it is a flood.
MIN_CYCLIC_PERIOD_MS = 100


class StepKind(str, Enum):
    SEND_KU = "send_ku"
    SEND_KT = "send_kt"
    WAIT_TIME = "wait_time"
    WAIT_FOR_TS = "wait_for_ts"
    COMMENT = "comment"


class AckPolicy(str, Enum):
    NONE = "none"
    EXPECT_ACK = "expect_ack"
    OPTIONAL_ACK = "optional_ack"


@dataclass
class RetryPolicy:
    attempts: int = 1
    retry_delay_ms: int = 0
    retry_on_timeout: bool = True
    retry_on_reject: bool = False

    def __post_init__(self) -> None:
        self.attempts = max(1, int(self.attempts))
        self.retry_delay_ms = max(0, int(self.retry_delay_ms))
        self.retry_on_timeout = bool(self.retry_on_timeout)
        self.retry_on_reject = bool(self.retry_on_reject)


@dataclass
class CyclicPolicy:
    """Repeat a send for as long as the run lasts.

    Telemetry commands are pushed by the БВС for the whole observation session, so they default to
    repeating; `enabled = False` turns a step back into a single shot, which is what bench testing
    of one command needs.
    """

    enabled: bool = False
    period_ms: int = 20_000
    #: None means "until the run ends".
    max_repeats: int | None = None

    def __post_init__(self) -> None:
        self.enabled = bool(self.enabled)
        self.period_ms = max(MIN_CYCLIC_PERIOD_MS, int(self.period_ms))
        if self.max_repeats is not None:
            self.max_repeats = max(1, int(self.max_repeats))


@dataclass
class StepBase:
    id: str
    kind: StepKind
    title: str = ""
    comment: str = ""
    enabled: bool = True


@dataclass
class MessageRef:
    category: Literal["KU", "KT", "TS"]
    msg_id: int | None = None
    name: str = ""


@dataclass
class SendMessageStep(StepBase):
    message: MessageRef | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    ack_policy: AckPolicy = AckPolicy.NONE
    ack_timeout_ms: int | None = None
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    #: None for messages that are never repeated; the protocol layer supplies the default.
    cyclic: CyclicPolicy | None = None

    def __post_init__(self) -> None:
        if self.ack_timeout_ms is not None:
            self.ack_timeout_ms = max(0, int(self.ack_timeout_ms))

        if not isinstance(self.retry, RetryPolicy):
            self.retry = RetryPolicy()

        if self.cyclic is not None and not isinstance(self.cyclic, CyclicPolicy):
            self.cyclic = CyclicPolicy()

    @property
    def repeats(self) -> bool:
        return self.cyclic is not None and self.cyclic.enabled


@dataclass
class WaitTimeStep(StepBase):
    delay_ms: int = 1000

    def __post_init__(self) -> None:
        self.delay_ms = max(0, int(self.delay_ms))


@dataclass
class WaitForTsStep(StepBase):
    expected: MessageRef | None = None
    timeout_ms: int = 1000
    match: dict[str, Any] = field(default_factory=dict)

    bind_to_previous_ku: bool = False
    ack_for_msg_id: int | None = None
    require_ack_ok: bool = False

    def __post_init__(self) -> None:
        self.timeout_ms = max(0, int(self.timeout_ms))
        self.bind_to_previous_ku = bool(self.bind_to_previous_ku)
        self.require_ack_ok = bool(self.require_ack_ok)

        if self.ack_for_msg_id is not None:
            self.ack_for_msg_id = int(self.ack_for_msg_id)

        if self.match is None:
            self.match = {}
        else:
            self.match = dict(self.match)


@dataclass
class CommentStep(StepBase):
    text: str = ""


ScenarioStep = SendMessageStep | WaitTimeStep | WaitForTsStep | CommentStep


@dataclass
class ValidationProfile:
    safe_mode: bool = False
    strict_ack_checks: bool = True
    strict_mode_transition_checks: bool = True
    strict_timeout_checks: bool = False


@dataclass
class ScenarioMetadata:
    name: str
    author: str = ""
    description: str = ""


@dataclass
class ScenarioDocument:
    schema_version: int
    metadata: ScenarioMetadata
    validation: ValidationProfile
    steps: list[ScenarioStep]
    #: Messages the user defined for this scenario; registered into the protocol registry on load
    #: so the rest of the tool treats them exactly like catalogue messages.
    custom_messages: list = field(default_factory=list)
    #: Built-in messages this scenario hides, as (category, msg_id). Restoring one is simply
    #: removing it from here — the specification's own definition is never overwritten.
    suppressed_messages: list = field(default_factory=list)
    #: Populated when an older file was upgraded on load; surfaced in the warnings panel so the
    #: user finds out that something needs re-entering rather than discovering it in flight.
    migration_notes: list = field(default_factory=list)
