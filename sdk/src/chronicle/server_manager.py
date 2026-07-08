"""ServerManager: auto-starts the Chronicle FastAPI server as a subprocess if it isn't reachable.

Mirrors what the Tauri desktop app's `start_chronicle_server` command does
(`app/src-tauri/src/lib.rs`) — shell out to `uvicorn` as a plain child
process, not a bundled binary. Used by `chronicle.instrument()` so an agent
process can start recording without the desktop app (or a manually-started
server) running first.
"""

from __future__ import annotations

import atexit
import contextlib
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import httpx

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7823
HEALTH_CHECK_TIMEOUT = 0.5
DEFAULT_POLL_INTERVAL = 0.5
DEFAULT_STARTUP_TIMEOUT = 5.0
PID_FILE = Path.home() / ".chronicle" / "server.pid"

logger = logging.getLogger("chronicle")


def _validated_python_executable() -> str:
    """Confirms `sys.executable` is a real, existing interpreter file before it's used
    to spawn a subprocess.

    Nothing here accepts an externally-supplied path — `subprocess.Popen` is always
    called with `sys.executable`, the interpreter this code is already running as, never
    a name resolved off `PATH` (which could be shadowed by an attacker-controlled
    `uvicorn`/`python` earlier in the search order). This is a defensive assertion
    against a corrupted or empty `sys.executable` rather than a boundary against
    attacker-controlled input, since nothing attacker-facing flows into it.

    Deliberately does *not* require `sys.executable` to live under `sys.prefix`/
    `sys.base_prefix`: some legitimate installations (e.g. the Microsoft Store build of
    Python on Windows) run through an app-execution-alias shim whose path is outside the
    interpreter's own prefix by design, so that check produced false positives that broke
    server auto-start on an otherwise perfectly normal install — confirmed by this
    module's own test suite failing against the real interpreter on such a system.
    """
    executable = sys.executable
    if not executable or not Path(executable).is_file():
        raise RuntimeError(f"sys.executable is not a valid file: {executable!r}")
    return executable


class ServerManager:
    """Ensures a Chronicle server is reachable at `host:port`, starting one if not.

    Never raises: every method that could fail (spawning the subprocess,
    reaching the health endpoint) catches its own errors and returns a
    plain `bool`, so a caller like `chronicle.instrument()` can always fall
    back to local file storage instead of crashing the agent.
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        startup_timeout: float = DEFAULT_STARTUP_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
    ) -> None:
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.startup_timeout = startup_timeout
        self.poll_interval = poll_interval
        self._process: subprocess.Popen[bytes] | None = None

    def is_running(self) -> bool:
        """Returns True if `GET /health` on `base_url` responds successfully."""
        try:
            response = httpx.get(f"{self.base_url}/health", timeout=HEALTH_CHECK_TIMEOUT)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    def ensure_running(self) -> bool:
        """Returns True if the server is (or becomes) reachable within `startup_timeout`.

        If nothing responds on `host:port`, spawns `python -m uvicorn
        src.main:app` as a detached subprocess (same approach the Tauri app
        uses) and polls `is_running()` every `poll_interval` seconds. If the
        subprocess can't even be spawned (e.g. `chronicle-server`/`uvicorn`
        isn't installed in this environment), or it doesn't become healthy
        in time, returns False without raising.
        """
        if self.is_running():
            return True

        try:
            python = _validated_python_executable()
        except RuntimeError:
            logger.warning("Chronicle: refusing to spawn a server subprocess", exc_info=True)
            return False

        try:
            self._process = subprocess.Popen(
                [python, "-m", "uvicorn", "src.main:app", "--host", self.host, "--port", str(self.port)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return False

        atexit.register(self._terminate)
        self._write_pid_file(self._process.pid)

        deadline = time.time() + self.startup_timeout
        while time.time() < deadline:
            if self.is_running():
                return True
            time.sleep(self.poll_interval)
        return False

    def stop(self) -> bool:
        """Kills the server process recorded in `PID_FILE`, if any. Returns True if it stopped one."""
        pid = self._read_pid_file()
        if pid is None:
            return False
        with contextlib.suppress(ProcessLookupError, OSError):
            os.kill(pid, signal.SIGTERM)
        self._clear_pid_file()
        return True

    def _terminate(self) -> None:
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
        self._clear_pid_file()

    def _write_pid_file(self, pid: int) -> None:
        try:
            PID_FILE.parent.mkdir(parents=True, exist_ok=True)
            PID_FILE.write_text(str(pid))
        except OSError:  # pragma: no cover - defensive: never block on a pid file write
            pass

    def _read_pid_file(self) -> int | None:
        try:
            return int(PID_FILE.read_text().strip())
        except (OSError, ValueError):
            return None

    def _clear_pid_file(self) -> None:
        with contextlib.suppress(OSError):  # pragma: no cover - defensive
            PID_FILE.unlink(missing_ok=True)
