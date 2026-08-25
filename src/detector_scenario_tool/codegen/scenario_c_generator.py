from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from detector_scenario_tool.domain.scenario import (
    AckPolicy,
    CommentStep,
    RetryPolicy,
    ScenarioDocument,
    SendMessageStep,
    WaitForTsStep,
    WaitTimeStep,
)
from detector_scenario_tool.protocol.packers import pack_message_payload


@dataclass
class GeneratedScenarioFiles:
    header_filename: str
    source_filename: str
    meta_filename: str
    contract_filename: str
    header_text: str
    source_text: str
    meta_text: str
    contract_text: str


def generate_scenario_c_files(
        document: ScenarioDocument,
        header_filename: str = "scenario_generated.h",
        source_filename: str = "scenario_generated.c",
        meta_filename: str = "scenario_generated.meta.txt",
        contract_filename: str = "scenario_runtime_contract.txt",
) -> GeneratedScenarioFiles:
    include_guard = _make_include_guard(header_filename)

    header_text = _generate_header_text(include_guard)
    source_text = _generate_source_text(document, header_filename)
    meta_text = _generate_meta_text(document, header_filename, source_filename)
    contract_text = _generate_contract_text(header_filename, source_filename)

    return GeneratedScenarioFiles(
        header_filename=header_filename,
        source_filename=source_filename,
        meta_filename=meta_filename,
        contract_filename=contract_filename,
        header_text=header_text,
        source_text=source_text,
        meta_text=meta_text,
        contract_text=contract_text,
    )


def save_generated_scenario_files(
        document: ScenarioDocument,
        output_dir: str | Path,
        header_filename: str = "scenario_generated.h",
        source_filename: str = "scenario_generated.c",
        meta_filename: str = "scenario_generated.meta.txt",
        contract_filename: str = "scenario_runtime_contract.txt",
) -> GeneratedScenarioFiles:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = generate_scenario_c_files(
        document=document,
        header_filename=header_filename,
        source_filename=source_filename,
        meta_filename=meta_filename,
        contract_filename=contract_filename,
    )

    (output_dir / files.header_filename).write_text(files.header_text, encoding="utf-8")
    (output_dir / files.source_filename).write_text(files.source_text, encoding="utf-8")
    (output_dir / files.meta_filename).write_text(files.meta_text, encoding="utf-8")
    (output_dir / files.contract_filename).write_text(files.contract_text, encoding="utf-8")

    return files


def _generate_header_text(include_guard: str) -> str:
    return f"""#pragma once

#ifndef {include_guard}
#define {include_guard}

#include <stdint.h>

#include "scenario_runtime.h"

#ifdef __cplusplus
extern "C" {{
#endif

/* Executes the linear scenario once. */
scenario_result_t scenario_run_once(void);

/*
 * Messages the runtime must keep re-sending for as long as the scenario runs.
 * The linear sequence sends each of them once; repeating them is the board's job, because the
 * board is what holds the cadence in flight.
 */
extern const scenario_cyclic_t scenario_cyclic_table[];
extern const uint32_t          scenario_cyclic_count;

#ifdef __cplusplus
}}
#endif

#endif /* {include_guard} */
"""


def _cyclic_entries(document: ScenarioDocument) -> list[tuple[int, SendMessageStep]]:
    return [
        (index, step)
        for index, step in enumerate(document.steps, start=1)
        if isinstance(step, SendMessageStep)
        and getattr(step, "enabled", True)
        and step.repeats
        and step.message is not None
        and step.message.msg_id is not None
    ]


