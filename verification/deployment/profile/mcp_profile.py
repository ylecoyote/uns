import asyncio,os
from agsignal_mcp.factory import create_mcp_server
from agsignal_mcp.runtime import MCPRuntimeConfig
from agsignal_mcp.transports.stdio import _serve
from runtime_profile import make_runtime
config=MCPRuntimeConfig(mode='stdio-persistent',read_only=False,operator_principal='smoke-operator',delivery_confirmation_token=os.environ['UNS_MCP_DELIVERY_CONFIRMATION_TOKEN'])
asyncio.run(_serve(create_mcp_server(config,runtime=make_runtime())))
