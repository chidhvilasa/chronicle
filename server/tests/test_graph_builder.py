from src.graph_builder import build_graph


def _event(
    event_id,
    run_id="run-1",
    timestamp=1000.0,
    event_type="tool_call",
    agent_name=None,
    duration_ms=None,
    input_tokens=None,
    output_tokens=None,
    data=None,
    error=None,
):
    return {
        "event_id": event_id,
        "run_id": run_id,
        "timestamp": timestamp,
        "event_type": event_type,
        "agent_name": agent_name,
        "duration_ms": duration_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "data": data or {},
        "error": error,
    }


def _find(items, **kwargs):
    return next(i for i in items if all(i[k] == v for k, v in kwargs.items()))


def test_build_graph_empty():
    graph = build_graph([])
    assert graph == {
        "nodes": [],
        "edges": [],
        "metadata": {"total_nodes": 0, "total_edges": 0, "has_cycles": False, "max_depth": 0},
    }


def test_build_graph_creates_agent_and_tool_nodes():
    events = [
        _event(
            "e1",
            agent_name="researcher",
            event_type="tool_call",
            timestamp=1000.0,
            data={"tool_name": "search"},
        )
    ]
    graph = build_graph(events)

    node_ids = {n["id"] for n in graph["nodes"]}
    assert "agent:researcher" in node_ids
    assert "tool:search" in node_ids

    agent_node = _find(graph["nodes"], id="agent:researcher")
    assert agent_node["type"] == "agent"
    assert agent_node["label"] == "researcher"
    assert agent_node["event_count"] == 1

    tool_node = _find(graph["nodes"], id="tool:search")
    assert tool_node["type"] == "tool"
    assert tool_node["label"] == "search"


def test_langgraph_style_tool_call_creates_calls_and_responds_edges():
    """A LangGraph tool_call event (no `data["event"]` marker) covers call + result in one event."""
    events = [
        _event(
            "e1",
            agent_name="agent-a",
            event_type="tool_call",
            data={"tool_name": "search"},
            duration_ms=50,
        )
    ]
    graph = build_graph(events)

    calls_edge = _find(graph["edges"], source="agent:agent-a", target="tool:search", edge_type="calls")
    responds_edge = _find(graph["edges"], source="tool:search", target="agent:agent-a", edge_type="responds")
    assert calls_edge["event_count"] == 1
    assert responds_edge["event_count"] == 1


def test_split_tool_call_and_tool_result_events_create_one_edge_each():
    """OpenAI Agents SDK/CrewAI/AutoGen style: separate tool_call and tool_result sub-events."""
    events = [
        _event("e1", agent_name="agent-a", event_type="tool_call", data={"tool_name": "search", "event": "tool_call"}),
        _event("e2", agent_name="agent-a", event_type="tool_call", data={"tool_name": "search", "event": "tool_result"}),
    ]
    graph = build_graph(events)

    calls_edges = [e for e in graph["edges"] if e["edge_type"] == "calls"]
    responds_edges = [e for e in graph["edges"] if e["edge_type"] == "responds"]
    assert len(calls_edges) == 1
    assert len(responds_edges) == 1
    assert calls_edges[0]["source"] == "agent:agent-a"
    assert calls_edges[0]["target"] == "tool:search"
    assert responds_edges[0]["source"] == "tool:search"
    assert responds_edges[0]["target"] == "agent:agent-a"


def test_repeated_tool_calls_merge_into_one_node_and_edge_with_incremented_count():
    events = [
        _event(f"e{i}", agent_name="agent-a", event_type="tool_call", data={"tool_name": "search"})
        for i in range(100)
    ]
    graph = build_graph(events)

    tool_nodes = [n for n in graph["nodes"] if n["type"] == "tool"]
    assert len(tool_nodes) == 1
    assert tool_nodes[0]["event_count"] == 100

    calls_edges = [e for e in graph["edges"] if e["edge_type"] == "calls"]
    assert len(calls_edges) == 1
    assert calls_edges[0]["event_count"] == 100


def test_llm_call_creates_llm_node_and_calls_edge():
    events = [
        _event(
            "e1",
            agent_name="agent-a",
            event_type="llm_call",
            data={"model": "gpt-4"},
            input_tokens=10,
            output_tokens=20,
            duration_ms=150,
        )
    ]
    graph = build_graph(events)

    llm_node = _find(graph["nodes"], id="llm:gpt-4")
    assert llm_node["type"] == "llm"
    assert llm_node["label"] == "gpt-4"
    assert llm_node["total_tokens"] == 30
    assert llm_node["avg_latency_ms"] == 150

    edge = _find(graph["edges"], source="agent:agent-a", target="llm:gpt-4", edge_type="calls")
    assert edge["event_count"] == 1


