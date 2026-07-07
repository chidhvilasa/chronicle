"""Builds a run's execution graph (nodes/edges/metadata) from its raw events.

Walks events in timestamp order, creating one node per unique agent, tool, and
LLM model seen, and edges for tool calls/results, LLM calls, and agent
handoffs. Duplicate edges (the same source/target/edge_type traversed
multiple times) are merged into one edge with an incremented `event_count`
rather than one edge per occurrence — this is what keeps a tool called 100
times from producing 100 duplicate nodes or edges.

Event-type conventions this reads (see `chronicle.adapters.*` in the SDK):
- `tool_call` events with no `data["event"]` marker (LangGraph's convention,
  one event covers the whole call+result) produce both a `calls` edge
  (agent -> tool) and a `responds` edge (tool -> agent).
- `tool_call` events with `data["event"] == "tool_call"` (OpenAI Agents SDK /
  CrewAI / AutoGen's convention, one event per hook) produce only the
  `calls` edge; `data["event"] == "tool_result"` produces only `responds`.
- `agent_message` events with `data["event"] == "handoff"` produce a
  `handoff` edge between `data["source_agent"]` and `data["target_agent"]`.
- `llm_call` events produce a `calls` edge from the agent to an LLM node
  keyed by `data["model"]`.
"""

from __future__ import annotations

import statistics
from typing import Any, TypedDict

INPUT_NODE_ID = "input"
OUTPUT_NODE_ID = "output"


class GraphNode(TypedDict):
    id: str
    type: str
    label: str
    agent_name: str | None
    event_count: int
    error_count: int
    total_tokens: int
    avg_latency_ms: float | None
    status: str


class GraphEdge(TypedDict):
    id: str
    source: str
    target: str
    label: str
    edge_type: str
    event_count: int


class GraphMetadata(TypedDict):
    total_nodes: int
    total_edges: int
    has_cycles: bool
    max_depth: int


class ExecutionGraph(TypedDict):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    metadata: GraphMetadata


class _NodeAccumulator(TypedDict):
    id: str
    type: str
    label: str
    agent_name: str | None
    event_count: int
    error_count: int
    total_tokens: int
    durations: list[float]


class _EdgeAccumulator(TypedDict):
    label: str
    edge_type: str
    event_count: int


def build_graph(events: list[dict[str, Any]]) -> ExecutionGraph:
    """Builds the execution graph for one run's events, in timestamp order."""
    if not events:
        return {"nodes": [], "edges": [], "metadata": _empty_metadata()}

    ordered = sorted(events, key=lambda event: event["timestamp"])
    nodes: dict[str, _NodeAccumulator] = {}
    edges: dict[tuple[str, str, str], _EdgeAccumulator] = {}
    first_agent_id: str | None = None
    last_agent_id: str | None = None

    for event in ordered:
        agent_name = event.get("agent_name") or "unknown"
        agent_id = _agent_node_id(agent_name)
        agent_node = _ensure_node(nodes, agent_id, "agent", agent_name, agent_name)
        _apply_event_stats(agent_node, event)

        first_agent_id = first_agent_id or agent_id
        last_agent_id = agent_id

        event_type = event["event_type"]
        data = event.get("data") or {}
        sub_event = data.get("event")

        if event_type == "tool_call":
            _handle_tool_call(nodes, edges, agent_id, data, sub_event, event)
        elif event_type == "llm_call":
            _handle_llm_call(nodes, edges, agent_id, data, event)

        if sub_event == "handoff":
            _handle_handoff(nodes, edges, agent_name, data)

    if first_agent_id is not None:
        _ensure_node(nodes, INPUT_NODE_ID, "input", "Input", None)
        _add_edge(edges, INPUT_NODE_ID, first_agent_id, "triggers", "start")
    if last_agent_id is not None:
        _ensure_node(nodes, OUTPUT_NODE_ID, "output", "Output", None)
        _add_edge(edges, last_agent_id, OUTPUT_NODE_ID, "triggers", "end")

    graph_nodes = [_finalize_node(node) for node in nodes.values()]
    graph_edges = [_finalize_edge(key, edge) for key, edge in edges.items()]

    adjacency = _build_adjacency(nodes.keys(), edges)
    metadata: GraphMetadata = {
        "total_nodes": len(graph_nodes),
        "total_edges": len(graph_edges),
        "has_cycles": _has_cycle(adjacency),
        "max_depth": _max_depth(adjacency, INPUT_NODE_ID),
    }
    return {"nodes": graph_nodes, "edges": graph_edges, "metadata": metadata}


def _empty_metadata() -> GraphMetadata:
    return {"total_nodes": 0, "total_edges": 0, "has_cycles": False, "max_depth": 0}


def _agent_node_id(agent_name: str) -> str:
    return f"agent:{agent_name}"


def _tool_node_id(tool_name: str) -> str:
    return f"tool:{tool_name}"


def _llm_node_id(model_name: str) -> str:
    return f"llm:{model_name}"


def _ensure_node(
    nodes: dict[str, _NodeAccumulator],
    node_id: str,
    node_type: str,
    label: str,
    agent_name: str | None,
) -> _NodeAccumulator:
    if node_id not in nodes:
        nodes[node_id] = {
            "id": node_id,
            "type": node_type,
            "label": label,
            "agent_name": agent_name,
            "event_count": 0,
            "error_count": 0,
            "total_tokens": 0,
            "durations": [],
        }
    return nodes[node_id]


