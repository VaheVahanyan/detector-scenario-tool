"""Which widget edits which message's payload.

Every sendable message gets a `GenericPayloadEditor` built from its definition. Register an
override here only when a message genuinely needs a bespoke layout — the generic form is the
default, so a new message costs no UI code.
"""

from __future__ import annotations

from typing import Callable

from detector_scenario_tool.protocol import registry
from detector_scenario_tool.protocol.fields import MessageDef
from detector_scenario_tool.ui.editors.generic_payload_editor import GenericPayloadEditor
from detector_scenario_tool.ui.editors.payload_editor_base import PayloadEditorBase
from detector_scenario_tool.ui.widgets.input_behaviour import apply_deferred_commit

EditorFactory = Callable[[MessageDef], PayloadEditorBase]

#: (category, msg_id) -> factory. Empty today: the generic editor covers all 19 sendable messages.
_OVERRIDES: dict[tuple[str, int], EditorFactory] = {}


def register_editor(category: str, msg_id: int, factory: EditorFactory) -> None:
    _OVERRIDES[(category, msg_id)] = factory


def build_payload_editor_registry() -> dict[tuple[str, int], PayloadEditorBase]:
    editors: dict[tuple[str, int], PayloadEditorBase] = {}

    for spec in registry.all_messages():
        if not spec.sendable:
            continue

        key = (spec.category, spec.msg_id)
        factory = _OVERRIDES.get(key, GenericPayloadEditor)
        editor = factory(spec)
        apply_deferred_commit(editor)
        editors[key] = editor

    return editors
