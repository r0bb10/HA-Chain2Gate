"""Manual, Zeroconf and reconfiguration flows for Chain2Gate."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import CannotConnect, Chain2GateClient
from .const import (
    CONF_APARTMENT,
    CONF_DEVICE_ID,
    CONF_ENTITY_IDENTITY,
    CONF_HOSTNAME,
    CONF_MAC,
    DOMAIN,
)
from .mac import async_resolve_mac, entity_identity
from .protocol import normalize_mac, valid_host


def _schema(host: str = "", *, include_host: bool = True, mac: str = "") -> vol.Schema:
    fields: dict[Any, Any] = {}
    if include_host:
        fields[vol.Required(CONF_HOST, default=host)] = str
    fields[vol.Optional(CONF_MAC, default=mac)] = str
    fields[vol.Optional(CONF_APARTMENT, default="")] = str
    return vol.Schema(fields)


class Chain2GateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Identify by the gateway's stable Id, independent of IP or optional MAC."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, Any] = {}

    async def _identify(self, host: str) -> dict[str, Any]:
        client = Chain2GateClient(async_get_clientsession(self.hass), valid_host(host))
        return await client.identify()

    async def _async_check_existing(self, info: dict[str, Any], host: str, mac: str | None):
        """Enrich existing entries without changing their registered sensor identities."""
        existing = await self.async_set_unique_id(info["Id"].lower())
        updates = {CONF_HOST: host}
        if existing and mac and not existing.data.get(CONF_MAC):
            updates.update({CONF_MAC: mac, CONF_ENTITY_IDENTITY: entity_identity(existing.data)})
        self._abort_if_unique_id_configured(updates=updates)

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors = {}
        if user_input is not None:
            try:
                host = valid_host(user_input[CONF_HOST])
                mac = normalize_mac(user_input[CONF_MAC]) if user_input.get(CONF_MAC) else None
            except ValueError:
                errors["base"] = "invalid_input"
            else:
                try:
                    info = await self._identify(host)
                except CannotConnect:
                    errors["base"] = "cannot_connect"
                else:
                    mac = mac or await async_resolve_mac(self.hass, host, info)
                    await self._async_check_existing(info, host, mac)
                    return self._create(info, host, mac, user_input.get(CONF_APARTMENT, ""))
        return self.async_show_form(step_id="user", data_schema=_schema(), errors=errors)

    def _create(self, info: dict[str, Any], host: str, mac: str | None, apartment: str):
        data = {
            CONF_HOST: host,
            CONF_DEVICE_ID: info["Id"],
            CONF_HOSTNAME: info["Id"],
            "metadata": {"prog_id": info.get("ProgId")},
        }
        if mac:
            data[CONF_MAC] = mac
        data[CONF_ENTITY_IDENTITY] = entity_identity(data)
        return self.async_create_entry(
            title=info["Id"], data=data, options={CONF_APARTMENT: apartment.strip()}
        )

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo):
        hostname = discovery_info.hostname.rstrip(".").lower()
        if not hostname.startswith("c2g-"):
            return self.async_abort(reason="not_chain2gate")
        try:
            info = await self._identify(discovery_info.host)
        except (CannotConnect, ValueError):
            return self.async_abort(reason="cannot_connect")
        mac = await async_resolve_mac(
            self.hass, discovery_info.host, info, discovery_info.properties
        )
        await self._async_check_existing(info, discovery_info.host, mac)
        self._discovered = {"info": info, CONF_HOST: discovery_info.host, CONF_MAC: mac}
        self.context["title_placeholders"] = {"name": info["Id"]}
        return await self.async_step_discovery_confirm()

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo):
        """Use HA's DHCP discoveries when available, including full hardware addresses."""
        try:
            info = await self._identify(discovery_info.ip)
            mac = normalize_mac(discovery_info.macaddress)
        except (CannotConnect, ValueError):
            return self.async_abort(reason="cannot_connect")
        await self._async_check_existing(info, discovery_info.ip, mac)
        self._discovered = {"info": info, CONF_HOST: discovery_info.ip, CONF_MAC: mac}
        self.context["title_placeholders"] = {"name": info["Id"]}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(self, user_input: dict[str, Any] | None = None):
        errors = {}
        if user_input is not None:
            try:
                mac = (
                    normalize_mac(user_input[CONF_MAC])
                    if user_input.get(CONF_MAC)
                    else self._discovered.get(CONF_MAC)
                )
            except ValueError:
                errors["base"] = "invalid_input"
            else:
                return self._create(
                    self._discovered["info"],
                    self._discovered[CONF_HOST],
                    mac,
                    user_input.get(CONF_APARTMENT, ""),
                )
        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=_schema(include_host=False, mac=self._discovered.get(CONF_MAC) or ""),
            description_placeholders={"name": self._discovered["info"]["Id"]},
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None):
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            try:
                host = valid_host(user_input[CONF_HOST])
                info = await self._identify(host)
            except ValueError:
                errors["base"] = "invalid_input"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            else:
                if info["Id"].lower() != entry.data[CONF_DEVICE_ID].lower():
                    errors["base"] = "wrong_device"
                else:
                    return self.async_update_reload_and_abort(entry, data_updates={CONF_HOST: host})
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return Chain2GateOptionsFlow()


class Chain2GateOptionsFlow(config_entries.OptionsFlow):
    """Apartment labels are user configuration, not mutable device metadata."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(
                title="", data={CONF_APARTMENT: user_input[CONF_APARTMENT].strip()}
            )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_APARTMENT,
                        default=self.config_entry.options.get(CONF_APARTMENT, ""),
                    ): str
                }
            ),
        )
