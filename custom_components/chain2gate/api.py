"""Small asynchronous HTTP/WebSocket transport using HA's shared aiohttp session."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import aiohttp

from .const import FRAME_TIMEOUT, HTTP_TIMEOUT
from .protocol import valid_host


class CannotConnect(Exception):
    """The gateway cannot be reached or returned invalid identification."""


class Chain2GateClient:
    """HTTP identification and WebSocket updates for one gateway."""

    def __init__(self, session: aiohttp.ClientSession, host: str) -> None:
        self.session = session
        self.host = valid_host(host)
        self._ws: aiohttp.ClientWebSocketResponse | None = None

    async def get_json(self, path: str) -> dict[str, Any]:
        """Get a bounded HTTP JSON response (some firmware mislabels its content type)."""
        async with asyncio.timeout(HTTP_TIMEOUT):
            async with self.session.get(f"http://{self.host}/{path}") as response:
                response.raise_for_status()
                data = await response.json(content_type=None)
        if not isinstance(data, dict):
            raise ValueError("Response must be an object")
        return data

    async def identify(self) -> dict[str, Any]:
        """Validate a Chain2Gate identity, not just that an HTTP server is present."""
        try:
            data = await self.get_json("info.json")
            if not isinstance(data, dict):
                raise ValueError("Invalid device response")
            info = data.get("Chain2Info", {})
            device_id = info.get("Id") if isinstance(info, dict) else None
            if not isinstance(device_id, str) or not device_id.lower().startswith("c2g-"):
                raise ValueError("Not a Chain2Gate device")
            return info
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise CannotConnect(f"Cannot identify Chain2Gate at {self.host}") from err

    async def frames(self) -> AsyncIterator[dict[str, Any]]:
        """Yield JSON objects, with bounded connection and silent-connection waits."""
        async with asyncio.timeout(HTTP_TIMEOUT):
            ws = await self.session.ws_connect(f"http://{self.host}:81", max_msg_size=65536)
        self._ws = ws
        try:
            async with ws:
                await ws.send_str("!")
                # The caller receives a successful-open marker before any measurement.
                yield {}
                while True:
                    async with asyncio.timeout(FRAME_TIMEOUT):
                        message = await ws.receive()
                    if message.type in (aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY):
                        try:
                            data = json.loads(message.data)
                        except (ValueError, UnicodeDecodeError):
                            continue
                        if isinstance(data, dict):
                            yield data
                    elif message.type in (
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                        aiohttp.WSMsgType.CLOSING,
                    ):
                        raise CannotConnect("WebSocket disconnected")
        finally:
            self._ws = None

    async def close(self) -> None:
        """Close only our WebSocket, never HA's shared HTTP session."""
        if self._ws is not None:
            await self._ws.close()
