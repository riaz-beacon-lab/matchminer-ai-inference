"""One ASGI app: MCP (streamable HTTP) at /mcp, the Flask API everywhere else."""

from __future__ import annotations

from asgiref.wsgi import WsgiToAsgi
from starlette.routing import Mount

from mmai_web.app import create_app
from mmai_web.mcp_server import mcp


def create_asgi_app():
    # FastMCP's Starlette app owns the /mcp route and the MCP session lifespan;
    # Flask is mounted as the catch-all behind it.
    app = mcp.streamable_http_app(stateless_http=True, json_response=True)
    app.router.routes.append(Mount("/", app=WsgiToAsgi(create_app())))
    return app
