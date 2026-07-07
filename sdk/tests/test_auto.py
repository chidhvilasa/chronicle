import time
from unittest.mock import MagicMock

import chronicle
from chronicle import auto as auto_module
from chronicle.adapters.langgraph import LangGraphAdapter
from chronicle.chaos import ChaosConfig
from chronicle.tracer import ChronicleTracer


class _MockCompiledGraph:
    """Stands in for a `langgraph.graph.state.CompiledStateGraph` instance."""

    __module__ = "langgraph.graph.state"

    def __init__(self):
        self.invoke_calls = []

    def invoke(self, input, config=None, **kwargs):
        self.invoke_calls.append((input, config, kwargs))
        return {"messages": []}


_MockCompiledGraph.__name__ = "CompiledStateGraph"
_MockCompiledGraph.__qualname__ = "CompiledStateGraph"


def test_instrument_returns_a_usable_graph(monkeypatch, tmp_path):
    monkeypatch.setattr(auto_module.ServerManager, "ensure_running", MagicMock(return_value=False))
    monkeypatch.chdir(tmp_path)
    graph = _MockCompiledGraph()

    result = chronicle.instrument(graph)

    assert result is not None
    result.invoke({"input": "hi"})
    assert graph.invoke_calls, "the wrapped graph's invoke() should delegate to the original"


def test_instrument_creates_a_chronicle_tracer_internally(monkeypatch, tmp_path):
    monkeypatch.setattr(auto_module.ServerManager, "ensure_running", MagicMock(return_value=False))
    monkeypatch.chdir(tmp_path)
    created = {}
    original_init = ChronicleTracer.__init__

    def _spy_init(self, *args, **kwargs):
        created["tracer"] = self
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(auto_module.ChronicleTracer, "__init__", _spy_init)

    chronicle.instrument(_MockCompiledGraph())

    assert isinstance(created.get("tracer"), ChronicleTracer)


def test_instrument_attaches_langgraph_adapter_callbacks(monkeypatch, tmp_path):
    monkeypatch.setattr(auto_module.ServerManager, "ensure_running", MagicMock(return_value=False))
    monkeypatch.chdir(tmp_path)
    graph = _MockCompiledGraph()

    result = chronicle.instrument(graph)
    result.invoke({"input": "hi"})

    _, config, _kwargs = graph.invoke_calls[0]
    callbacks = config["callbacks"]
    assert any(isinstance(cb, LangGraphAdapter) for cb in callbacks)


def test_instrument_merges_with_user_supplied_callbacks(monkeypatch, tmp_path):
    monkeypatch.setattr(auto_module.ServerManager, "ensure_running", MagicMock(return_value=False))
    monkeypatch.chdir(tmp_path)
    graph = _MockCompiledGraph()
    user_callback = object()

    result = chronicle.instrument(graph)
    result.invoke({"input": "hi"}, config={"callbacks": [user_callback]})

    _, config, _kwargs = graph.invoke_calls[0]
    assert user_callback in config["callbacks"]
    assert any(isinstance(cb, LangGraphAdapter) for cb in config["callbacks"])


def test_instrument_prints_fallback_message_when_server_unavailable(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(auto_module.ServerManager, "ensure_running", MagicMock(return_value=False))
    monkeypatch.chdir(tmp_path)

    chronicle.instrument(_MockCompiledGraph())

    out = capsys.readouterr().out
    assert "chronicle_runs/ locally" in out


def test_instrument_prints_success_message_when_server_available(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(auto_module.ServerManager, "ensure_running", MagicMock(return_value=True))
    monkeypatch.chdir(tmp_path)

    chronicle.instrument(_MockCompiledGraph())

    out = capsys.readouterr().out
    assert "recording to" in out
    assert "open the desktop app to inspect" in out


def test_instrument_with_chaos_config_stamps_run_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(auto_module.ServerManager, "ensure_running", MagicMock(return_value=False))
    monkeypatch.chdir(tmp_path)
    set_metadata_mock = MagicMock(return_value=True)
    monkeypatch.setattr(auto_module.ChronicleTracer, "set_metadata", set_metadata_mock)

    chronicle.instrument(_MockCompiledGraph(), chaos=ChaosConfig(tool_failure_rate=0.3))

    set_metadata_mock.assert_called_once()
    metadata = set_metadata_mock.call_args[0][0]
    assert metadata["chaos_mode"] is True
    assert metadata["chaos_config"]["tool_failure_rate"] == 0.3


def test_instrument_without_chaos_does_not_stamp_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(auto_module.ServerManager, "ensure_running", MagicMock(return_value=False))
    monkeypatch.chdir(tmp_path)
    set_metadata_mock = MagicMock(return_value=True)
    monkeypatch.setattr(auto_module.ChronicleTracer, "set_metadata", set_metadata_mock)

    chronicle.instrument(_MockCompiledGraph())

    set_metadata_mock.assert_not_called()


def test_instrument_unknown_framework_returns_object_unchanged_and_warns(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(auto_module.ServerManager, "ensure_running", MagicMock(return_value=False))
    monkeypatch.chdir(tmp_path)
    unknown = object()

    result = chronicle.instrument(unknown)

    assert result is unknown
    out = capsys.readouterr().out
    assert "detected unknown framework type" in out


def test_ensure_running_returns_false_gracefully_when_server_unavailable(monkeypatch, tmp_path):
    """`ServerManager.ensure_running()` never raises and falls back cleanly; no real server spawned."""
    import httpx

    from chronicle.server_manager import ServerManager

    monkeypatch.setattr(
        "chronicle.server_manager.subprocess.Popen", MagicMock(side_effect=OSError("no uvicorn"))
    )
    monkeypatch.setattr(
        "chronicle.server_manager.httpx.get", MagicMock(side_effect=httpx.ConnectError("refused"))
    )

    manager = ServerManager(startup_timeout=0.05, poll_interval=0.01)
    assert manager.ensure_running() is False


def test_instrument_context_flushes_and_prints_summary_on_exit(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(auto_module.ServerManager, "ensure_running", MagicMock(return_value=False))
    monkeypatch.chdir(tmp_path)
    graph = _MockCompiledGraph()

    with chronicle.instrument_context(graph) as instrumented:
        instrumented.invoke({"input": "hi"})

    out = capsys.readouterr().out
    assert "Chronicle: run complete" in out
    assert "events" in out
    assert "run_id:" in out


def test_instrument_adds_negligible_overhead_beyond_tracer_construction(monkeypatch, tmp_path):
    """`instrument()`'s own logic (detection, adapter wiring, frame walk) must stay under 100ms.

    Measured as the delta over a bare `ChronicleTracer()` construction,
    since that alone pays a one-time `httpx.Client()` / TLS-truststore
    warm-up cost (tens to hundreds of ms, OS-dependent) that has nothing to
    do with `instrument()` and isn't part of "server startup" either.
    """
    monkeypatch.setattr(auto_module.ServerManager, "ensure_running", MagicMock(return_value=True))
    monkeypatch.chdir(tmp_path)

    baseline_start = time.perf_counter()
    ChronicleTracer()
    baseline_ms = (time.perf_counter() - baseline_start) * 1000

    graph = _MockCompiledGraph()
    start = time.perf_counter()
    chronicle.instrument(graph)
    elapsed_ms = (time.perf_counter() - start) * 1000

    assert elapsed_ms - baseline_ms < 100
