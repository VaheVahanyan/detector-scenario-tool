from __future__ import annotations

import os

# Qt must be told to run headless before PySide6 is imported anywhere.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from detector_scenario_tool.domain.scenario import (
    AckPolicy,
    MessageRef,
    ScenarioDocument,
    ScenarioMetadata,
    SendMessageStep,
    StepKind,
    ValidationProfile,
    WaitForTsStep,
)
from detector_scenario_tool.protocol.catalog import ProtocolCatalog
from message_ids import STATUS_REQ, TM_ACK


@pytest.fixture(autouse=True)
def restore_language():
    """The active language is process-wide state.

    A test that switches to English and returns leaves every later test reading English strings,
    which shows up as a puzzling failure somewhere unrelated.
    """
    from detector_scenario_tool.i18n import get_language, set_language

    before = get_language()
    yield
    set_language(before)


@pytest.fixture
def catalog() -> ProtocolCatalog:
    return ProtocolCatalog()


@pytest.fixture
def empty_document() -> ScenarioDocument:
    return ScenarioDocument(
        schema_version=1,
        metadata=ScenarioMetadata(name="test scenario"),
        validation=ValidationProfile(),
        steps=[],
    )


@pytest.fixture
def make_send_step():
    """Build a SEND step without going through the UI."""

    def _make(
            category: str = "KU",
            msg_id: int = STATUS_REQ,
            name: str = "",
            payload: dict | None = None,
            step_id: str = "s1",
            ack_policy: AckPolicy = AckPolicy.EXPECT_ACK,
            ack_timeout_ms: int | None = 1000,
    ) -> SendMessageStep:
        kind = StepKind.SEND_KU if category == "KU" else StepKind.SEND_KT
        return SendMessageStep(
            id=step_id,
            kind=kind,
            message=MessageRef(category=category, msg_id=msg_id, name=name),
            payload=dict(payload or {}),
            ack_policy=ack_policy,
            ack_timeout_ms=ack_timeout_ms,
        )

    return _make


@pytest.fixture
def make_wait_ts_step():
    def _make(
            msg_id: int = TM_ACK,
            step_id: str = "w1",
            timeout_ms: int = 1000,
            bind_to_previous_ku: bool = True,
            require_ack_ok: bool = True,
    ) -> WaitForTsStep:
        return WaitForTsStep(
            id=step_id,
            kind=StepKind.WAIT_FOR_TS,
            expected=MessageRef(category="TS", msg_id=msg_id, name=""),
            timeout_ms=timeout_ms,
            bind_to_previous_ku=bind_to_previous_ku,
            require_ack_ok=require_ack_ok,
        )

    return _make
