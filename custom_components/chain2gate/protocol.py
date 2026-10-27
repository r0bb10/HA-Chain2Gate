"""Device protocol and stream routing, independent of Home Assistant.

A gateway can report both M1 and M2. Never merge their cumulative counters.
Consumption keys refer to M1; production keys refer to M2.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

CONSUMPTION = {
    "InstantPower": "instant_power",
    "QuartAveragePower": "quart_avg_power",
    "CurrQuartActEnergy": "quart_energy",
    "TotalActEnergy": "total_energy",
    "TariffCode": "tariff",
}
PRODUCTION = {
    "InstantProdPower": "prod_instant_power",
    "QuartAverageProdPower": "prod_quart_avg_power",
    "CurrQuartProdActEnergy": "prod_quart_energy",
    "TotalProdActEnergy": "prod_total_energy",
}


def normalize_mac(value: str) -> str:
    """Validate and normalize a full MAC; never guess it from a shortened hostname."""
    compact = re.sub(r"[:.\-]", "", value.strip()).lower()
    if not re.fullmatch(r"[0-9a-f]{12}", compact) or compact == "000000000000":
        raise ValueError("Invalid MAC address")
    return ":".join(compact[i : i + 2] for i in range(0, 12, 2))


def valid_host(value: str) -> str:
    """Accept a hostname or IPv4 address, not an arbitrary HTTP URL."""
    value = value.strip().rstrip(".")
    if not value or len(value) > 253 or not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise ValueError("Enter a hostname or IPv4 address without a port or scheme")
    return value


def number(value: Any) -> int | float | None:
    """Only accept finite, nonnegative numeric meter readings."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value < 0 or not math.isfinite(value):
        return None
    return value


@dataclass
class FrameUpdate:
    """A partial update; absent fields never overwrite existing measurements."""

    values: dict[str, int | float | str | None] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    power_limit: dict[str, Any] | None = None
    timestamps: dict[str, int] = field(default_factory=dict)
    intervals: dict[str, int] = field(default_factory=dict)


def decode_frame(data: Any) -> FrameUpdate:
    """Decode supported frames, preserving the identity of their meter stream."""
    update = FrameUpdate()
    if not isinstance(data, dict):
        raise ValueError("Frame must be a JSON object")
    info = data.get("Chain2Info")
    if isinstance(info, dict):
        if isinstance(info.get("ProgId"), str):
            update.metadata["prog_id"] = info["ProgId"]
        return update
    frame = data.get("Chain2Data")
    if not isinstance(frame, dict):
        return update
    kind = frame.get("Type")
    payload = frame.get("Payload", {})
    if not isinstance(payload, dict):
        raise ValueError("Payload must be an object")

    meter = frame.get("Meter") or ("M2" if kind in ("CF41", "CF101", "CF103") else "M1")
    if meter not in ("M1", "M2"):
        return update
    periodic = kind in ("CF1", "CF2", "CF3", "CF4", "CF101", "CF103")
    if payload and (periodic or kind in ("CF20", "CF21", "CF22", "CF41", "CF51")):
        if meter == "M2":
            update.metadata.update(meter_type="M2", has_m2=True)
        else:
            update.metadata["meter_type"] = "M1"

    timestamp = payload.get("MeasurePosixTimestamp" if periodic else "EventPosixTimestamp")
    # Message/reception times are not measurement times and cannot identify intervals.
    if (
        isinstance(timestamp, bool)
        or not isinstance(timestamp, int)
        or not 900 <= timestamp <= 253402300799
    ):
        timestamp = None

    def extract(mapping: dict[str, str], prefix: str = "") -> None:
        for source, key in mapping.items():
            if (value := number(payload.get(source))) is not None:
                full_key = prefix + key
                update.values[full_key] = value
                if timestamp is not None:
                    update.timestamps[full_key] = timestamp
                    if key.endswith("quart_energy"):
                        # CurrQuart is the completed interval ending at MeasurePosixTimestamp.
                        update.intervals[full_key] = timestamp - 900

    consumption_prefix = "" if meter == "M1" else "m2_"
    production_prefix = "" if meter == "M2" else "m1_"
    if kind in ("CF1", "CF2", "CF3", "CF4"):
        extract(CONSUMPTION, consumption_prefix)
    if kind in ("CF2", "CF4", "CF101", "CF103"):
        extract(PRODUCTION, production_prefix)
    if kind in ("CF21", "CF22", "CF51"):
        extract({"InstantPower": "instant_power"}, consumption_prefix)
    if kind == "CF41":
        extract({"ProdInstantPower": "prod_instant_power"}, production_prefix)
    if kind == "CF51":
        extract(
            {"ProdInstantPower": "prod_instant_power", "InstantProdPower": "prod_instant_power"},
            production_prefix,
        )
    if kind == "CF22":
        update.power_limit = {"meter": meter}
        for source, target in (
            ("InstantPower", "instant_power"),
            ("AvailablePower", "available_power"),
            ("SwitchOffCountdownSeconds", "switch_off_seconds"),
        ):
            if (value := number(payload.get(source))) is not None:
                update.power_limit[target] = value
    if kind == "CF20":
        if isinstance(pod := payload.get("POD"), str) and pod.strip():
            update.metadata["pod"] = pod.strip()
        if (power := number(payload.get("ContractPower"))) is not None:
            update.metadata["contract_power"] = power
    return update