def _emit_cyclic_table(document: ScenarioDocument) -> list[str]:
    entries = _cyclic_entries(document)

    lines = [
        "/*",
        " * Periodic sends. The runtime should start these when the scenario starts and stop them",
        " * when it ends; payload bytes are the ones the corresponding linear step carries.",
        " */",
        "const scenario_cyclic_t scenario_cyclic_table[] =",
        "{",
    ]

    if not entries:
        # A zero-length array is not valid C, so keep one inert entry and a count of zero.
        lines.append("    { 0u, 0u, 0u }, /* none: scenario_cyclic_count is 0 */")
    else:
        for index, step in entries:
            policy = step.cyclic
            max_repeats = 0 if policy.max_repeats is None else policy.max_repeats
            lines.append(
                f"    {{ 0x{step.message.msg_id:04X}u, {policy.period_ms}u, {max_repeats}u }},"
                f" /* step {index} */"
            )

    lines.append("};")
    lines.append("")
    lines.append(f"const uint32_t scenario_cyclic_count = {len(entries)}u;")
    lines.append("")
    return lines


def _generate_source_text(document: ScenarioDocument, header_filename: str) -> str:
    body_lines: list[str] = []
    emitted_steps = 0

    for step_index, step in enumerate(document.steps, start=1):
        if not getattr(step, "enabled", True):
            body_lines.extend(_emit_disabled_step_comment(step_index, step))
            continue

        if isinstance(step, SendMessageStep):
            body_lines.extend(_emit_send_step(step_index, step))
            emitted_steps += 1
        elif isinstance(step, WaitTimeStep):
            body_lines.extend(_emit_wait_time_step(step_index, step))
            emitted_steps += 1
        elif isinstance(step, WaitForTsStep):
            body_lines.extend(_emit_wait_for_ts_runtime_handled_comment(step_index, step))
        elif isinstance(step, CommentStep):
            body_lines.extend(_emit_comment_step_comment(step_index, step))
        else:
            body_lines.extend(_emit_unsupported_step_comment(step_index, step))

    if emitted_steps == 0:
        body_lines.extend(
            [
                "    /* no enabled executable steps */",
                "    scenario_log_scenario_done();",
                "    return SCENARIO_OK;",
            ]
        )

    body = "\n".join(body_lines).rstrip()

    cyclic_table = "\n".join(_emit_cyclic_table(document))

    return f"""#include <stdint.h>

#include "{header_filename}"
#include "scenario_runtime.h"

{cyclic_table}
scenario_result_t scenario_run_once(void)
{{
    scenario_result_t rc;

    scenario_log_scenario_started();

{body}

    scenario_log_scenario_done();
    return SCENARIO_OK;
}}
"""


def _custom_meta(step: SendMessageStep) -> str:
    """Mark a user-defined message: the board has no field layout for it, only raw bytes."""
    from detector_scenario_tool.protocol import registry

    if step.message is None or step.message.msg_id is None:
        return ""
    spec = registry.find(step.message.category, step.message.msg_id)
    return "custom=true | " if spec is not None and spec.custom else ""


def _cyclic_meta(step: SendMessageStep) -> str:
    """Repeats are board-side behaviour, so the meta file has to say so explicitly."""
    if not step.repeats:
        return "cyclic=false | "
    repeats = "unlimited" if step.cyclic.max_repeats is None else step.cyclic.max_repeats
    return f"cyclic=true | cyclic_period_ms={step.cyclic.period_ms} | cyclic_max={repeats} | "


