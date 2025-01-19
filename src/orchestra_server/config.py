"""
Configuration Settings for MCP Orchestra Server
==============================================

This module defines the settings and configuration options for the MCP Orchestra Server
using pydantic for settings management and validation.
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
        ### INSERT SERVERS HERE ###
    }
    ORCHESTRA: Orchestra = None  ### INSERT EUNOMIA ORCHESTRA HERE ###
