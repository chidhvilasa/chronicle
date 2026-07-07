import json

from chronicle import ChronicleTracer
from chronicle.memory_diff import diff_memory_keys, json_safe_dict, record_memory_update


def _tracer(tmp_path, **kwargs):
    return ChronicleTracer(
        server_url="http://127.0.0.1:1",  # nothing listens here
        timeout=0.2,
        local_dir=tmp_path / "chronicle_runs",
        batch_size=1,
        **kwargs,
    )


def _read_events(tmp_path, run_id):
    path = tmp_path / "chronicle_runs" / f"{run_id}.json"
    return json.loads(path.read_text())


def test_diff_memory_keys_detects_added_removed_changed():
    diff = diff_memory_keys({"a": 1, "b": 2}, {"a": 1, "b": 3, "c": 4})
    assert diff["keys_added"] == ["c"]
    assert diff["keys_removed"] == []
    assert diff["keys_changed"] == ["b"]


def test_diff_memory_keys_nested_change_reported_as_top_level_key():
    before = {"user": {"name": "Alice", "age": 30}}
    after = {"user": {"name": "Alice", "age": 31}}
    diff = diff_memory_keys(before, after)
    assert diff["keys_changed"] == ["user"]


def test_json_safe_dict_returns_empty_dict_for_non_dict_input():
    assert json_safe_dict("not a dict") == {}
    assert json_safe_dict(None) == {}


def test_json_safe_dict_converts_non_serializable_leaves_to_strings():
    class Custom:
        def __str__(self):
            return "custom-value"

    result = json_safe_dict({"a": Custom()})
    assert result == {"a": "custom-value"}


def test_json_safe_dict_decouples_from_the_original_nested_object():
    original = {"nested": {"count": 1}}
    safe = json_safe_dict(original)
    original["nested"]["count"] = 2
    assert safe["nested"]["count"] == 1


def test_record_memory_update_records_event_when_changed(tmp_path):
    tracer = _tracer(tmp_path)
    record_memory_update(tracer, "agent-a", {"a": 1}, {"a": 1, "b": 2})
    tracer.close()

    events = _read_events(tmp_path, tracer.run_id)
    assert events[0]["event_type"] == "memory_update"
    assert events[0]["agent_name"] == "agent-a"
    assert events[0]["data"]["memory_before"] == {"a": 1}
    assert events[0]["data"]["memory_after"] == {"a": 1, "b": 2}
    assert events[0]["data"]["keys_added"] == ["b"]


def test_record_memory_update_is_a_no_op_when_unchanged(tmp_path):
    tracer = _tracer(tmp_path)
    record_memory_update(tracer, "agent-a", {"a": 1}, {"a": 1})
    tracer.close()

    path = tmp_path / "chronicle_runs" / f"{tracer.run_id}.json"
    assert not path.exists()


def test_record_memory_update_is_a_no_op_when_neither_side_is_dict_like(tmp_path):
    tracer = _tracer(tmp_path)
    record_memory_update(tracer, "agent-a", "not a dict", None)
    tracer.close()

    path = tmp_path / "chronicle_runs" / f"{tracer.run_id}.json"
    assert not path.exists()