def _generate_meta_text(
        document: ScenarioDocument,
        header_filename: str,
        source_filename: str,
) -> str:
    scenario_name = getattr(document.metadata, "name", "") or "Untitled scenario"
    total_steps = len(document.steps)
    enabled_steps = sum(1 for step in document.steps if getattr(step, "enabled", True))
    disabled_steps = total_steps - enabled_steps

    used_send_ids: list[str] = []
    used_ui_wait_ids: list[str] = []
    exported_step_count = 0

    step_lines: list[str] = []

    for step_index, step in enumerate(document.steps, start=1):
        enabled = getattr(step, "enabled", True)
        enabled_text = "enabled" if enabled else "disabled"
        comment = _get_step_comment(step)

        if isinstance(step, SendMessageStep):
            exported_to_c = enabled
            if step.message is None or step.message.msg_id is None:
                line = (
                    f"{step_index:03d} | {enabled_text} | SEND | invalid message | "
                    f"exported_to_c={_bool_text(exported_to_c)}"
                )
            else:
                payload = pack_message_payload(step.message.category, step.message.msg_id, step.payload or {})
                payload_len = len(payload)
                retry = _normalize_retry(step.retry)
                line = (
                    f"{step_index:03d} | {enabled_text} | SEND {step.message.category} "
                    f"0x{step.message.msg_id:04X} | payload_len={payload_len} | "
                    f"{_cyclic_meta(step)}{_custom_meta(step)}"
                    f"ack_policy={step.ack_policy.value} | "
                    f"ack_timeout_ms={step.ack_timeout_ms if step.ack_timeout_ms is not None else '-'} | "
                    f"attempts={retry.attempts} | "
                    f"retry_delay_ms={retry.retry_delay_ms} | "
                    f"retry_on_timeout={retry.retry_on_timeout} | "
                    f"retry_on_reject={retry.retry_on_reject} | "
                    f"exported_to_c={_bool_text(exported_to_c)}"
                )
                used_send_ids.append(f"{step.message.category} 0x{step.message.msg_id:04X}")

            if exported_to_c:
                exported_step_count += 1

        elif isinstance(step, WaitTimeStep):
            exported_to_c = enabled
            line = (
                f"{step_index:03d} | {enabled_text} | WAIT_TIME | delay_ms={step.delay_ms} | "
                f"exported_to_c={_bool_text(exported_to_c)}"
            )
            if exported_to_c:
                exported_step_count += 1

        elif isinstance(step, WaitForTsStep):
            exported_to_c = False
            if step.expected is None or step.expected.msg_id is None:
                line = (
                    f"{step_index:03d} | {enabled_text} | WAIT_FOR_TS | invalid expected message | "
                    f"ui_only=true | exported_to_c=false"
                )
            else:
                line = (
                    f"{step_index:03d} | {enabled_text} | WAIT_FOR_TS "
                    f"{step.expected.category} 0x{step.expected.msg_id:04X} | "
                    f"timeout_ms={step.timeout_ms} | "
                    f"bind_to_previous_ku={step.bind_to_previous_ku} | "
                    f"ack_for_msg_id={step.ack_for_msg_id if step.ack_for_msg_id is not None else '-'} | "
                    f"require_ack_ok={step.require_ack_ok} | "
                    f"ui_only=true | exported_to_c=false"
                )
                used_ui_wait_ids.append(f"{step.expected.category} 0x{step.expected.msg_id:04X}")

        elif isinstance(step, CommentStep):
            exported_to_c = False
            line = (
                f"{step_index:03d} | {enabled_text} | COMMENT | "
                f"ui_only=true | exported_to_c=false"
            )

        else:
            exported_to_c = False
            line = (
                f"{step_index:03d} | {enabled_text} | {type(step).__name__} | "
                f"ui_only=true | exported_to_c=false"
            )

        if comment:
            line += f" | comment={_escape_meta_text(comment)}"

        step_lines.append(line)

    unique_send_ids = sorted(set(used_send_ids))
    unique_ui_wait_ids = sorted(set(used_ui_wait_ids))

    send_ids_text = ", ".join(unique_send_ids) if unique_send_ids else "-"
    ui_wait_ids_text = ", ".join(unique_ui_wait_ids) if unique_ui_wait_ids else "-"

    lines = [
        "Generated Scenario Metadata",
        "===========================",
        "",
        f"Scenario name: {scenario_name}",
        f"Header file: {header_filename}",
        f"Source file: {source_filename}",
        "",
        f"Total steps in UI scenario: {total_steps}",
        f"Enabled steps in UI scenario: {enabled_steps}",
        f"Disabled steps in UI scenario: {disabled_steps}",
        f"Executable steps exported to C: {exported_step_count}",
        "",
        f"Used send message IDs: {send_ids_text}",
        f"UI-only WAIT_FOR_TS IDs: {ui_wait_ids_text}",
        "",
        "Step list:",
        "----------",
    ]
    lines.extend(step_lines)

    return "\n".join(lines) + "\n"