def _apply_event_stats(node: _NodeAccumulator, event: dict[str, Any]) -> None:
    node["event_count"] += 1
    if event.get("error") is not None:
        node["error_count"] += 1
    node["total_tokens"] += (event.get("input_tokens") or 0) + (event.get("output_tokens") or 0)
    if event.get("duration_ms") is not None:
        node["durations"].append(event["duration_ms"])


def _add_edge(
    edges: dict[tuple[str, str, str], _EdgeAccumulator],
    source: str,
    target: str,
    edge_type: str,
    label: str,
) -> None:
    key = (source, target, edge_type)
    if key not in edges:
        edges[key] = {"label": label, "edge_type": edge_type, "event_count": 0}
    edges[key]["event_count"] += 1


def _handle_tool_call(
    nodes: dict[str, _NodeAccumulator],
    edges: dict[tuple[str, str, str], _EdgeAccumulator],
    agent_id: str,
    data: dict[str, Any],
    sub_event: Any,
    event: dict[str, Any],
) -> None:
    tool_name = data.get("tool_name") or "unknown"
    tool_id = _tool_node_id(tool_name)
    tool_node = _ensure_node(nodes, tool_id, "tool", tool_name, None)
    _apply_event_stats(tool_node, event)

    if sub_event == "tool_result":
        _add_edge(edges, tool_id, agent_id, "responds", tool_name)
    else:
        # Either the OpenAI Agents SDK/CrewAI/AutoGen "tool_call" sub-event, or a plain
        # LangGraph tool_call event with no sub-event marker (one event = call + result).
        _add_edge(edges, agent_id, tool_id, "calls", tool_name)
        if sub_event is None:
            _add_edge(edges, tool_id, agent_id, "responds", tool_name)


def _handle_llm_call(
    nodes: dict[str, _NodeAccumulator],
    edges: dict[tuple[str, str, str], _EdgeAccumulator],
    agent_id: str,
    data: dict[str, Any],
    event: dict[str, Any],
) -> None:
    model_name = data.get("model") or "unknown"
    llm_id = _llm_node_id(model_name)
    llm_node = _ensure_node(nodes, llm_id, "llm", model_name, None)
    _apply_event_stats(llm_node, event)
    _add_edge(edges, agent_id, llm_id, "calls", model_name)


def _handle_handoff(
    nodes: dict[str, _NodeAccumulator],
    edges: dict[tuple[str, str, str], _EdgeAccumulator],
    agent_name: str,
    data: dict[str, Any],
) -> None:
    source_agent = data.get("source_agent") or agent_name
    target_agent = data.get("target_agent") or "unknown"
    source_id = _agent_node_id(source_agent)
    target_id = _agent_node_id(target_agent)
    _ensure_node(nodes, source_id, "agent", source_agent, source_agent)
    _ensure_node(nodes, target_id, "agent", target_agent, target_agent)
    _add_edge(edges, source_id, target_id, "handoff", f"{source_agent} -> {target_agent}")


def _finalize_node(node: _NodeAccumulator) -> GraphNode:
    return {
        "id": node["id"],
        "type": node["type"],
        "label": node["label"],
        "agent_name": node["agent_name"],
        "event_count": node["event_count"],
        "error_count": node["error_count"],
        "total_tokens": node["total_tokens"],
        "avg_latency_ms": statistics.fmean(node["durations"]) if node["durations"] else None,
        "status": "error" if node["error_count"] > 0 else "ok",
    }


def _finalize_edge(key: tuple[str, str, str], edge: _EdgeAccumulator) -> GraphEdge:
    source, target, edge_type = key
    return {
        "id": f"{source}->{target}:{edge_type}",
        "source": source,
        "target": target,
        "label": edge["label"],
        "edge_type": edge_type,
        "event_count": edge["event_count"],
    }


def _build_adjacency(
    node_ids: Any, edges: dict[tuple[str, str, str], _EdgeAccumulator]
) -> dict[str, list[str]]:
    """Adjacency for cycle/depth analysis, excluding `responds` edges.

    `responds` is definitionally the automatic reverse of a `calls` edge (the
    tool answering back), not an independent transition — including it would
    make every single tool call a trivial 2-node cycle and drown out real
    agent loops (handoffs that circle back), which is what the cycle
    detection is meant to surface.
    """
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for (source, target, edge_type) in edges:
        if edge_type == "responds":
            continue
        adjacency.setdefault(source, []).append(target)
    return adjacency


def _has_cycle(adjacency: dict[str, list[str]]) -> bool:
    """Standard directed-graph cycle detection via 3-color DFS (white/gray/black)."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {node_id: WHITE for node_id in adjacency}

    def visit(node_id: str) -> bool:
        color[node_id] = GRAY
        for neighbor in adjacency.get(node_id, []):
            neighbor_color = color.get(neighbor, WHITE)
            if neighbor_color == GRAY:
                return True
            if neighbor_color == WHITE and visit(neighbor):
                return True
        color[node_id] = BLACK
        return False

    return any(color[node_id] == WHITE and visit(node_id) for node_id in list(adjacency))


def _max_depth(adjacency: dict[str, list[str]], start: str) -> int:
    """Longest simple path (in hops) from `start`, guarding against cycles via a path-local visited set."""
    if start not in adjacency:
        return 0

    best = 0

    def dfs(node_id: str, visited: frozenset[str], depth: int) -> None:
        nonlocal best
        best = max(best, depth)
        for neighbor in adjacency.get(node_id, []):
            if neighbor not in visited:
                dfs(neighbor, visited | {neighbor}, depth + 1)

    dfs(start, frozenset({start}), 0)
    return best
