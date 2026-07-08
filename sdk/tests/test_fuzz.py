"""Fuzz tests (Hypothesis) for SDK code that evaluates or serializes untrusted-shaped data.

Both targets are pure functions with no I/O, so no server/fixtures are needed
beyond Hypothesis itself.
"""

from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from chronicle.adapters.langgraph import _json_safe
from chronicle.models import StateSnapshot
from chronicle.testing.models import AssertionType, ChronicleAssertion
from chronicle.testing.runner import evaluate_assertion

_ASSERTION_TYPES: tuple[AssertionType, ...] = (
    "output_contains",
    "output_not_contains",
    "output_matches_regex",
    "tool_called",
    "tool_not_called",
    "token_count_under",
    "latency_under_ms",
    "no_errors",
    "custom",
)

# `target` is deliberately allowed to be regex metacharacter soup / non-numeric
# text: "output_matches_regex" parses it as a regex and "token_count_under"/
# "latency_under_ms" parse it as an int, so malformed targets must fail
# gracefully (as a failed assertion), not raise.
_targets = st.one_of(
    st.text(max_size=30),
    st.sampled_from(["(", "[", "*", "??", "(?P<x>", "\\", "999999999999999999999", "-1", "0", "abc"]),
)

_events = st.lists(
    st.fixed_dictionaries(
        {
            "event_type": st.sampled_from(
                ["tool_call", "llm_call", "agent_message", "memory_update", "error", "retry"]
            ),
            "agent_name": st.one_of(st.none(), st.text(max_size=10)),
        },
        optional={
            "data": st.dictionaries(st.text(max_size=10), st.text(max_size=10), max_size=3),
            "duration_ms": st.one_of(st.none(), st.floats(allow_nan=False, allow_infinity=False)),
            "token_usage": st.one_of(
                st.none(),
                st.fixed_dictionaries(
                    {
                        "input_tokens": st.one_of(st.none(), st.integers(min_value=0, max_value=10_000)),
                        "output_tokens": st.one_of(st.none(), st.integers(min_value=0, max_value=10_000)),
                    }
                ),
            ),
        },
    ),
    max_size=5,
)


@settings(max_examples=100, deadline=None)
@given(
    assertion_type=st.sampled_from(_ASSERTION_TYPES),
    target=_targets,
    agent_name=st.one_of(st.none(), st.text(max_size=10)),
    events=_events,
)
def test_fuzz_evaluate_assertion_never_raises(assertion_type, target, agent_name, events):
    assertion = ChronicleAssertion(assertion_type=assertion_type, target=target, agent_name=agent_name)
    result = evaluate_assertion(assertion, events)
    assert result.assertion_type == assertion_type
    assert isinstance(result.passed, bool)
    assert isinstance(result.reason, str)


# --- StateSnapshot serialization fuzzing --------------------------------------

_json_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=20),
)


class _Unserializable:
    """Stands in for the kind of live object `_json_safe` must defang: a LangChain
    message, a datetime, or any other custom class `json.dumps` can't handle on its own.
    """

    def __repr__(self) -> str:
        return "<Unserializable>"


_messy_values = st.recursive(
    st.one_of(_json_scalars, st.builds(_Unserializable)),
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(st.text(max_size=10), children, max_size=4),
    ),
    max_leaves=25,
)


@settings(max_examples=100, deadline=None)
@given(graph_state=_messy_values, messages=_messy_values, tool_results=_messy_values, metadata=_messy_values)
def test_fuzz_state_snapshot_serialization_always_produces_valid_json(
    graph_state, messages, tool_results, metadata
):
    safe_graph_state, _ = _json_safe(graph_state)
    safe_messages, _ = _json_safe(messages)
    safe_tool_results, _ = _json_safe(tool_results)
    safe_metadata, _ = _json_safe(metadata)

    snapshot = StateSnapshot(
        run_id="run-1",
        step_index=0,
        graph_state=safe_graph_state if isinstance(safe_graph_state, dict) else {"value": safe_graph_state},
        messages=safe_messages if isinstance(safe_messages, list) else [safe_messages],
        tool_results=safe_tool_results if isinstance(safe_tool_results, list) else [safe_tool_results],
        metadata=safe_metadata if isinstance(safe_metadata, dict) else {"value": safe_metadata},
    )

    # Must never raise: this is the exact call POST /snapshots' body construction relies on.
    json.dumps(snapshot.to_dict())


@settings(max_examples=100, deadline=None)
@given(value=_messy_values)
def test_fuzz_json_safe_never_raises_and_always_serializes(value):
    safe_value, _warned = _json_safe(value)
    json.dumps(safe_value)
