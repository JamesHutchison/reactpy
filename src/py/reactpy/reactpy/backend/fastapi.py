from __future__ import annotations

from fastapi import FastAPI

from reactpy.backend import starlette

serve_development_app = starlette.serve_development_app
"""Alias for :func:`reactpy.backend.starlette.serve_development_app`"""

use_connection = starlette.use_connection
"""Alias for :func:`reactpy.backend.starlette.use_location`"""

use_websocket = starlette.use_websocket
"""Alias for :func:`reactpy.backend.starlette.use_websocket`"""

Options = starlette.Options
"""Alias for :class:`reactpy.backend.starlette.Options`"""

configure = starlette.configure
"""Alias for :class:`reactpy.backend.starlette.configure`"""


def create_development_app() -> FastAPI:
    """Create a development ``FastAPI`` application instance."""
    return FastAPI(debug=True)