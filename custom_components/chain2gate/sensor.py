"""Native sensors with explicit meter-stream identities and numeric restoration."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import CONF_HOST, EntityCategory, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import Chain2GateConfigEntry
from .const import CONF_APARTMENT, CONF_DEVICE_ID, CONF_HOSTNAME, CONF_MAC, DOMAIN
from .coordinator import Chain2GateCoordinator


@dataclass(frozen=True, kw_only=True)
class Chain2GateSensorDescription(SensorEntityDescription):
    """Sensor description with its data source."""

    source: str = "measurement"


def _power(key: str, name: str, icon: str = "mdi:lightning-bolt") -> Chain2GateSensorDescription:
    return Chain2GateSensorDescription(
        key=key,
        name=name,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        icon=icon,
    )


def _energy(
    key: str, name: str, *, total: bool = False, icon: str | None = None
) -> Chain2GateSensorDescription:
    return Chain2GateSensorDescription(
        key=key,
        name=name,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING if total else SensorStateClass.TOTAL,
        icon=icon or ("mdi:counter" if total else "mdi:flash"),
    )


CONSUMPTION = (
    _power("instant_power", "Instant power"),
    _power("quart_avg_power", "Quarter average power", "mdi:chart-line"),
    _energy("quart_energy", "Quarter energy"),
    _energy("total_energy", "Total energy", total=True),
    Chain2GateSensorDescription(key="tariff", name="Tariff code", icon="mdi:cash-multiple"),
)
PRODUCTION = (
    _power("prod_instant_power", "Production instant power", "mdi:solar-power"),
    _power("prod_quart_avg_power", "Production quarter average power", "mdi:solar-panel"),
    _energy("prod_quart_energy", "Production quarter energy", icon="mdi:solar-power-variant"),
    _energy("prod_total_energy", "Total production energy", total=True),
)
DIAGNOSTICS = (
    Chain2GateSensorDescription(
        key="contract_power",
        name="Contract power",
        source="metadata",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        icon="mdi:file-document-edit",
    ),
    *(
        Chain2GateSensorDescription(
            key=key,
            name=name,
            source=source,
            icon=icon,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        for key, name, source, icon in (
            ("ip", "IP address", "host", "mdi:ip-network"),
            ("pod", "POD", "metadata", "mdi:identifier"),
            ("apartment", "Apartment", "apartment", "mdi:home-account"),
        )
    ),
)
SECONDARY = tuple(
    replace(
        description,
        key=prefix + description.key,
        name=(
            "M1 "
            + description.name.replace("Production", "Grid export").replace(
                "production", "grid export"
            )
            if prefix == "m1_"
            else f"{label} {description.name}"
        ),
        entity_registry_enabled_default=False,
    )
    for prefix, label, descriptions in (
        ("m1_", "M1", PRODUCTION),
        ("m2_", "M2", CONSUMPTION),
    )
    for description in descriptions
)


async def async_setup_entry(
    hass: HomeAssistant, entry: Chain2GateConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create base sensors, then discover additional stream sensors without reloading."""
    coordinator = entry.runtime_data
    added: set[str] = set()
    has_apartment = bool(entry.options.get(CONF_APARTMENT, "").strip())
    registry = er.async_get(hass)
    apartment_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{coordinator.identity}_apartment"
    )
    if apartment_id and (registered := registry.async_get(apartment_id)):
        updates = {}
        # Preserve user visibility choices when a label is cleared and restored.
        if not has_apartment:
            if registered.disabled_by is None:
                updates["disabled_by"] = er.RegistryEntryDisabler.INTEGRATION
            if registered.hidden_by is None:
                updates["hidden_by"] = er.RegistryEntryHider.INTEGRATION
        else:
            if registered.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
                updates["disabled_by"] = None
            if registered.hidden_by is er.RegistryEntryHider.INTEGRATION:
                updates["hidden_by"] = None
        if updates:
            registry.async_update_entity(apartment_id, **updates)
        if not has_apartment:
            # Remove restored placeholders for an entity intentionally not created.
            hass.states.async_remove(apartment_id)

    @callback
    def add_sensors() -> None:
        descriptions = list(CONSUMPTION + DIAGNOSTICS)
        if coordinator.metadata.get("has_m2"):
            descriptions.extend(PRODUCTION)
        # Keep previously discovered secondary sensors registered across restarts.
        known = set(coordinator.metadata.get("secondary_keys", []))
        known.update(key for key in coordinator.data if key.startswith(("m1_", "m2_")))
        descriptions.extend(d for d in SECONDARY if d.key in known)
        entities = []
        for description in descriptions:
            if description.key == "apartment" and not has_apartment:
                continue
            if description.key not in added:
                added.add(description.key)
                entities.append(Chain2GateSensor(coordinator, description))
        if entities:
            async_add_entities(entities)

    add_sensors()
    entry.async_on_unload(coordinator.async_add_listener(add_sensors))


class Chain2GateSensor(CoordinatorEntity[Chain2GateCoordinator], RestoreSensor):
    """One native push sensor; each cumulative counter has its own unique ID."""

    _attr_has_entity_name = True
    entity_description: Chain2GateSensorDescription

    def __init__(
        self, coordinator: Chain2GateCoordinator, description: Chain2GateSensorDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.identity}_{description.key}"
        self._restored_value: Any = None
        hostname = coordinator.entry.data[CONF_HOSTNAME].lower().replace("-", "_")
        # Suggest a stable ID; existing registry entries always take precedence.
        self.entity_id = f"sensor.{hostname}_{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        entry = self.coordinator.entry
        metadata = self.coordinator.metadata
        info = DeviceInfo(
            identifiers={(DOMAIN, entry.data[CONF_DEVICE_ID].lower())},
            name=entry.data[CONF_HOSTNAME],
            manufacturer="MAC s.r.l",
            model="Chain2Gate",
            sw_version=metadata.get("prog_id"),
            hw_version=metadata.get("meter_type"),
            serial_number=metadata.get("pod"),
            configuration_url=f"http://{entry.data[CONF_HOST]}",
        )
        if mac := entry.data.get(CONF_MAC):
            info["connections"] = {(dr.CONNECTION_NETWORK_MAC, mac)}
        return info

    @property
    def available(self) -> bool:
        return self.coordinator.connected and super().available

    @property
    def last_reset(self) -> datetime | None:
        """Use the interval's clock, never the packet reception or HA startup time."""
        timestamp = self.coordinator.intervals.get(self.entity_description.key)
        return dt_util.utc_from_timestamp(timestamp) if timestamp is not None else None

    @property
    def native_value(self):
        description = self.entity_description
        key = description.key
        entry = self.coordinator.entry
        if description.source == "metadata":
            value = self.coordinator.metadata.get(key)
            return value / 1000 if key == "contract_power" and value is not None else value
        if description.source == "host":
            return entry.data[CONF_HOST]
        if description.source == "apartment":
            return entry.options.get(CONF_APARTMENT, "")
        if key.endswith("quart_energy") and key not in self.coordinator.intervals:
            # Without an interval boundary TOTAL would compute misleading deltas.
            return None
        return self.coordinator.data.get(key, self._restored_value)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.entity_description.source == "measurement":
            if (last := await self.async_get_last_sensor_data()) is not None:
                self._restored_value = last.native_value
