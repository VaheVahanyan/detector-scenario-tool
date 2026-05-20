from __future__ import annotations

from enum import Enum


class StepKind(str, Enum):
    SEND_KU = "send_ku"
    SEND_KT = "send_kt"
    WAIT_FOR_TS = "wait_for_ts"
    WAIT_TIME = "wait_time"
    COMMENT = "comment"
    WAIT_FOR_TS = "wait_for_ts"


class AckPolicy(str, Enum):
    NONE = "none"
    EXPECT_ACK = "expect_ack"
    OPTIONAL_ACK = "optional_ack"


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
