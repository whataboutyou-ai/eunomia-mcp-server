"""
Example Settings for MCP Orchestra Server
==============================================

This example shows how we can combine Eunomia with a web-browser-mcp-server (https://github.com/blazickjp/web-browser-mcp-server) 
"""

from eunomia.instruments import IdbacInstrument, PiiInstrument
from eunomia.orchestra import Orchestra
from pydantic import ConfigDict
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application settings class for MCP orchestra server using pydantic_settings.

    Attributes:
        APP_NAME (str): Name of the application
        APP_VERSION (str): Current version of the application
        LOG_LEVEL (str): Logging level (default: "info")
        MCP_SERVERS (dict): Servers to be connected
        ORCHESTRA (Orchestra): Orchestra class from Eunomia to define data governance policies
    """

    APP_NAME: str = "mcp-server_orchestra"
    APP_VERSION: str = "0.1.0"
    LOG_LEVEL: str = "info"
    MCP_SERVERS: dict = {
        "web-browser-mcp-server": {
            "command": "uv",
            "args": ["tool", "run", "web-browser-mcp-server"],
            "env": {"REQUEST_TIMEOUT": "30"},
        }
    }
    ORCHESTRA: Orchestra = Orchestra(
        instruments=[
            PiiInstrument(entities=["EMAIL_ADDRESS", "PERSON"], edit_mode="replace")
        ]
    )

    model_config = ConfigDict(env_file=".env", env_file_encoding="utf-8")
