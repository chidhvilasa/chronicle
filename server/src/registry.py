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
import re
from typing import Any

# One or more dotted segments, each starting with a letter/underscore and containing only
# alphanumerics/underscores after that - the same shape `import a.b.c` accepts. This
# rejects slashes, a leading dot, consecutive dots (an empty segment), and anything else
# that isn't a plain Python dotted module path, before it ever reaches importlib.
_MODULE_PATH_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$")
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class GraphRegistrationError(Exception):
    """Raised when a graph module/attribute can't be imported."""


class GraphRegistry:
    """Holds registered graph objects in memory for the server process's lifetime."""

    def __init__(self) -> None:
        self._graphs: dict[str, Any] = {}
        self._active_name: str | None = None

    def register(self, graph_module: str, graph_attr: str) -> str:
        """Imports `graph_module` and reads `graph_attr` off it; returns the registered name.

        `graph_module` is validated against a strict dotted-identifier allowlist before
        `importlib.import_module` ever sees it — rejecting slashes, a leading dot, or
        `..` prevents it from being used to reach outside the normal Python module
        namespace (e.g. relative-import escapes). `graph_attr` must be a plain identifier.
        """
        if not _MODULE_PATH_PATTERN.match(graph_module):
            raise GraphRegistrationError(
                f"Invalid graph_module {graph_module!r}: must be a dotted Python module "
                "path (letters, digits, underscores, and single dots only)."
            )
        if not _IDENTIFIER_PATTERN.match(graph_attr):
            raise GraphRegistrationError(
                f"Invalid graph_attr {graph_attr!r}: must be a valid Python identifier."
            )

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
