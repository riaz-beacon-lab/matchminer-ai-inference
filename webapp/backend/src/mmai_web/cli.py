"""Command line entry point: ``uv run mmai-web {serve,mcp,warmup}``."""

from __future__ import annotations

import argparse
import logging
import os


def main() -> None:
    parser = argparse.ArgumentParser(prog="mmai-web")
    sub = parser.add_subparsers(dest="command", required=True)
    serve = sub.add_parser("serve", help="Flask API + MCP (/mcp) over HTTP")
    serve.add_argument("--host")
    serve.add_argument("--port", type=int)
    sub.add_parser("mcp", help="MCP server over stdio")
    sub.add_parser("warmup", help="Embed the trial corpus and load models")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # The llama.cpp server for the optional LLM review does not check keys.
    os.environ.setdefault("OPENAI_API_KEY", "not-needed")

    if args.command == "serve":
        import uvicorn

        from mmai_web.asgi import create_asgi_app
        from mmai_web.services import get_services

        settings = get_services().settings
        uvicorn.run(
            create_asgi_app(),
            host=args.host or settings.host,
            port=args.port or settings.port,
        )
    elif args.command == "mcp":
        # stdout is the MCP channel: keep logs on stderr (basicConfig default).
        from mmai_web.mcp_server import mcp

        mcp.run(transport="stdio")
    elif args.command == "warmup":
        from mmai_web.services import get_services

        spaces = get_services().trials.embedded_spaces()
        print(f"trial spaces embedded: {len(spaces)}")


if __name__ == "__main__":
    main()
