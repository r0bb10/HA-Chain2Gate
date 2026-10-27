"""Push coordination, metadata persistence and connection lifecycle."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CannotConnect, Chain2GateClient
from .const import CONF_DEVICE_ID, DOMAIN, EVENT_POWER_LIMIT, RECONNECT_SECONDS
from .mac import entity_identity
from .protocol import decode_frame

_LOGGER = logging.getLogger(__name__)


class Chain2GateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Publish partial push updates; no scheduled polling."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: Chain2GateClient) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry)
        self.entry = entry
        self.client = client
        self.metadata = dict(entry.data.get("metadata", {}))
        if self.metadata.get("has_m2"):
            self.metadata["meter_type"] = "M2"
        self.applied_options = dict(entry.options)
        self.data = {}
        self.connected = False
        self._task: asyncio.Task | None = None
        self.timestamps: dict[str, int] = {}
        self.intervals: dict[str, int] = {}
        self._store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.measurements")

    async def async_load_measurements(self) -> None:
        """Load values and their clocks together before processing cached HTTP frames."""
        if saved := await self._store.async_load():
            self.data = saved["values"]
            self.timestamps = saved["timestamps"]
            self.intervals = saved["intervals"]

    def _stored_measurements(self) -> dict[str, Any]:
        return {
            "values": dict(self.data),
            "timestamps": dict(self.timestamps),
            "intervals": dict(self.intervals),
        }

    @property
    def identity(self) -> str:
        """Learning a MAC later must never change registered sensor identities."""
        return entity_identity(self.entry.data)

    def start(self) -> None:
        """Track the listener through the config entry, not a fire-and-forget task."""
        self._task = self.entry.async_create_background_task(
            self.hass, self._listen(), f"{DOMAIN}-{self.identity}"
        )

    async def stop(self) -> None:
        """Cancel and await the listener before removing entities."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self.client.close()
        await self._store.async_save(self._stored_measurements())
        self.connected = False

    def process_frame(self, data: dict[str, Any]) -> None:
        """Apply one frame and persist only nonsensitive, changed device metadata."""
        for key in ("Chain2Data", "Chain2Info"):
            content = data.get(key)
            if isinstance(content, dict) and isinstance(content.get("Id"), str):
                if content["Id"].lower() != self.entry.data[CONF_DEVICE_ID].lower():
                    raise CannotConnect("Gateway identity changed at this address")
        update = decode_frame(data)
        for key in list(update.values):
            previous = self.timestamps.get(key)
            timestamp = update.timestamps.get(key)
            if previous is not None and (timestamp is None or timestamp <= previous):
                del update.values[key]
                update.intervals.pop(key, None)
        self.timestamps.update({k: v for k, v in update.timestamps.items() if k in update.values})
        self.intervals.update(update.intervals)
        if self.metadata.get("has_m2") or self.metadata.get("meter_type") == "M2":
            if "meter_type" in update.metadata:
                update.metadata["meter_type"] = "M2"
        self.data.update(update.values)
        if update.values:
            self._store.async_delay_save(self._stored_measurements, 1)
        secondary = sorted(
            set(self.metadata.get("secondary_keys", []))
            | {key for key in update.values if key.startswith(("m1_", "m2_"))}
        )
        if secondary:
            update.metadata["secondary_keys"] = secondary
        changed = any(self.metadata.get(k) != v for k, v in update.metadata.items())
        if changed:
            self.metadata.update(update.metadata)
            self.hass.config_entries.async_update_entry(
                self.entry, data={**self.entry.data, "metadata": dict(self.metadata)}
            )
            self._update_device_metadata()
        if update.power_limit is not None and update.values:
            self.hass.bus.async_fire(
                EVENT_POWER_LIMIT,
                {
                    **update.power_limit,
                    "device_id": self.entry.data[CONF_DEVICE_ID],
                    "config_entry_id": self.entry.entry_id,
                },
            )
        if update.values or changed:
            self.async_set_updated_data(dict(self.data))

    def _update_device_metadata(self) -> None:
        """Refresh the device registry once per metadata change, not once per sensor."""
        registry = dr.async_get(self.hass)
        identifier = (DOMAIN, self.entry.data[CONF_DEVICE_ID].lower())
        if lookup := getattr(registry, "async_get_device_by_identifier", None):
            device = lookup(identifier, self.entry.entry_id)
        else:
            # Compatibility with HA 2026.2–2026.7, before scoped lookups existed.
            device = registry.async_get_device(identifiers={identifier})
        if device:
            changes = {}
            if self.metadata.get("prog_id") and self.metadata["prog_id"] != device.sw_version:
                changes["sw_version"] = self.metadata["prog_id"]
            if self.metadata.get("pod") and self.metadata["pod"] != device.serial_number:
                changes["serial_number"] = self.metadata["pod"]
            if self.metadata.get("meter_type") and self.metadata["meter_type"] != device.hw_version:
                changes["hw_version"] = self.metadata["meter_type"]
            if changes:
                registry.async_update_device(device.id, **changes)

    async def _listen(self) -> None:
        while True:
            try:
                async for data in self.client.frames():
                    if not self.connected:
                        self.connected = True
                        self.async_set_updated_data(dict(self.data))
                        _LOGGER.debug("Connected to %s", self.client.host)
                    try:
                        self.process_frame(data)
                    except (ValueError, TypeError, KeyError):
                        _LOGGER.debug("Ignoring malformed frame from %s", self.client.host)
                raise CannotConnect("WebSocket stream ended")
            except (CannotConnect, aiohttp.ClientError, TimeoutError, OSError) as err:
                self.connected = False
                self.async_set_update_error(UpdateFailed(str(err)))
                await asyncio.sleep(RECONNECT_SECONDS)
