"""In-memory registry of LangGraph graph objects, for the replay engine.

Graphs are registered by *module path + attribute name* and re-imported on
demand — never pickled. Pickling an arbitrary object sent over HTTP is a
remote code execution risk (unpickling runs attacker-controlled code), so
`POST /register` only ever accepts an import path and calls
`importlib.import_module` on it, exactly like a normal Python import
statement would.
"""

from __future__ import annotations

import importlib
from typing import Any


class GraphRegistrationError(Exception):
    """Raised when a graph module/attribute can't be imported."""


class GraphRegistry:
    """Holds registered graph objects in memory for the server process's lifetime."""

    def __init__(self) -> None:
        self._graphs: dict[str, Any] = {}
        self._active_name: str | None = None

    def register(self, graph_module: str, graph_attr: str) -> str:
        """Imports `graph_module` and reads `graph_attr` off it; returns the registered name."""
        try:
            module = importlib.import_module(graph_module)
        except ImportError as exc:
            raise GraphRegistrationError(
                f"Could not import {graph_module}. Make sure the module is in your Python path."
            ) from exc

        if not hasattr(module, graph_attr):
            raise GraphRegistrationError(
                f"Module {graph_module} has no attribute {graph_attr!r}."
            )

        name = f"{graph_module}.{graph_attr}"
        self._graphs[name] = getattr(module, graph_attr)
        self._active_name = name
        return name

    def get_active(self) -> Any | None:
        """Returns the most recently registered graph, or `None` if none has been registered."""
        if self._active_name is None:
            return None
        return self._graphs.get(self._active_name)

    def list_names(self) -> list[str]:
        return sorted(self._graphs)
