import sqlite3

from chronicle import ChronicleTracer


def test_tracer_falls_back_to_local_storage_when_server_unreachable(tmp_path):
    db_path = tmp_path / "chronicle.db"
    tracer = ChronicleTracer(
        server_url="http://127.0.0.1:1",  # nothing listens here
        timeout=0.2,
        local_db_path=db_path,
    )

    tracer.tool_call("search", {"query": "weather"})
    tracer.close()

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT event_type FROM events WHERE run_id = ?", (tracer.run_id,)).fetchall()
    conn.close()

    assert rows == [("tool_call",)]


def test_tracer_generates_run_id_when_not_provided(tmp_path):
    tracer = ChronicleTracer(local_db_path=tmp_path / "c.db")
    assert tracer.run_id
    tracer.close()


def test_tracer_uses_provided_run_id(tmp_path):
    tracer = ChronicleTracer(run_id="my-run", local_db_path=tmp_path / "c.db")
    assert tracer.run_id == "my-run"
    tracer.close()


def test_all_event_helpers_return_events(tmp_path):
    tracer = ChronicleTracer(
        server_url="http://127.0.0.1:1", timeout=0.2, local_db_path=tmp_path / "c.db"
    )
    assert tracer.tool_call("t", {})["event_type"] == "tool_call"
    assert tracer.llm_call("gpt-4o")["event_type"] == "llm_call"
    assert tracer.agent_message("assistant", "hi")["event_type"] == "agent_message"
    assert tracer.memory_update("k", "v")["event_type"] == "memory_update"
    assert tracer.error("oops")["event_type"] == "error"
    assert tracer.retry(1, 3)["event_type"] == "retry"
    tracer.close()
