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


def test_detects_crewai_crew():
    crew = _make_instance("crewai", "Crew")
    assert _detect_framework(crew) == "crewai"


def test_detects_crewai_crew_from_submodule():
    crew = _make_instance("crewai.crew", "Crew")
    assert _detect_framework(crew) == "crewai"


def test_returns_unknown_for_a_crewai_module_class_that_is_not_a_crew():
    task = _make_instance("crewai", "Task")
    assert _detect_framework(task) == "unknown"


def test_detects_autogen_conversable_agent():
    agent = _make_instance("autogen", "ConversableAgent")
    assert _detect_framework(agent) == "autogen"


def test_detects_autogen_agent_from_submodule():
    agent = _make_instance("autogen.agentchat.conversable_agent", "ConversableAgent")
    assert _detect_framework(agent) == "autogen"


def test_detects_autogen_assistant_agent():
    agent = _make_instance("autogen", "AssistantAgent")
    assert _detect_framework(agent) == "autogen"


def test_returns_unknown_for_an_autogen_module_class_without_agent_in_the_name():
    group_chat = _make_instance("autogen", "GroupChat")
    assert _detect_framework(group_chat) == "unknown"


def test_returns_unknown_for_unrelated_object():
    assert _detect_framework(object()) == "unknown"


def test_returns_unknown_for_similarly_named_but_unrelated_class():
    # An "Agent" class from some unrelated package should not false-positive.
    other = _make_instance("myapp.agents", "Agent")
    assert _detect_framework(other) == "unknown"


def test_returns_unknown_for_similarly_named_but_unrelated_crewai_and_autogen_classes():
    other_crew = _make_instance("myapp.crewai", "Crew")
    other_agent = _make_instance("myapp.autogen", "ConversableAgent")
    assert _detect_framework(other_crew) == "unknown"
    assert _detect_framework(other_agent) == "unknown"
