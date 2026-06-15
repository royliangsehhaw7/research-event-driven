# mcps/fetch_client.py
from __future__ import annotations

from fastmcp import Client
from fastmcp.client.transports import StdioTransport

# Single shared client for the Fetch MCP server. Import this instance
# everywhere `fetch_page` needs it — do not construct a new Client.
#
# Lifecycle: entered once via `async with fetch_client:` around the pipeline
# run (see main.py). Re-entrant and ref-counted, so it's safe for multiple
# agents to also enter/exit it concurrently if needed — fastmcp keeps the
# subprocess and session alive until the last exit.
fetch_client = Client(
    StdioTransport(command="python", args=["-m", "mcp_server_fetch"])
)