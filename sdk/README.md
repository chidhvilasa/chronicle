# chronicle-sdk

Python SDK for [Chronicle](../README.md) — the Chrome DevTools for AI agents.

Instrument your agent code with `ChronicleTracer` to capture tool calls, LLM
calls, agent messages, memory updates, errors, and retries. Events are
buffered and flushed to a local Chronicle server over HTTP in batches; if the
server isn't running, unsent events are written to
`chronicle_runs/{run_id}.json` so nothing is lost.

## Install

```bash
pip install -e .
```

## Usage

```python
from chronicle import ChronicleTracer

with ChronicleTracer() as tracer:
    tracer.record_event("tool_call", data={"tool_name": "search", "arguments": {"query": "weather in nyc"}})
    tracer.record_event("llm_call", data={"model": "gpt-4o", "prompt": "What's the weather?"})
    tracer.record_event("agent_message", data={"role": "assistant", "content": "It's sunny."})
```

## LangGraph / LangChain

```python
from chronicle import ChronicleTracer, LangGraphAdapter

tracer = ChronicleTracer()
adapter = LangGraphAdapter(tracer)

graph.invoke(input, config={"callbacks": [adapter]})
```

## Development

```bash
pip install -e ".[dev]"
pytest
```
