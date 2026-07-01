import sqlite3
import uuid

from chronicle import ChronicleTracer
from chronicle.integrations.langgraph import ChronicleCallbackHandler


def _make_tracer(tmp_path):
    return ChronicleTracer(
        server_url="http://127.0.0.1:1", timeout=0.2, local_db_path=tmp_path / "c.db"
    )


def test_on_tool_start_logs_tool_call(tmp_path):
    tracer = _make_tracer(tmp_path)
    handler = ChronicleCallbackHandler(tracer)

    handler.on_tool_start({"name": "search"}, "weather query", run_id=uuid.uuid4())
    tracer.close()

    conn = sqlite3.connect(tmp_path / "c.db")
    rows = conn.execute("SELECT event_type FROM events WHERE run_id = ?", (tracer.run_id,)).fetchall()
    conn.close()
    assert rows == [("tool_call",)]


def test_on_chain_error_logs_error(tmp_path):
    tracer = _make_tracer(tmp_path)
    handler = ChronicleCallbackHandler(tracer)

    handler.on_chain_error(ValueError("boom"), run_id=uuid.uuid4())
    tracer.close()

    conn = sqlite3.connect(tmp_path / "c.db")
    rows = conn.execute("SELECT event_type FROM events WHERE run_id = ?", (tracer.run_id,)).fetchall()
    conn.close()
    assert rows == [("error",)]