def _generate_contract_text(header_filename: str, source_filename: str) -> str:
    return f"""Scenario Runtime Contract
=========================

Protocol revision
-----------------

The identifiers in the generated tables follow **Протокол_CAN_ГС_v2_1_Спутникс**. Every control
command and every telemetry message was renumbered in that revision, so a board runtime built
against Протокол_CAN_ГС_v2 will answer ERR_MSG_ID to everything this package sends. Check the
firmware's own message table before flashing a scenario generated here.

The same revision replaced the six-byte AAh-padded form of the short control commands with their
true content lengths (0-6 bytes), so the DLC of almost every frame changed as well. There is no
compatibility mode: the generator emits v2.1 lengths only.

This generated scenario package contains:
- {header_filename}
- {source_filename}

The generated source expects that the board-side embedded project provides:
- scenario_runtime.h
- scenario_runtime.c

Architectural rule
------------------

UI scenario is richer than generated C:
- UI scenario may contain SEND, WAIT_TIME, WAIT_FOR_TS, COMMENT.
- Generated C exports only executable board-side actions:
  - SEND_KU
  - SEND_KT
  - WAIT_TIME
- WAIT_FOR_TS steps are UI-only and are NOT emitted as executable code.
- User-defined messages are emitted exactly like catalogue ones: the generated table carries the
  raw bytes, and the meta file marks the step `custom=true`. The board runtime needs no knowledge
  of them beyond the MSG_ID and the payload.
- Cyclic sends are NOT unrolled into the linear step list. A step marked `cyclic=true` in the
  meta file is sent once by the linear sequence, and the board runtime is expected to keep
  repeating it at `cyclic_period_ms` until the scenario ends. See "Cyclic sends" below.
- Board runtime is responsible for waiting for all protocol responses
  (ACK, STATUS, TELEMETRY, TEST_RESULT, etc.) after each command.

Cyclic sends
------------

Telemetry commands (КТ) are pushed repeatedly by the БВС for the whole observation session
(Протокол_CAN_ГС_v2_1_Спутникс §3, and the 20 s cadence in the algorithm description). The generated
sequence therefore sends such a message once and expects the runtime to register a periodic task:

typedef struct
{{
    uint16_t msg_id;
    uint32_t period_ms;
    uint32_t max_repeats;   /* 0 = until the scenario ends */
}} scenario_cyclic_t;

extern const scenario_cyclic_t scenario_cyclic_table[];
extern const uint32_t          scenario_cyclic_count;

The runtime should start these when the scenario starts and stop them when it ends. Payload bytes
for each entry are the ones the linear step already carries.

Required runtime API
--------------------

The generated code expects the following runtime API contract:

#define SCENARIO_MAX_PAYLOAD_LEN 6146u
#define SCENARIO_LOG_SRC        "board"

typedef enum
{{
    SCENARIO_OK = 0,

    SCENARIO_ERR_SEND = -1,
    SCENARIO_ERR_TIMEOUT = -2,
    SCENARIO_ERR_UNEXPECTED_MESSAGE = -3,
    SCENARIO_ERR_INTERNAL = -4,
    SCENARIO_ERR_BAD_ARGUMENT = -5,
    SCENARIO_ERR_RX_OVERFLOW = -6,
    SCENARIO_ERR_REJECTED = -7
}} scenario_result_t;

typedef enum
{{
    SCENARIO_ACK_NONE = 0,
    SCENARIO_ACK_EXPECT = 1,
    SCENARIO_ACK_OPTIONAL = 2
}} scenario_ack_policy_t;

scenario_result_t scenario_send_ku(uint16_t msg_id,
                                   const uint8_t *data,
                                   uint16_t len,
                                   scenario_ack_policy_t ack_policy,
                                   uint32_t ack_timeout_ms,
                                   uint8_t max_attempts,
                                   uint32_t retry_delay_ms,
                                   uint8_t retry_on_timeout,
                                   uint8_t retry_on_reject);

scenario_result_t scenario_send_kt(uint16_t msg_id,
                                   const uint8_t *data,
                                   uint16_t len,
                                   scenario_ack_policy_t ack_policy,
                                   uint32_t ack_timeout_ms,
                                   uint8_t max_attempts,
                                   uint32_t retry_delay_ms,
                                   uint8_t retry_on_timeout,
                                   uint8_t retry_on_reject);

void scenario_wait_ms(uint32_t delay_ms);

void scenario_log_tx(uint16_t msg_id,
                     const uint8_t *data,
                     uint16_t len);

void scenario_log_rx(uint16_t msg_id,
                     const uint8_t *data,
                     uint16_t len);

void scenario_log_runtime_error(uint16_t step_index,
                                scenario_result_t error_code);

void scenario_log_scenario_started(void);
void scenario_log_scenario_done(void);

Expected semantics
------------------

scenario_send_ku(...) / scenario_send_kt(...)
- Execute one full protocol-level board command.
- Runtime itself handles:
  - low-level send
  - ACK wait if required by ack_policy
  - retry logic according to:
    - ack_timeout_ms
    - max_attempts
    - retry_delay_ms
    - retry_on_timeout
    - retry_on_reject
  - waiting for all mandatory protocol responses for this command
    (for example STATUS / TELEMETRY / TEST_RESULT), if protocol requires them
- Runtime performs TX logging internally after successful low-level send.
- Runtime performs RX logging internally for received protocol responses.
- Runtime returns:
  - SCENARIO_OK on final success
  - error code on final failure

Recommended retry behavior:
- If ack_policy == SCENARIO_ACK_NONE:
  - send once
  - do not wait for ACK
- If ack_policy == SCENARIO_ACK_EXPECT:
  - send
  - wait for ACK up to ack_timeout_ms
  - retry according to retry settings
- If ack_policy == SCENARIO_ACK_OPTIONAL:
  - runtime-specific; may attempt ACK wait without making absence fatal

scenario_wait_ms(...)
- Waits for a fixed amount of time.
- Used for WAIT_TIME steps.
- Does not return an error code.

Logging expectations
--------------------

Generated code assumes protocol/event logging is available in the runtime layer.

Recommended UART log line format:

DSTLOG|v=2|src=board|ts=<ms>|dir=<tx|rx>|id=<hex4>|data=<HEX>[|can=<hex3>][|frames=<n>][|valid=0]

Examples:
DSTLOG|v=2|src=board|ts=120|dir=tx|id=0003|data=010203040506|can=0BE
DSTLOG|v=2|src=board|ts=257|dir=rx|id=0201|data=000000000000|can=3C5

Where:
- src=board for board-side runtime logs
- src=detector for detector-side runtime logs
- src=host for lines the desktop tool produced itself
- dir=tx when board sends a message
- dir=rx when board receives a protocol response
- id is message id in 4-digit hex
- data is payload hex without spaces
- can is the CAN identifier of the first frame, optional
- frames is the number of CAN frames a long message occupied, omitted when 1
- valid=0 marks a frame that could not be reassembled, omitted otherwise

v=1 lines (no can/frames/valid) are still accepted by the desktop tool.

Generated code itself should only call:
- scenario_log_scenario_started()
- scenario_log_runtime_error(...)
- scenario_log_scenario_done()

Generated code must not call scenario_log_tx()/scenario_log_rx() directly.

Execution model
---------------

The generated function is:

scenario_result_t scenario_run_once(void);

Expected behavior:
- Executes the exported board scenario once from start to finish.
- Returns SCENARIO_OK on success.
- Returns first runtime error code on failure.
- Does not contain infinite loop.
- Repeat policy is controlled by outer application logic.

User-defined messages
---------------------

A scenario may define its own messages: a MSG_ID, a length and raw content bytes, with no field
structure. They are emitted exactly like catalogue messages — the generated table carries the
bytes and the meta file marks the step `custom=true`. The runtime needs no knowledge of them
beyond the MSG_ID and the payload, and should not attempt to validate them.

Such a message may also carry its own destination and source addresses, so that a scenario can
deliberately put traffic on the bus that is not addressed to the payload. When those are present
the meta file records them; a runtime that only ever talks to one peer can ignore them.

Generation rules
----------------

1. Generated code must not use HAL / LL / CMSIS / UniCAN directly.
2. Generated code must not parse payload fields.
3. Payload is fully prepared by desktop tool.
4. Generated code exports only:
   - SEND_KU
   - SEND_KT
   - WAIT_TIME
   - the cyclic table (data only; the runtime drives it)
5. WAIT_FOR_TS remains only at UI / validation / log-matching level.
6. Generated code should contain only:
   - const scenario_cyclic_t scenario_cyclic_table[] = {{ ... }};
   - static const uint8_t payload[] = {{ ... }};
   - scenario_send_ku(...)
   - scenario_send_kt(...)
   - scenario_wait_ms(...)
   - scenario_log_scenario_started()
   - scenario_log_runtime_error(...)
   - scenario_log_scenario_done()

Recommended file split on embedded side
---------------------------------------

Manually written:
- scenario_runtime.h
- scenario_runtime.c

Generated:
- {header_filename}
- {source_filename}

Status
------

This contract file is intended to be shared with the board-side embedded implementation so that desktop generator and embedded runtime use the same assumptions.
"""


