# Chain2Gate for Home Assistant

Native **local-push** integration for MAC s.r.l. Chain2Gate gateways. Receives
meter readings directly over HTTP/WebSocket.

Requires **Home Assistant 2026.2 or newer**.

## Installation

### HACS custom repository

Add this repository to HACS as an **Integration**, download Chain2Gate and
restart Home Assistant.

### Manual installation

1. Copy `custom_components/chain2gate` into your Home Assistant configuration's
   `custom_components` directory.
2. Restart Home Assistant.
3. Open **Settings → Devices & services** and confirm a discovered gateway, or
   select **Add integration → Chain2Gate** and enter its hostname or IPv4 address.

The gateway must be reachable on TCP ports **80 and 81**. Zeroconf discovery
requires local multicast visibility. Manual configuration works when discovery
is unavailable or the gateway is on another subnet. IPv6 is not supported.

Communication uses local, unencrypted HTTP/WebSocket. Keep the gateway on a
trusted network and do not expose it to the Internet.

## Sensors

| Sensor key | Unit | Description |
| --- | --- | --- |
| `instant_power` | W | M1 instantaneous grid-import power |
| `quart_avg_power` | W | M1 quarter-average grid-import power |
| `quart_energy` | Wh | M1 completed quarter-hour grid-import energy |
| `total_energy` | Wh | M1 cumulative grid-import energy |
| `tariff` | — | Reported tariff code |
| `contract_power` | kW | Contract power, displayed with one decimal place |
| `ip` | — | Configured gateway address |
| `pod` | — | Reported POD identifier |

M2 detection adds four production sensors: `prod_instant_power`,
`prod_quart_avg_power`, `prod_quart_energy` and `prod_total_energy`.

**M1 grid export and M2 production are distinct measurements.** M1 export uses
separate `m1_prod_*` sensor keys, with grid-export display names. M2 import, if
reported, uses separate `m2_*` keys. These additional sensors are discovered
automatically and disabled by default; enable them in the device's entity settings.

Sensor keys and registered identities remain stable. An existing entity ID,
custom name or user visibility setting is not overwritten.

### Frames and source detection

- CF1–CF4 provide periodic import measurements.
- CF2/CF4/CF101/CF103 provide periodic export-direction measurements.
- CF21/CF22/CF51 provide import-power updates; CF41/CF51 provide export-direction
  power updates.
- CF20 provides contract/POD information.

An explicit `Meter` field determines the source role. When it is absent,
CF41/CF101/CF103 default to M2 and other supported frames default to M1.
CF4 alone does not identify M2. Empty frames and invalid fields do not erase
existing measurements. Once M2 has been observed, later M1 messages do not
remove production support.

See [the protocol reference](docs/README.md) for frame meanings, source
documentation and the limits of frame-based inference.

### Energy statistics

Cumulative energy sensors use `total_increasing` and are the recommended sources
for the Energy dashboard.

Quarter-energy sensors use `total` with an interval-based `last_reset`, derived
from `MeasurePosixTimestamp - 900`. They remain unknown without a valid interval
timestamp. Home Assistant uses the first recorded value as its initial zero
point; subsequent intervals add their reported energy. Missing intervals are not
reconstructed or backfilled.

Timestamp checks prevent duplicate/stale readings and stop older periodic power
snapshots from overwriting newer event readings. Values and interval boundaries
are saved together, with a short save delay and a flush on unload, so normal
restarts do not create artificial interval resets. This is not an exactly-once
transactional guarantee across abrupt power loss.

## Power-limit event

CF22 fires `chain2gate_power_limit_exceeded` with:

- `device_id`: gateway protocol identifier, not Home Assistant's device UUID;
- `config_entry_id`: the gateway's integration entry;
- `meter`: source role;
- `instant_power`, `available_power` and `switch_off_seconds`, when supplied.

Use an event-triggered automation to respond. Events are not replayed after a
restart. This is not a safety-critical load-shedding system.

## License

[MIT](LICENSE) © 2026 r0bb10.
