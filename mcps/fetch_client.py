# mcps/fetch_client.py
from __future__ import annotations

import logging
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger("fetch_client")


class FetchClient:
    """Singleton MCP client that manages the fetch server subprocess lifecycle.

    Usage:
        await fetch_client.startup()   # call once at app boot
        result = await fetch_client.call_tool("fetch", {"url": "https://..."})
        await fetch_client.shutdown()  # call once at app exit
    """

    def __init__(self) -> None:
        self._session: ClientSession | None = None
        self._exit_stack = None

    async def startup(self) -> None:
        """Start the MCP fetch server subprocess and open a session."""
        from contextlib import AsyncExitStack
        
        self._exit_stack = AsyncExitStack()
        server_params = StdioServerParameters(
            command="uvx",
            args=["mcp-server-fetch"],
        )
        stdio_transport = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        read, write = stdio_transport
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        await self._session.initialize()
        logger.info("fetch_client | MCP fetch server started")

    async def shutdown(self) -> None:
        """Stop the MCP fetch server subprocess."""
        if self._exit_stack:
            await self._exit_stack.aclose()
            self._session = None
            self._exit_stack = None
            logger.info("fetch_client | MCP fetch server stopped")

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Call a tool on the running MCP fetch server.

        Args:
            tool_name:  Name of the tool to call (e.g. "fetch").
            arguments:  Dict of arguments to pass to the tool.

        Returns:
            Tool result as a string.

        Raises:
            RuntimeError: if the session has not been started via startup().
        """
        if self._session is None:
            raise RuntimeError(
                "FetchClient is not started. "
                "Call await fetch_client.startup() before calling call_tool()."
            )
        result = await self._session.call_tool(tool_name, arguments)
        # result.content is a list of content blocks; extract text
        texts = [
            block.text
            for block in result.content
            if hasattr(block, "text")
        ]
        return "\n".join(texts)


# Module-level singleton — importing this module twice gives the same object
fetch_client = FetchClient()