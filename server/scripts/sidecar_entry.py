"""Entry point for the PyInstaller-bundled Chronicle server sidecar.

Not used by the normal `pip install chronicle-server` / `chronicle start` /
`uvicorn src.main:app` paths - this exists only so PyInstaller has a single
script to analyze and freeze. Imports the `app` object directly (rather than
uvicorn's `"module:app"` import-string form) and runs with `reload=False`,
since a frozen binary has no source tree for the reloader to watch and no
`multiprocessing`-spawn-by-re-exec path to rely on.

Host/port are read from CHRONICLE_HOST/CHRONICLE_PORT so the Tauri sidecar
launcher can pin them without needing command-line argument parsing here.
"""

import os

import uvicorn

from src.main import DEFAULT_HOST, DEFAULT_PORT, app

if __name__ == "__main__":
    host = os.environ.get("CHRONICLE_HOST", DEFAULT_HOST)
    port = int(os.environ.get("CHRONICLE_PORT", str(DEFAULT_PORT)))
    uvicorn.run(app, host=host, port=port, reload=False)
