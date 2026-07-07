"""Chronicle SDK: instrument AI agents and ship traces to a Chronicle server.

Zero-friction quickstart:

    import chronicle
    graph = chronicle.instrument(graph)

See `README.md` for the full quickstart. Everything from v0.1.0/v0.2.0
(`ChronicleTracer`, `LangGraphAdapter`, event/snapshot models) still works
exactly as before — `instrument()` is a convenience wrapper around it, not
a replacement.
"""

from chronicle.adapters.langgraph import LangGraphAdapter
from chronicle.auto import instrument, instrument_context
from chronicle.models import ChronicleEvent, EventType, StateSnapshot, TokenUsage
from chronicle.server_manager import ServerManager
from chronicle.tracer import ChronicleTracer

__version__ = "0.6.0"

__all__ = [
    "ChronicleTracer",
    "LangGraphAdapter",
    "ChronicleEvent",
    "EventType",
    "StateSnapshot",
    "TokenUsage",
    "ServerManager",
    "instrument",
    "instrument_context",
    "__version__",
]
