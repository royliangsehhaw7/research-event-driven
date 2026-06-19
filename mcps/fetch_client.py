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

# https://dev.to/mayankcse/fastmcp-simplifying-ai-context-management-with-the-model-context-protocol-37l9
# https://www.freecodecamp.org/news/how-to-build-your-first-mcp-server-using-fastmcp/
# https://medium.com/@laurentkubaski/understanding-mcp-stdio-transport-protocol-ae3d5daf64db


# THIS IS A MCP CLIENT BUT WILL spawns the server (StdioTransport)
fetch_client = Client(
    StdioTransport(command="python", args=["-m", "mcp_server_fetch"])
)


# using uvx - it will fetch directly from PyPi (but runs in an isolated environment)
# fetch_client = Client(
#     StdioTransport(command="uvx", args=["mcp-server-fetch"])
# )






# ======================CORE PYTHON MCP SDK ========================== #
# import asyncio
# from mcp.server.models import InitializationOptions
# import mcp.types as types
# from mcp.server import Server, NotificationOptions
# from mcp.server.stdio import stdio_server

# # 1. Initialize the base MCP server
# server = Server("Demo Server 🚀")

# # 2. Register the available tools
# @server.list_tools()
# async def handle_list_tools() -> list[types.Tool]:
#     """List available tools. 
#     Unlike FastMCP, you must explicitly define the JSON Schema for arguments.
#     """
#     return [
#         types.Tool(
#             name="add",
#             description="Add two numbers and return the result",
#             inputSchema={
#                 "type": "object",
#                 "properties": {
#                     "a": {"type": "integer", "description": "The first number"},
#                     "b": {"type": "integer", "description": "The second number"},
#                 },
#                 "required": ["a", "b"],
#             },
#         )
#     ]

# # 3. Handle the actual execution of the tool
# @server.call_tool()
# async def handle_call_tool(
#     name: str, arguments: dict | None
# ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
#     """Execute the requested tool."""
#     if name != "add":
#         raise ValueError(f"Unknown tool: {name}")

#     if not arguments or "a" not in arguments or "b" not in arguments:
#         raise ValueError("Missing required arguments 'a' or 'b'")

#     # Extract arguments and execute core logic
#     try:
#         a = int(arguments["a"])
#         b = int(arguments["b"])
#         result = a + b
#     except (ValueError, TypeError) as e:
#         raise ValueError(f"Invalid argument types: {e}")

#     # Return the formatted response required by the MCP protocol
#     return [
#         types.TextContent(
#             type="text",
#             text=str(result)
#         )
#     ]

# # 4. Handle the server lifecycle and transport
# async def main():
#     # Run the server using stdin/stdout streams
#     async with stdio_server() as (read_stream, write_stream):
#         await server.run(
#             read_stream,
#             write_stream,
#             InitializationOptions(
#                 server_name="Demo Server 🚀",
#                 server_version="0.1.0",
#                 capabilities=server.get_capabilities(
#                     notification_options=NotificationOptions(),
#                     experimental_capabilities={},
#                 ),
#             ),
#         )

# if __name__ == "__main__":
#     asyncio.run(main())