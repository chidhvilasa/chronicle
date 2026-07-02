from chronicle.auto import _detect_framework


def _make_instance(module: str, class_name: str):
    cls = type(class_name, (), {"__module__": module})
    return cls()


def test_detects_langgraph_compiled_graph():
    graph = _make_instance("langgraph.graph.state", "CompiledStateGraph")
    assert _detect_framework(graph) == "langgraph"


def test_detects_langchain_runnable_as_langgraph():
    runnable = _make_instance("langchain_core.runnables.base", "RunnableSequence")
    assert _detect_framework(runnable) == "langgraph"


def test_detects_openai_agents_sdk_agent():
    agent = _make_instance("agents", "Agent")
    assert _detect_framework(agent) == "openai_agents"


def test_detects_openai_agents_sdk_agent_from_submodule():
    agent = _make_instance("agents.agent", "Agent")
    assert _detect_framework(agent) == "openai_agents"


def test_detects_pydanticai_agent():
    agent = _make_instance("pydantic_ai", "Agent")
    assert _detect_framework(agent) == "pydanticai"


def test_detects_pydanticai_agent_from_submodule():
    agent = _make_instance("pydantic_ai.agent", "Agent")
    assert _detect_framework(agent) == "pydanticai"


def test_returns_unknown_for_unrelated_object():
    assert _detect_framework(object()) == "unknown"


def test_returns_unknown_for_similarly_named_but_unrelated_class():
    # An "Agent" class from some unrelated package should not false-positive.
    other = _make_instance("myapp.agents", "Agent")
    assert _detect_framework(other) == "unknown"
