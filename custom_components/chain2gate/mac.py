"""Best-effort MAC discovery, never a prerequisite for connecting to a gateway."""

from __future__ import annotations

from ipaddress import IPv4Address
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONF_DEVICE_ID, CONF_ENTITY_IDENTITY, CONF_MAC
from .protocol import normalize_mac


def entity_identity(data: Any) -> str:
    """Freeze the existing sensor identity before enriching its network metadata."""
    return data.get(CONF_ENTITY_IDENTITY) or (
        data[CONF_MAC].replace(":", "").lower()
        if data.get(CONF_MAC)
        else data[CONF_DEVICE_ID].lower()
    )


def mac_from_properties(properties: dict[str, Any]) -> str | None:
    """Use only explicitly named full MAC fields, never a shortened device ID."""
    for key, value in properties.items():
        if key.lower().replace("_", "") not in ("mac", "macaddress"):
            continue
        if isinstance(value, str):
            try:
                return normalize_mac(value)
            except ValueError:
                continue
    return None


def parse_neighbor_mac(text: str, ip: str) -> str | None:
    """Read a complete IPv4 neighbor entry for this exact IP, not the router's MAC."""
    for line in text.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 6 or fields[0] != ip:
            continue
        try:
            if not int(fields[2], 16) & 0x2:
                continue
            mac = normalize_mac(fields[3])
            if int(mac[:2], 16) & 1:
                continue
            return mac
        except ValueError:
            continue
    return None


def _read_neighbor_mac(ip: str) -> str | None:
    """No raw sockets, scans, shell commands, privileges or active ARP requests."""
    try:
        return parse_neighbor_mac(Path("/proc/net/arp").read_text(), ip)
    except OSError:
        return None


async def async_resolve_mac(
    hass: HomeAssistant, host: str, info: dict[str, Any], properties: dict[str, Any] | None = None
) -> str | None:
    """Prefer device/mDNS data, then HA's DHCP cache, then an optional Linux cache."""
    if mac := mac_from_properties(info) or mac_from_properties(properties or {}):
        return mac
    try:
        ip = str(IPv4Address(info.get("Ip") or host))
    except ValueError:
        return None
    # Don't load or start DHCP packet capture just to obtain a MAC. The public
    # cache helper is available on newer HA versions when DHCP is already loaded.
    if "dhcp" in hass.config.components:
        from homeassistant.components import dhcp  # noqa: PLC0415

        if get_discoveries := getattr(dhcp, "async_discovered_service_info", None):
            for discovered in get_discoveries(hass):
                if discovered.ip == ip:
                    try:
                        return normalize_mac(discovered.macaddress)
                    except ValueError:
                        continue
    # The HTTP identity request normally populated this cache on the same LAN.
    # If the device is routed, or /proc is unavailable, setup still proceeds.
    return await hass.async_add_executor_job(_read_neighbor_mac, ip)
