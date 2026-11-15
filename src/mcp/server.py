"""
MCP Server implementation — JSON-RPC 2.0 over stdio.
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """MCP Server configuration."""
    name: str = "LP-PC Suite"
    version: str = "1.0.0"
    description: str = "Lucky Patcher PC Suite MCP Server"
    capabilities: dict[str, Any] = field(default_factory=lambda: {
        "tools": True,
        "resources": True,
        "prompts": True,
    })
    log_level: str = "INFO"


class JSONRPCError(Exception):
    """JSON-RPC 2.0 error."""

    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(f"JSON-RPC Error {code}: {message}")

    def to_dict(self) -> dict[str, Any]:
        result = {"code": self.code, "message": self.message}
        if self.data is not None:
            result["data"] = self.data
        return result


# JSON-RPC 2.0 error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class MCPServer:
    """
    MCP Server — handles JSON-RPC 2.0 requests over stdio.

    Protocol:
    - Request: {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {...}}
    - Response: {"jsonrpc": "2.0", "id": 1, "result": {...}}
    - Error: {"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "Method not found"}}
    - Notification: {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
    """

    def __init__(self, config: MCPServerConfig | None = None):
        self.config = config or MCPServerConfig()
        self.tools: dict[str, Callable] = {}
        self.resources: dict[str, Callable] = {}
        self.prompts: dict[str, Callable] = {}
        self._initialized = False
        self._tool_schemas: dict[str, dict] = {}
        self._resource_schemas: dict[str, dict] = {}
        self._prompt_schemas: dict[str, dict] = {}

    def register_tool(self, name: str, func: Callable, schema: dict | None = None):
        """Register a tool (function) with optional schema."""
        self.tools[name] = func
        if schema:
            self._tool_schemas[name] = schema

    def register_resource(self, uri: str, func: Callable, schema: dict | None = None):
        """Register a resource handler."""
        self.resources[uri] = func
        if schema:
            self._resource_schemas[uri] = schema

    def register_prompt(self, name: str, func: Callable, schema: dict | None = None):
        """Register a prompt template."""
        self.prompts[name] = func
        if schema:
            self._prompt_schemas[name] = schema

    async def handle_request(self, request: dict[str, Any]) -> dict[str, Any] | None:
        """Handle incoming JSON-RPC request."""
        # Validate request
        if not isinstance(request, dict):
            return self._error_response(None, INVALID_REQUEST, "Invalid request format")

        jsonrpc = request.get("jsonrpc")
        if jsonrpc != "2.0":
            return self._error_response(request.get("id"), INVALID_REQUEST, "Invalid JSON-RPC version")

        method = request.get("method")
        if not method:
            return self._error_response(request.get("id"), INVALID_REQUEST, "Missing method")

        request_id = request.get("id")
        params = request.get("params", {})

        try:
            # Handle built-in methods
            if method == "initialize":
                return await self._handle_initialize(request_id, params)
            elif method == "notifications/initialized":
                self._initialized = True
                return None  # No response for notifications
            elif method == "tools/list":
                return await self._handle_tools_list(request_id)
            elif method == "tools/call":
                return await self._handle_tool_call(request_id, params)
            elif method == "resources/list":
                return await self._handle_resources_list(request_id)
            elif method == "resources/read":
                return await self._handle_resource_read(request_id, params)
            elif method == "prompts/list":
                return await self._handle_prompts_list(request_id)
            elif method == "prompts/get":
                return await self._handle_prompt_get(request_id, params)
            else:
                return self._error_response(request_id, METHOD_NOT_FOUND, f"Method not found: {method}")
        except JSONRPCError as e:
            return self._error_response(request_id, e.code, e.message, e.data)
        except Exception as e:
            logger.exception("Internal error handling request")
            return self._error_response(request_id, INTERNAL_ERROR, str(e))

    async def _handle_initialize(self, request_id: Any, params: dict) -> dict[str, Any]:
        """Handle initialize request."""
        client_info = params.get("clientInfo", {})
        client_name = client_info.get("name", "unknown")
        client_version = client_info.get("version", "unknown")

        logger.info(f"MCP initialize from {client_name} {client_version}")

        return self._success_response(request_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": self.config.capabilities,
            "serverInfo": {
                "name": self.config.name,
                "version": self.config.version,
            },
        })

    async def _handle_tools_list(self, request_id: Any) -> dict[str, Any]:
        """Handle tools/list request."""
        tools = []
        for name, func in self.tools.items():
            schema = self._tool_schemas.get(name, {})
            tools.append({
                "name": name,
                "description": schema.get("description", func.__doc__ or ""),
                "inputSchema": schema.get("inputSchema", {"type": "object", "properties": {}}),
            })

        return self._success_response(request_id, {"tools": tools})

    async def _handle_tool_call(self, request_id: Any, params: dict) -> dict[str, Any]:
        """Handle tools/call request."""
        name = params.get("name")
        arguments = params.get("arguments", {})

        if not name:
            raise JSONRPCError(INVALID_PARAMS, "Missing tool name")

        if name not in self.tools:
            raise JSONRPCError(METHOD_NOT_FOUND, f"Tool not found: {name}")

        func = self.tools[name]

        # Validate arguments against schema if available
        schema = self._tool_schemas.get(name, {})
        input_schema = schema.get("inputSchema")
        if input_schema:
            self._validate_arguments(arguments, input_schema, name)

        # Call the tool function
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(**arguments)
            else:
                result = func(**arguments)
        except TypeError as e:
            raise JSONRPCError(INVALID_PARAMS, f"Invalid arguments for {name}: {e}") from e
        except Exception as e:
            raise JSONRPCError(INTERNAL_ERROR, f"Tool execution failed: {e}") from e

        return self._success_response(request_id, result)

    async def _handle_resources_list(self, request_id: Any) -> dict[str, Any]:
        """Handle resources/list request."""
        resources = []
        for uri, func in self.resources.items():
            schema = self._resource_schemas.get(uri, {})
            resources.append({
                "uri": uri,
                "name": schema.get("name", uri),
                "description": schema.get("description", func.__doc__ or ""),
                "mimeType": schema.get("mimeType", "application/json"),
            })

        return self._success_response(request_id, {"resources": resources})

    async def _handle_resource_read(self, request_id: Any, params: dict) -> dict[str, Any]:
        """Handle resources/read request."""
        uri = params.get("uri")

        if not uri:
            raise JSONRPCError(INVALID_PARAMS, "Missing resource URI")

        if uri not in self.resources:
            raise JSONRPCError(METHOD_NOT_FOUND, f"Resource not found: {uri}")

        func = self.resources[uri]

        try:
            if asyncio.iscoroutinefunction(func):
                content = await func()
            else:
                content = func()
        except Exception as e:
            raise JSONRPCError(INTERNAL_ERROR, f"Resource read failed: {e}") from e

        return self._success_response(request_id, {
            "contents": [{
                "uri": uri,
                "mimeType": self._resource_schemas.get(uri, {}).get("mimeType", "application/json"),
                "text": content if isinstance(content, str) else json.dumps(content, indent=2),
            }]
        })

    async def _handle_prompts_list(self, request_id: Any) -> dict[str, Any]:
        """Handle prompts/list request."""
        prompts = []
        for name, func in self.prompts.items():
            schema = self._prompt_schemas.get(name, {})
            prompts.append({
                "name": name,
                "description": schema.get("description", func.__doc__ or ""),
                "arguments": schema.get("arguments", []),
            })

        return self._success_response(request_id, {"prompts": prompts})

    async def _handle_prompt_get(self, request_id: Any, params: dict) -> dict[str, Any]:
        """Handle prompts/get request."""
        name = params.get("name")
        arguments = params.get("arguments", {})

        if not name:
            raise JSONRPCError(INVALID_PARAMS, "Missing prompt name")

        if name not in self.prompts:
            raise JSONRPCError(METHOD_NOT_FOUND, f"Prompt not found: {name}")

        func = self.prompts[name]

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(**arguments)
            else:
                result = func(**arguments)
        except Exception as e:
            raise JSONRPCError(INTERNAL_ERROR, f"Prompt execution failed: {e}") from e

        return self._success_response(request_id, {
            "description": self._prompt_schemas.get(name, {}).get("description", ""),
            "messages": result if isinstance(result, list) else [{"role": "user", "content": str(result)}],
        })

    def _validate_arguments(self, args: dict, schema: dict, tool_name: str):
        """Validate arguments against JSON schema (basic validation)."""
        # Basic type checking
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for req in required:
            if req not in args:
                raise JSONRPCError(INVALID_PARAMS, f"Missing required argument: {req}")

        for key, value in args.items():
            if key in properties:
                prop_schema = properties[key]
                expected_type = prop_schema.get("type")
                if expected_type:
                    if expected_type == "string" and not isinstance(value, str):
                        raise JSONRPCError(INVALID_PARAMS, f"Argument {key} must be string")
                    elif expected_type == "integer" and not isinstance(value, int):
                        raise JSONRPCError(INVALID_PARAMS, f"Argument {key} must be integer")
                    elif expected_type == "boolean" and not isinstance(value, bool):
                        raise JSONRPCError(INVALID_PARAMS, f"Argument {key} must be boolean")
                    elif expected_type == "array" and not isinstance(value, list):
                        raise JSONRPCError(INVALID_PARAMS, f"Argument {key} must be array")
                    elif expected_type == "object" and not isinstance(value, dict):
                        raise JSONRPCError(INVALID_PARAMS, f"Argument {key} must be object")

    def _success_response(self, request_id: Any, result: Any) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": result,
        }

    def _error_response(self, request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": error,
        }

    async def run_stdio(self):
        """Run server over stdio (for MCP clients)."""
        logger.info(f"Starting MCP server: {self.config.name} v{self.config.version}")

        # Read from stdin line by line
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        writer_transport, writer_protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, loop)

        try:
            while True:
                line = await reader.readline()
                if not line:
                    break

                line = line.decode('utf-8').strip()
                if not line:
                    continue

                try:
                    request = json.loads(line)
                except json.JSONDecodeError as e:
                    response = self._error_response(None, PARSE_ERROR, f"Parse error: {e}")
                    await self._send_response(writer, response)
                    continue

                response = await self.handle_request(request)
                if response is not None:
                    await self._send_response(writer, response)
        finally:
            writer.close()
            await writer.wait_closed()

    async def _send_response(self, writer: asyncio.StreamWriter, response: dict):
        """Send JSON-RPC response."""
        data = json.dumps(response, ensure_ascii=False) + "\n"
        writer.write(data.encode('utf-8'))
        await writer.drain()


async def run_mcp_server(config: MCPServerConfig | None = None):
    """Run MCP server with default tools/resources/prompts."""
    from .prompts import register_prompts
    from .resources import register_resources
    from .tools import register_tools

    server = MCPServer(config)
    register_tools(server)
    register_resources(server)
    register_prompts(server)

    await server.run_stdio()


# Synchronous wrapper for CLI entry point
def main():
    """Synchronous entry point for MCP server."""
    import logging
    logging.basicConfig(level=logging.INFO, format='%(name)s: %(message)s')

    config = MCPServerConfig()
    asyncio.run(run_mcp_server(config))


if __name__ == "__main__":
    main()
