from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class Diagnostic:
    severity: Severity
    step_index: int
    code: str
    message: str
