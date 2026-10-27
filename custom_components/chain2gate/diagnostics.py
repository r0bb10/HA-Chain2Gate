"""Redacted integration diagnostics, without meter IDs, IPs or raw device frames."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from . import Chain2GateConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: Chain2GateConfigEntry
) -> dict:
    coordinator = entry.runtime_data
    return {
        "connected": coordinator.connected,
        "firmware": coordinator.metadata.get("prog_id"),
        "has_m2": bool(coordinator.metadata.get("has_m2")),
        "meter_type": coordinator.metadata.get("meter_type"),
        "measurement_keys": sorted(coordinator.data),
        "secondary_keys": coordinator.metadata.get("secondary_keys", []),
        "mac_configured": bool(entry.data.get("mac")),
    }