def _emit_send_step(step_index: int, step: SendMessageStep) -> list[str]:
    if step.message is None or step.message.msg_id is None:
        return _emit_invalid_step_comment(
            step_index,
            "send step has no selected message",
            step,
        )

    payload = pack_message_payload(step.message.category, step.message.msg_id, step.payload or {})
    payload_name = f"step_{step_index}_payload"

    if step.message.category == "KU":
        send_fn = "scenario_send_ku"
    elif step.message.category == "KT":
        send_fn = "scenario_send_kt"
    else:
        return _emit_invalid_step_comment(
            step_index,
            f"unsupported send category {step.message.category}",
            step,
        )

    ack_policy_c = _ack_policy_to_c(step.ack_policy)
    ack_timeout_ms = 0 if step.ack_timeout_ms is None else max(0, int(step.ack_timeout_ms))
    retry = _normalize_retry(step.retry)

    lines: list[str] = []
    lines.extend(
        _emit_step_comment_block(step_index, step, f"send {step.message.category} 0x{step.message.msg_id:04X}"))
    lines.extend(_emit_payload_declaration(payload_name, payload))
    lines.extend(
        [
            f"    rc = {send_fn}(0x{step.message.msg_id:04X}u,",
            f"                     {payload_name},",
            f"                     (uint16_t)sizeof({payload_name}),",
            f"                     {ack_policy_c},",
            f"                     {ack_timeout_ms}u,",
            f"                     (uint8_t){retry.attempts}u,",
            f"                     {retry.retry_delay_ms}u,",
            f"                     {_bool_to_c_u8(retry.retry_on_timeout)},",
            f"                     {_bool_to_c_u8(retry.retry_on_reject)});",
            "    if (rc != SCENARIO_OK) {",
            f"        scenario_log_runtime_error({step_index}u, rc);",
            "        return rc;",
            "    }",
            "",
        ]
    )
    return lines


