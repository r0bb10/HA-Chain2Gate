"""Native, local-push Chain2Gate integration."""

from __future__ import annotations

import logging

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CannotConnect, Chain2GateClient
from .const import CONF_DEVICE_ID, CONF_ENTITY_IDENTITY, CONF_MAC
from .coordinator import Chain2GateCoordinator
from .mac import async_resolve_mac, entity_identity

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.SENSOR]
type Chain2GateConfigEntry = ConfigEntry[Chain2GateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: Chain2GateConfigEntry) -> bool:
    """Identify before setup; HA retries temporary failures automatically."""
    client = Chain2GateClient(async_get_clientsession(hass), entry.data[CONF_HOST])
    try:
        info = await client.identify()
    except CannotConnect as err:
        raise ConfigEntryNotReady(str(err)) from err
    if info["Id"].lower() != entry.data[CONF_DEVICE_ID].lower():
        raise ConfigEntryError("This address now belongs to a different Chain2Gate device")
    data = {**entry.data, CONF_ENTITY_IDENTITY: entity_identity(entry.data)}
    if not data.get(CONF_MAC):
        if mac := await async_resolve_mac(hass, entry.data[CONF_HOST], info):
            data[CONF_MAC] = mac
    hass.config_entries.async_update_entry(entry, data=data)
    coordinator = Chain2GateCoordinator(hass, entry, client)
    await coordinator.async_load_measurements()
    entry.runtime_data = coordinator
    coordinator.process_frame({"Chain2Info": info})
    # Read cached snapshots once. This detects M2 immediately and avoids waiting
    # a quarter hour for initial values; normal operation remains WebSocket push.
    for kind in ("cf20", "cf1", "cf2", "cf3", "cf4", "cf101", "cf103"):
        try:
            coordinator.process_frame(await client.get_json(f"getcf.json?type={kind}"))
        except (aiohttp.ClientError, TimeoutError, ValueError, TypeError):
            _LOGGER.debug("Optional %s snapshot unavailable at %s", kind, client.host)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    coordinator.start()
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: Chain2GateConfigEntry) -> bool:
    """Release all subscriptions and the device connection."""
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.stop()
        return True
    return False


async def _async_entry_updated(hass: HomeAssistant, entry: Chain2GateConfigEntry) -> None:
    """Reload options only; config-flow helpers already reload host changes."""
    coordinator = entry.runtime_data
    if coordinator.applied_options != dict(entry.options):
        hass.config_entries.async_schedule_reload(entry.entry_id)
