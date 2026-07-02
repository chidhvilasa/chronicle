from unittest.mock import MagicMock

import httpx
import pytest

from chronicle import server_manager as server_manager_module
from chronicle.server_manager import ServerManager


@pytest.fixture(autouse=True)
def _isolated_pid_file(tmp_path, monkeypatch):
    """Every test gets its own pid file location so tests never touch `~/.chronicle`."""
    monkeypatch.setattr(server_manager_module, "PID_FILE", tmp_path / "server.pid")


def _manager(**kwargs):
    return ServerManager(startup_timeout=0.05, poll_interval=0.01, **kwargs)


def test_is_running_true_when_health_check_succeeds(monkeypatch):
    monkeypatch.setattr(
        server_manager_module.httpx, "get", MagicMock(return_value=MagicMock(status_code=200))
    )
    assert _manager().is_running() is True


def test_is_running_false_when_health_check_errors(monkeypatch):
    monkeypatch.setattr(
        server_manager_module.httpx, "get", MagicMock(side_effect=httpx.ConnectError("refused"))
    )
    assert _manager().is_running() is False


def test_is_running_false_on_non_200_status(monkeypatch):
    monkeypatch.setattr(
        server_manager_module.httpx, "get", MagicMock(return_value=MagicMock(status_code=500))
    )
    assert _manager().is_running() is False


def test_ensure_running_skips_spawn_when_already_running(monkeypatch):
    manager = _manager()
    monkeypatch.setattr(manager, "is_running", MagicMock(return_value=True))
    popen = MagicMock()
    monkeypatch.setattr(server_manager_module.subprocess, "Popen", popen)

    assert manager.ensure_running() is True
    popen.assert_not_called()


def test_ensure_running_spawns_and_returns_true_once_healthy(monkeypatch):
    manager = _manager()
    health_results = iter([False, False, True])
    monkeypatch.setattr(manager, "is_running", MagicMock(side_effect=lambda: next(health_results)))
    fake_process = MagicMock(pid=12345)
    monkeypatch.setattr(server_manager_module.subprocess, "Popen", MagicMock(return_value=fake_process))
    monkeypatch.setattr(server_manager_module.atexit, "register", MagicMock())

    assert manager.ensure_running() is True


def test_ensure_running_returns_false_when_subprocess_cannot_spawn(monkeypatch):
    manager = _manager()
    monkeypatch.setattr(manager, "is_running", MagicMock(return_value=False))
    monkeypatch.setattr(
        server_manager_module.subprocess, "Popen", MagicMock(side_effect=OSError("no uvicorn"))
    )

    assert manager.ensure_running() is False


def test_ensure_running_returns_false_when_never_becomes_healthy(monkeypatch):
    manager = _manager()
    monkeypatch.setattr(manager, "is_running", MagicMock(return_value=False))
    monkeypatch.setattr(
        server_manager_module.subprocess, "Popen", MagicMock(return_value=MagicMock(pid=1))
    )
    monkeypatch.setattr(server_manager_module.atexit, "register", MagicMock())

    assert manager.ensure_running() is False


def test_stop_returns_false_when_no_pid_file():
    assert _manager().stop() is False


def test_stop_kills_process_from_pid_file_and_clears_it(monkeypatch, tmp_path):
    pid_file = tmp_path / "server.pid"
    monkeypatch.setattr(server_manager_module, "PID_FILE", pid_file)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text("4242")
    kill = MagicMock()
    monkeypatch.setattr(server_manager_module.os, "kill", kill)

    assert _manager().stop() is True
    kill.assert_called_once()
    assert kill.call_args[0][0] == 4242
    assert not pid_file.exists()


def test_stop_handles_process_already_gone(monkeypatch, tmp_path):
    pid_file = tmp_path / "server.pid"
    monkeypatch.setattr(server_manager_module, "PID_FILE", pid_file)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text("4242")
    monkeypatch.setattr(
        server_manager_module.os, "kill", MagicMock(side_effect=ProcessLookupError())
    )

    assert _manager().stop() is True
    assert not pid_file.exists()