def _emit_wait_time_step(step_index: int, step: WaitTimeStep) -> list[str]:
    lines: list[str] = []
    lines.extend(_emit_step_comment_block(step_index, step, f"wait {step.delay_ms} ms"))
    lines.extend(
        [
            f"    scenario_wait_ms({max(0, int(step.delay_ms))}u);",
            "",
        ]
    )
    return lines


def _emit_wait_for_ts_runtime_handled_comment(step_index: int, step: WaitForTsStep) -> list[str]:
    if step.expected is None or step.expected.msg_id is None:
        return _emit_invalid_step_comment(
            step_index,
            "WAIT_FOR_TS has no expected message (UI-only, handled by runtime logic)",
            step,
        )

    lines = [
        f"    /* step {step_index}: expected {step.expected.category} 0x{step.expected.msg_id:04X} handled by board runtime */"
    ]

    if step.bind_to_previous_ku:
        lines.append("    /* bind_to_previous_ku=true */")
    if step.ack_for_msg_id is not None:
        lines.append(f"    /* ack_for_msg_id=0x{step.ack_for_msg_id:04X} */")
    if step.require_ack_ok:
        lines.append("    /* require_ack_ok=true */")

    comment = _get_step_comment(step)
    if comment:
        lines.append(f"    /* comment: {_escape_c_comment_text(comment)} */")

    lines.append("")
    return lines


