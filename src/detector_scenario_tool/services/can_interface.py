"""Bringing a SocketCAN interface up.

python-can's SocketCAN backend does not accept a bitrate — the kernel takes it from the netlink
configuration, which is set with `ip link` and needs root. Rather than asking the user to leave the
application and type it in a terminal, this runs the one command through `pkexec`, so PolicyKit
shows the desktop's own password dialog and the application never sees the password.

Nothing else here is privileged: this configures the interface and stops. Opening it, sending and
receiving all happen unprivileged afterwards.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass

#: Network interface names are short and restricted; anything else is refused rather than passed
#: to a command running as root.
CHANNEL_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,14}$")

MIN_BITRATE = 10_000
MAX_BITRATE = 1_000_000

CONFIGURE_TIMEOUT_S = 60


@dataclass(frozen=True)
class ConfigureResult:
    ok: bool
    #: Untranslated detail from the tools, shown verbatim so a failure is diagnosable.
    detail: str = ""
    cancelled: bool = False


def is_available() -> bool:
    """Whether the interface can be configured from here at all."""
    return bool(shutil.which("ip") and shutil.which("pkexec"))


def validate(channel: str, bitrate: int) -> str | None:
    """Returns a diagnostic code, or None when the arguments are usable."""
    if not CHANNEL_PATTERN.match(channel or ""):
        return "caninterface.bad_channel"
    if not isinstance(bitrate, int) or not MIN_BITRATE <= bitrate <= MAX_BITRATE:
        return "caninterface.bad_bitrate"
    return None


def batch_script(channel: str, bitrate: int) -> str:
    """The `ip -batch` script that reconfigures the interface.

    Taking it down first is what makes this repeatable: `type can bitrate` is rejected on an
    interface that is already up, which is the usual case on a second attempt.
    """
    return (
        f"link set {channel} down\n"
        f"link set {channel} type can bitrate {bitrate}\n"
        f"link set {channel} up\n"
    )


def describe_command(channel: str, bitrate: int) -> str:
    """What the user is about to authorise, in a form they could paste into a terminal."""
    return (
        f"sudo ip link set {channel} down && "
        f"sudo ip link set {channel} type can bitrate {bitrate} && "
        f"sudo ip link set {channel} up"
    )


def configure(channel: str, bitrate: int, runner=subprocess.run) -> ConfigureResult:
    """Bring `channel` up at `bitrate`, asking PolicyKit for authorisation."""
    problem = validate(channel, bitrate)
    if problem is not None:
        return ConfigureResult(ok=False, detail=problem)

    ip_path = shutil.which("ip")
    pkexec_path = shutil.which("pkexec")
    if not ip_path or not pkexec_path:
        return ConfigureResult(ok=False, detail="caninterface.tools_missing")

    try:
        completed = runner(
            [pkexec_path, ip_path, "-batch", "-"],
            input=batch_script(channel, bitrate),
            capture_output=True,
            text=True,
            timeout=CONFIGURE_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return ConfigureResult(ok=False, detail="caninterface.timeout")
    except OSError as exc:
        return ConfigureResult(ok=False, detail=str(exc))

    if completed.returncode == 0:
        return ConfigureResult(ok=True)

    # 126 and 127 are pkexec's own codes for "not authorised" and "dismissed".
    if completed.returncode in (126, 127):
        return ConfigureResult(ok=False, cancelled=True, detail="caninterface.not_authorised")

    detail = (completed.stderr or completed.stdout or "").strip()
    return ConfigureResult(ok=False, detail=detail or f"exit code {completed.returncode}")