def test_handoff_event_creates_edge_between_agents():
    events = [
        _event(
            "e1",
            agent_name="triage",
            event_type="agent_message",
            data={"event": "handoff", "source_agent": "triage", "target_agent": "billing"},
        )
    ]
    graph = build_graph(events)

    edge = _find(graph["edges"], source="agent:triage", target="agent:billing", edge_type="handoff")
    assert edge["event_count"] == 1
    node_ids = {n["id"] for n in graph["nodes"]}
    assert "agent:billing" in node_ids


def test_node_status_is_error_when_error_count_positive():
    events = [
        _event("e1", agent_name="agent-a", event_type="tool_call", data={"tool_name": "search"}, error="boom")
    ]
    graph = build_graph(events)
    tool_node = _find(graph["nodes"], id="tool:search")
    assert tool_node["error_count"] == 1
    assert tool_node["status"] == "error"


def test_node_status_is_ok_with_no_errors():
    events = [_event("e1", agent_name="agent-a", event_type="tool_call", data={"tool_name": "search"})]
    graph = build_graph(events)
    tool_node = _find(graph["nodes"], id="tool:search")
    assert tool_node["status"] == "ok"


def test_input_and_output_nodes_bracket_the_run():
    events = [
        _event("e1", agent_name="agent-a", event_type="llm_call", timestamp=1000.0, data={"model": "gpt-4"}),
        _event("e2", agent_name="agent-b", event_type="llm_call", timestamp=1001.0, data={"model": "gpt-4"}),
    ]
    graph = build_graph(events)

    node_types = {n["id"]: n["type"] for n in graph["nodes"]}
    assert node_types["input"] == "input"
    assert node_types["output"] == "output"

    trigger_in = _find(graph["edges"], source="input", target="agent:agent-a", edge_type="triggers")
    trigger_out = _find(graph["edges"], source="agent:agent-b", target="output", edge_type="triggers")
    assert trigger_in["event_count"] == 1
    assert trigger_out["event_count"] == 1


def test_metadata_counts_nodes_and_edges():
    events = [
        _event("e1", agent_name="agent-a", event_type="tool_call", data={"tool_name": "search"}),
    ]
    graph = build_graph(events)
    assert graph["metadata"]["total_nodes"] == len(graph["nodes"])
    assert graph["metadata"]["total_edges"] == len(graph["edges"])


def test_no_cycle_for_a_simple_agent_to_tool_run():
    events = [
        _event("e1", agent_name="agent-a", event_type="tool_call", timestamp=1000.0, data={"tool_name": "search"}),
    ]
    graph = build_graph(events)
    assert graph["metadata"]["has_cycles"] is False


def test_detects_cycle_from_an_agent_handoff_loop():
    events = [
        _event(
            "e1",
            agent_name="a",
            event_type="agent_message",
            timestamp=1000.0,
            data={"event": "handoff", "source_agent": "a", "target_agent": "b"},
        ),
        _event(
            "e2",
            agent_name="b",
            event_type="agent_message",
            timestamp=1001.0,
            data={"event": "handoff", "source_agent": "b", "target_agent": "a"},
        ),
    ]
    graph = build_graph(events)
    assert graph["metadata"]["has_cycles"] is True


def test_repeated_tool_call_round_trips_do_not_falsely_report_a_cycle():
    """calls + responds between the same agent/tool pair is not a real cycle."""
    events = [
        _event("e1", agent_name="agent-a", event_type="tool_call", timestamp=1000.0, data={"tool_name": "search"}),
        _event("e2", agent_name="agent-a", event_type="tool_call", timestamp=1001.0, data={"tool_name": "search"}),
    ]
    graph = build_graph(events)
    assert graph["metadata"]["has_cycles"] is False


def test_max_depth_counts_hops_from_input_to_output():
    events = [
        _event("e1", agent_name="agent-a", event_type="tool_call", timestamp=1000.0, data={"tool_name": "search"}),
    ]
    graph = build_graph(events)
    # input -> agent-a -> tool:search -> output is not reachable via "responds" (excluded),
    # so the longest path is input -> agent:agent-a -> tool:search (calls) = 2 hops,
    # or input -> agent:agent-a -> output = 2 hops. Either way, at least 2.
    assert graph["metadata"]["max_depth"] >= 2


def test_unknown_agent_name_defaults_to_unknown():
    events = [_event("e1", agent_name=None, event_type="tool_call", data={"tool_name": "search"})]
    graph = build_graph(events)
    assert _find(graph["nodes"], id="agent:unknown")["label"] == "unknown"


def test_missing_tool_name_defaults_to_unknown():
    events = [_event("e1", agent_name="agent-a", event_type="tool_call", data={})]
    graph = build_graph(events)
    assert _find(graph["nodes"], id="tool:unknown")["label"] == "unknown"