def _emit_comment_step_comment(step_index: int, step: CommentStep) -> list[str]:
    lines = [f"    /* step {step_index}: comment */"]
    if step.text:
        lines.append(f"    /* text: {_escape_c_comment_text(step.text)} */")
    comment = _get_step_comment(step)
    if comment:
        lines.append(f"    /* comment: {_escape_c_comment_text(comment)} */")
    lines.append("")
    return lines


def _emit_payload_declaration(name: str, payload: bytes) -> list[str]:
    if not payload:
        return [f"    static const uint8_t {name}[] = {{}};"]

    byte_list = ", ".join(f"0x{b:02X}" for b in payload)
    return [f"    static const uint8_t {name}[] = {{ {byte_list} }};"]


def _emit_step_comment_block(step_index: int, step, title: str) -> list[str]:
    lines = [f"    /* step {step_index}: {title} */"]

    comment = _get_step_comment(step)
    if comment:
        lines.append(f"    /* comment: {_escape_c_comment_text(comment)} */")

    return lines


def _emit_disabled_step_comment(step_index: int, step) -> list[str]:
    lines = [f"    /* step {step_index}: disabled, skipped */"]

    comment = _get_step_comment(step)
    if comment:
        lines.append(f"    /* comment: {_escape_c_comment_text(comment)} */")

    lines.append("")
    return lines


def _emit_unsupported_step_comment(step_index: int, step) -> list[str]:
    lines = [f"    /* step {step_index}: unsupported step type {type(step).__name__}, skipped */"]

    comment = _get_step_comment(step)
    if comment:
        lines.append(f"    /* comment: {_escape_c_comment_text(comment)} */")

    lines.append("")
    return lines


def _emit_invalid_step_comment(step_index: int, reason: str, step) -> list[str]:
    lines = [f"    /* step {step_index}: {reason}, skipped */"]

    comment = _get_step_comment(step)
    if comment:
        lines.append(f"    /* comment: {_escape_c_comment_text(comment)} */")

    lines.append("")
    return lines


def _get_step_comment(step) -> str:
    value = getattr(step, "comment", "") or ""
    return str(value).strip()


def _ack_policy_to_c(policy: AckPolicy) -> str:
    if policy == AckPolicy.EXPECT_ACK:
        return "SCENARIO_ACK_EXPECT"
    if policy == AckPolicy.OPTIONAL_ACK:
        return "SCENARIO_ACK_OPTIONAL"
    return "SCENARIO_ACK_NONE"


def _normalize_retry(retry: RetryPolicy) -> RetryPolicy:
    if not isinstance(retry, RetryPolicy):
        return RetryPolicy()
    return RetryPolicy(
        attempts=retry.attempts,
        retry_delay_ms=retry.retry_delay_ms,
        retry_on_timeout=retry.retry_on_timeout,
        retry_on_reject=retry.retry_on_reject,
    )


def _bool_to_c_u8(value: bool) -> str:
    return "1u" if value else "0u"


def _bool_text(value: bool) -> str:
    return "true" if value else "false"


def _escape_c_comment_text(text: str) -> str:
    text = text.replace("/*", "/ *")
    text = text.replace("*/", "* /")
    text = text.replace("\r", " ")
    text = text.replace("\n", " | ")
    return text.strip()


def _escape_meta_text(text: str) -> str:
    text = text.replace("\r", " ")
    text = text.replace("\n", " | ")
    return text.strip()


def _make_include_guard(header_filename: str) -> str:
    return header_filename.upper().replace(".", "_").replace("-", "_")
