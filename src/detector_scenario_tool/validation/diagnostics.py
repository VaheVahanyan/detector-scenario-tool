from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class Diagnostic:
    """A finding about one scenario step.

    `code` plus `params` rather than a pre-formatted string, so the message can be rendered in the
    current UI language and re-rendered when the language changes. Values in `params` whose key
    ends in `_key` are themselves translation keys and get resolved before formatting.
    """

    severity: Severity
    step_index: int
    code: str
    params: dict[str, Any] = field(default_factory=dict)
    #: Optional pre-rendered text; only used when no translation exists for `code`.
    message: str = ""
