import asyncio
import logging
from contextlib import AsyncExitStack

import mcp
import mcp.types as types
from eunomia import *
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server import NotificationOptions, Server
from mcp.server.models import InitializationOptions

from .config import Settings

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

settings = Settings()
server = Server(settings.APP_NAME)
eunomia_orchestra = settings.ORCHESTRA

SERVER_TOOLS_SEP = "___"
SERVER_PROMPTS_SEP = "___"
SERVER_RESOURCES_SEP = "___"

servers_sessions = {}


#
# -----------------------
#  TOOLS IMPLEMENTATION
# -----------------------
#
@server.list_tools()
async def list_tools() -> list[types.Tool]:
    server_tools = []

    for server_name, session in servers_sessions.items():
        response = await session.list_tools()

        # Rename and flatten
        for tool in response.tools:
            renamed_tool = types.Tool(
                name=f"{server_name}{SERVER_TOOLS_SEP}{tool.name}",
                description=tool.description,
                inputSchema=tool.inputSchema,
            )
            server_tools.append(renamed_tool)

    return server_tools


@server.call_tool()
async def call_tool(
    name: str, arguments: dict
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    server_name, tool_name = name.split(SERVER_TOOLS_SEP, 1)

    try:
        if server_name not in servers_sessions:
            raise ValueError(f"No session found for sub-server: {server_name}")

        session = servers_sessions[server_name]
        logging.debug(
            f"Calling tool: {tool_name} on server: {server_name} with arguments: {arguments}"
        )

        result = await asyncio.wait_for(
            session.call_tool(tool_name, arguments), timeout=10
        )

    except asyncio.TimeoutError:
        logging.error(f"Timeout while calling tool '{tool_name}'")
        raise
    except Exception as e:
        logging.exception(f"Error during call_tool for '{tool_name}'")
        raise

    # Optionally run through Eunomia
    logging.debug("Running eunomia orchestra...")
    full_content_post_eunomia = []
    try:
        for content in result.content:
            if content.type == "text":
                text_post_eunomia = eunomia_orchestra.run(content.text)
                full_content_post_eunomia.append(text_post_eunomia)
            else:
                # For non-text content, just pass it through
                full_content_post_eunomia.append(content)
    except Exception as e:
        logging.exception(f"Error running eunomia_orchestra: {e}")

    # Return them as text content for simplicity
    # or adapt as needed to preserve images/embeds.
    return [types.TextContent(type="text", text=str(full_content_post_eunomia))]


#
# -----------------------
#  PROMPTS IMPLEMENTATION
# -----------------------
#
@server.list_prompts()
async def list_prompts() -> list[types.Prompt]:
    """
    Aggregate and rename prompts from each sub-server.
    """
    aggregated_prompts = []

    for server_name, session in servers_sessions.items():
        try:
            response = await session.list_prompts()
            # response.prompts is typically the list of prompts
            for prompt in response.prompts:
                # Optionally rename prompt to avoid collisions
                renamed_prompt = types.Prompt(
                    name=f"{server_name}{SERVER_PROMPTS_SEP}{prompt.name}",
                    description=prompt.description,
                    arguments=prompt.arguments,
                )
                aggregated_prompts.append(renamed_prompt)
        except Exception as e:
            logger.exception(
                f"Failed to list_prompts from sub-server {server_name}: {e}"
            )

    return aggregated_prompts


@server.get_prompt()
async def get_prompt(
    name: str, arguments: dict[str, str] | None = None
) -> types.GetPromptResult:
    """
    Route the get_prompt call to the correct sub-server,
    and return the prompt's messages.
    """
    # Extract sub-server name and actual prompt name
    server_name, prompt_name = name.split(SERVER_PROMPTS_SEP, 1)

    if server_name not in servers_sessions:
        raise ValueError(f"No session found for sub-server: {server_name}")

    session = servers_sessions[server_name]
    try:
        result = await session.get_prompt(prompt_name, arguments)
        return result
    except Exception as e:
        logger.exception(
            f"Failed to get_prompt '{prompt_name}' from sub-server {server_name}: {e}"
        )
        raise


#
# -----------------------
#  RESOURCES IMPLEMENTATION
# -----------------------
#
@server.list_resources()
async def list_resources() -> list[types.Resource]:
    """
    Aggregate and rename resources from each sub-server.
    """
    aggregated_resources = []

    for server_name, session in servers_sessions.items():
        try:
            response = await session.list_resources()
            for resource in response.resources:
                new_uri = f"{server_name}{SERVER_RESOURCES_SEP}{resource.uri}"
                renamed_resource = types.Resource(
                    uri=new_uri,
                    name=f"{server_name}{SERVER_RESOURCES_SEP}{resource.name}",
                    mimeType=resource.mimeType,
                )
                aggregated_resources.append(renamed_resource)
        except Exception as e:
            logger.exception(
                f"Failed to list_resources from sub-server {server_name}: {e}"
            )

    return aggregated_resources


@server.read_resource()
async def read_resource(uri: types.AnyUrl) -> str:
    """
    Extract the sub-server name from the prefixed URI,
    then call the read_resource on that sub-server.
    """
    uri_str = str(uri)

    if SERVER_RESOURCES_SEP not in uri_str:
        raise ValueError("Invalid resource URI format (missing sub-server prefix).")

    server_name, real_uri = uri_str.split(SERVER_RESOURCES_SEP, 1)

    if server_name not in servers_sessions:
        raise ValueError(f"No session found for sub-server: {server_name}")

    session = servers_sessions[server_name]
    try:
        result = await session.read_resource(real_uri)
        return result.content
    except Exception as e:
        logger.exception(
            f"Failed to read_resource '{real_uri}' from sub-server {server_name}: {e}"
        )
        raise


#
# -----------------------
#  SERVER MAIN
# -----------------------
#
async def main():
    """
    Main entry point for the aggregator MCP server.
    Sets up and runs the server using stdin/stdout streams.
    """
    async with AsyncExitStack() as stack:
        await initialize_sub_servers(stack)

        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name=settings.APP_NAME,
                    server_version=settings.APP_VERSION,
                    capabilities=server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )


async def initialize_sub_servers(stack: AsyncExitStack):
    """
    Create and initialize sessions for each sub-server,
    storing them in the global servers_sessions dictionary.
    """
    for server_name, params in settings.MCP_SERVERS.items():
        command = params.get("command")
        args = params.get("args", [])
        env = params.get("env")

        server_params = StdioServerParameters(command=command, args=args, env=env)

        stdio_transport = await stack.enter_async_context(stdio_client(server_params))
        stdio, write = stdio_transport

        session = await stack.enter_async_context(ClientSession(stdio, write))
        await session.initialize()

        servers_sessions[server_name] = session
