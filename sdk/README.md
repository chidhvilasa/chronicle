# chronicle-sdk

Python SDK for [Chronicle](../README.md) — the Chrome DevTools for AI agents.

Instrument your agent code with `ChronicleTracer` to capture tool calls, LLM
calls, agent messages, memory updates, errors, and retries. Events are sent to
a local Chronicle server over HTTP; if the server isn't running, events are
written directly to a local SQLite database so nothing is lost.

## Install

```bash
pip install -e .
```

## Usage

```python
from chronicle import ChronicleTracer

with ChronicleTracer() as tracer:
    tracer.tool_call("search", {"query": "weather in nyc"})
    tracer.llm_call(model="gpt-4o", prompt="What's the weather?")
    tracer.agent_message(role="assistant", content="It's sunny.")
```

## LangGraph / LangChain

```python
from chronicle import ChronicleTracer
from chronicle.integrations.langgraph import ChronicleCallbackHandler

tracer = ChronicleTracer()
handler = ChronicleCallbackHandler(tracer)

graph.invoke(input, config={"callbacks": [handler]})
```

## Development

```bash
pip install -e ".[dev]"
pytest
```
