# Chain 2 and Chain2Gate: protocol and frame reference

Research checked: **27 October 2026**.

This is a standalone explanation of the Italian Chain 2 metering protocol and
the Chain2Gate gateway's representation of it. It is not an integration manual,
a migration guide, or a replacement for the CEI specifications.

## 1. Sources and their authority

The reference numbers below distinguish three different kinds of evidence:

- **Distributor documentation:** E-Distribuzione's public technical material
  describes its service, protocol requirements and integration tests. [1][2]
- **Manufacturer documentation:** MAC's datasheet and public Chain2 Profiler
  describe the gateway architecture and expose frame/profile descriptions.
  The profiler is a useful manufacturer reference, **not the normative CEI
  specification**. [3][4]
- **Institutional semantic models:** ENEA explains the physical meaning of M1
  and M2 measurements and maps them to OBIS identifiers. These models are not
  binary frame specifications. [5][6]

Gateway JSON field names and capture-based checks are explicitly identified as
**observations**, rather than attributed to the standards. The full CEI texts
were not examined in this research; their titles and editions are reported from
the distributor/manufacturer documents that reference them.

## 2. Chain 2 is not the gateway's LAN protocol

```text
Electricity meter M1 and/or M2
           |
           | Chain 2: compact metering frames over the electrical wiring (PLC)
           v
User device / gateway, for example Chain2Gate
           |
           | Gateway-side network interface: JSON, WebSocket, MQTT, REST
           v
Local application or remote service
```

**Chain 2** is the communication channel between a compatible electricity meter
and a **Dispositivo Utente (DU)**. **Chain2Gate** is MAC's product family that
receives/handles those messages and exposes data through other interfaces.
The JSON object seen by a network client is therefore not the raw PLC frame.

E-Distribuzione identifies these technical specifications: [1][2, p. 4]

| Specification | Subject |
| --- | --- |
| CEI TS 13-82 | Communication with user devices, Part 1: use cases |
| CEI TS 13-83 | Part 2: data model and application layer |
| CEI TS 13-84 | Part 3-1: PLC profile in the 125–140 kHz C band |

The 2020 distributor test document references the 2017 editions. MAC's product
datasheet references the April 2020 editions under **Chain2full**, and identifies
DLMS/COSEM application/data-model standards IEC 62056-5-3, 62056-6-1 and
62056-6-2. Those edition differences matter when comparing frame lists. [2][3]

The test environment specifies a PLC channel centred at **132.5 kHz**. MAC's
datasheet describes a C-band modem with B-PSK modulation. [2, §3][3, p. 1]

MAC describes **JCD** as a JSON, message-oriented peer-to-peer architecture over
MQTT or WebSocket; its datasheet also lists REST connectivity. This does not
establish a universal HTTP endpoint, port, MQTT topic or JSON schema for every
Chain2Gate model/firmware. [3, pp. 1–2]

## 3. Meter roles and energy directions

| Term | Meaning |
| --- | --- |
| **M1** | Grid-exchange meter: records energy withdrawn from and fed into the grid |
| **M2** | Production meter: records energy at the generating installation's metering boundary |
| **Prelievo / Prel** | Withdrawal/import direction |
| **Immissione / Imm** | Injection/export direction, interpreted at the relevant meter |
| **Attiva / Att** | Active energy or power |
| **Reattiva / Reatt** | Reactive energy |
| **Induttiva / capacitiva** | Inductive/capacitive reactive-energy categories |
| **Monofase / trifase** | Single-phase / three-phase |
| **POD** | Identifier of a supply/metering point; not the gateway's network identity |
| **CF** | Compact frame (*trama compatta*) |

M1 and M2 are **roles**, not gateway models, phase counts or update rates.
A single DU can receive both sources; the distributor's test specification
explicitly describes this arrangement. [2, §3]

ENEA's M1 model supports CF1–CF4 and separates grid withdrawal from grid feed-in.
Its M2 model supports CF101/CF103 and describes produced energy. [5][6]

### Grid export is not production

An installation can use some generation locally before the remainder crosses
the grid-exchange meter. Storage, losses and the placement of meters also affect
the relationship. Consequently:

- M1 export and M2 production are **different measurements**.
- Their cumulative counters must never be interleaved into one series.
- M1 import is not necessarily the site's entire electrical consumption.
- A frame or field described as *immissione* needs its source-meter context.

For a simple site without storage, with aligned metering intervals and ignoring
losses, consumption can be estimated as production + grid import − grid export.
That is an energy-balance calculation, not a universal field supplied by Chain 2.

## 4. Frame families and profiles

The following catalogue paraphrases the manufacturer's public profiler. It
describes available frame families, **not a promise that every installation
transmits every frame**. Availability depends on service/profile, meter and
firmware. [4]

### Periodic measurement frames

| Frame | Period / phase type | Information family |
| --- | --- | --- |
| CF1 | 15 minutes, single-phase | Import active energy and power |
| CF2 | 15 minutes, single-phase | Import and export active energy and power |
| CF3 | 15 minutes, three-phase | Import active measurements plus reactive energy |
| CF4 | 15 minutes, three-phase | Import/export active measurements plus reactive energy |
| CF101 | 15 minutes, single-phase | Export-direction active energy and power |
| CF103 | 15 minutes, three-phase | Export-direction active measurements plus reactive energy |
| CF5 | Daily, single-phase | Import measurements |
| CF6 | Daily, single-phase | Import/export measurements |
| CF7 | Daily, three-phase | Import measurements including reactive energy |
| CF8 | Daily, three-phase | Import/export measurements including reactive energy |
| CF9 | Weekly, single-phase | RMS voltage extrema, associated times and voltage-band counters |
| CF19 | Weekly, three-phase | Voltage-quality information by phase |
| CF10 | Monthly, single-phase | Import energy by tariff band and closure information |
| CF11 | Monthly, single-phase | Import/export energy by tariff band and closure information |
| CF12 | Monthly, three-phase | Import energy, including reactive energy, and closure information |
| CF13 | Monthly, three-phase | Import/export energy, including reactive energy, and closure information |

Daily tables include tariff-band energy values, peak-power information and
additional fields such as prepaid credit/day type where applicable. Monthly
tables include a *freezing* closure code. **Weekly does not automatically mean
weekly energy totals:** CF9/CF19 describe voltage quality in the profiler.
Do not equate a daily/monthly register with a lifetime counter without checking
its register and closure definition. [4]

### Event, contract and security frames

| Frame | Event / purpose | Principal information shown by the profiler |
| --- | --- | --- |
| CF20 | Meter/contract information (*dati di targa*) | POD, customer/supplier information, contract/available power, meter serial, transformation constant and other contract fields |
| CF21 | Import-power step crossing | Event time/count, instantaneous import power and power step |
| CF22 | Available-power excess | Event time/count, instantaneous import power, available power and remaining disconnection time |
| CF23 | Single-phase service interruption | Event information and interruption duration |
| CF24 | Three-phase service interruption | Event information and interruption durations by phase |
| CF25 | Prepaid credit running low | Event information and prepaid credit |
| CF26 | Prepaid credit updated | Event information and prepaid credit |
| CF27 | Supplier change | Customer, POD, supplier and contract information |
| CF28 | New contract | Contract power and available power |
| CF29 | Power limitation | Reduction percentage/reason and contract/available power |
| CF30 | Tariff-plan change | Activation time and tariff-plan records |
| CF31 | PESSE group change | Event information and PESSE group |
| CF32 | Operating-key K2 change | Event information and new K2 material |
| CF33 | Invocation-counter reset | Message timestamp and event type |
| CF41 | M2 power-threshold crossing | Event time/count, instantaneous export-direction/production power and power step |
| CF50 | Initialisation using K1 | Operating key K2, system title and event information |
| CF51 | M1 import/export power-threshold crossing | Event time/count, instantaneous import/export power and power step |

These are event-triggered frames, not all periodic measurements. In particular,
**CF22 is a power-excess warning; CF25 concerns prepaid credit**, even though the
older distributor test procedure groups their reception counters. A threshold
event does not provide a guaranteed fixed-rate power sampling stream. [2][4]

The profiler groups these into P1–P7 single-/three-phase, M1/M2 and advanced
profiles, with P8 extras. P6 includes CF101, and P7 includes CF103. These are the
profiler's profile labels; consult the applicable service specification before
treating them as contractual capabilities. [4]

### Important historical difference: CF2 can come from M2

The **10 July 2020 monitoring test specification** lists CF1/CF21/CF22/CF25 from
M1 and **CF2/CF41 from M2**. It explicitly says that CF2, also provided for M1 in
the referenced data model, is sent by M2 in that monitoring arrangement, with
the source SSAP changed accordingly and the CF2 structure unchanged. [2, §4]

Do not interpret this older subset as the complete Chain2full catalogue, or
classify all CF2 messages as M1 solely from their frame number.

## 5. Understanding CF4 versus CF103

The profiler presents **both as quarter-hour frames**: [4]

- **CF4:** three-phase import/export measurements. It contains current/previous
  quarter active energy, instantaneous/average active power in both directions,
  inductive/capacitive quarter reactive energy, and cumulative energy registers.
- **CF103:** three-phase export-direction measurements. It contains the
  export-direction active quantities, associated quarter reactive energy and
  cumulative registers, without CF4's import-direction group.

Neither frame is inherently a faster update stream. The physical source remains
essential: **CF4 from M1 describes grid exchange; CF103 from M2 describes the
production-meter boundary**. ENEA's models support this distinction. [5][6]

In observed Chain2Gate JSON, both can contain `TotalProdActEnergy`. That spelling
does **not** make the M1 value total generation. For an M1 source it is grid
export; for an M2 source it is production. Preserve separate source identities.

The same principle applies to quarter energy, average power and instantaneous
power, not just cumulative counters. An explicit source identifier takes
precedence over an application guessing a meter role from the CF number.

## 6. Measurements, units and time

### Power and energy are different quantities

| Quantity | Meaning | Engineering units |
| --- | --- | --- |
| Instantaneous active power | Power at the measurement/event instant | W or kW |
| Quarter-average active power | Mean power over a 15-minute interval | W or kW |
| Quarter active energy | Energy accumulated during one interval | Wh or kWh |
| Cumulative active energy | Running register reading at the meter | Wh or kWh |
| Reactive energy | Inductive/capacitive energy category | varh or kvarh |
| RMS voltage | Effective voltage, including extrema in quality reports | V |

For an interval of exactly 900 seconds:

```text
average power [W] = interval energy [Wh] / 0.25 h = 4 × interval energy [Wh]
interval energy [kWh] = interval energy [Wh] / 1000
```

These equations are dimensional relationships, not a substitute for checking
the transmitted unit/scaler. Binary widths, signedness, scaling, transformation
constants and unavailable-value encodings must come from the applicable data
model. Do not assume every integer uses the same scale or that a maximum integer
is automatically invalid. The profiler's form labels are not sufficient to
implement a complete binary decoder. [3][4]

Three-phase aggregate fields are not individual phase readings. ENEA explicitly
describes the relevant three-phase energy/power quantities as totals across the
three phases. [5][6]

### Quarter totals are not lifetime counters

Current- and previous-quarter energy are separate interval amounts. A series
such as 50, 70, 40 Wh does not mean that the meter lost energy when it dropped
from 70 to 40. Do not compute successive differences of interval totals as
though they were cumulative readings, or repeatedly add a retransmitted total.

An interval amount and a cumulative register can be cross-checked **for the same
meter, direction and consecutive measurement boundaries**:

```text
cumulative(T) − cumulative(T − 900 s) ≈ energy of the interval ending at T
previous-quarter field at T ≈ current-quarter field at T − 900 s
```

Resets, rollovers, scaling/rounding, missing intervals and meter replacement need
separate handling; a counter difference over a longer gap is not the energy of
one quarter. Never add a previous-quarter recovery value without first checking
whether that interval was already received.

### Measurement, event, generation and reception times

The profiler distinguishes packet-generation time from measurement/event time.
These represent different instants. Transport delay or a cached gateway response
can make reception much later than measurement. [4]

Use the measurement timestamp to identify periodic intervals, and the event
timestamp for event ordering. Do not use the arrival time to invent a new
measurement interval. Preserve the original timestamp and apply a timezone only
when presenting it; local formatted strings can be ambiguous during daylight
saving changes. Do not assume every timestamp/date field shares one encoding.

## 7. Source identification, protection and repetitions

The distributor's monitoring tests check these layers: [2, §§4.1–4.2]

- **MAC/LLC:** valid link-layer framing, destination addressing and service.
- **Convergence:** absence of segmentation in the tested messages, DSAP `0x04`,
  and SSAP `0x0B` for M1 or `0x0C` for M2.
- **Application:** security-service identification and validation of its parameters.

Here, **MAC** means Medium Access Control. It must not be confused with the
manufacturer MAC s.r.l. or assumed to be the gateway's Ethernet/Wi-Fi MAC address.

The security test uses **AES-GCM-128**, a 128-bit operating key, and an
initialisation vector formed from the system title and frame/invocation counter.
The counter is carried in the application security header. Published test
parameters are test material, not credentials for an installed meter. [2, §4.2]

The repeat-management requirement is explicit: decode the first valid message
and discard subsequent replicas identified by an already-known valid frame
counter. A counter becomes valid only after successful message decoding. The
reception counters must increase once for an original plus its repeats, not
once for every copy. [2, §§5.1, 5.3]

That is the **PLC-level** duplicate rule. An application reading decoded JSON
may not receive the security counter, and can additionally encounter cached
snapshots/reconnect replays. It still needs source-aware interval/event ordering;
a timestamp-based application check is not a replacement for PLC authentication.

The distributor also tests daily reception counters, profiles containing 60
daily elements, and a most-significant-bit indication of a DU power interruption.
These are communication diagnostics, not energy registers. [2, §§5.2–5.4]

## 8. Relevant OBIS meanings

ENEA supplies the following semantic mappings. They identify quantities, not
JSON field names or byte offsets. The physical source is still required. [5][6]

| OBIS | Meaning in the cited models |
| --- | --- |
| `1-0:1.8.0.255` | Cumulative active energy withdrawn at M1 |
| `1-0:2.8.0.255` | Cumulative active energy fed into the grid at M1; produced energy at M2 |
| `1-0:99.1.0.255` | Withdrawal interval-energy information |
| `1-0:99.1.1.255` | Feed-in/production interval-energy information |
| `1-0:1.27.0.255` | Withdrawal active-power quantity in the M1 model |
| `1-0:2.27.0.255` | Feed-in active-power quantity at M1; produced active power at M2 |
| `1-0:99.1.2.255` | Withdrawal inductive reactive interval-energy information |
| `1-0:99.1.3.255` | Withdrawal capacitive reactive interval-energy information |
| `1-0:99.1.4.255` | Feed-in/production inductive reactive interval-energy information |
| `1-0:99.1.5.255` | Feed-in/production capacitive reactive interval-energy information |
| `1-0:3.8.0.255` | Cumulative withdrawal inductive reactive energy |
| `1-0:7.8.0.255` | Cumulative feed-in/production inductive reactive energy |

Do not infer that a period-power property in these semantic models is the
instantaneous-power field of every gateway message.

## 9. Chain2Gate JSON: observed representation, not a CEI schema

**Evidence boundary:** the manufacturer documents JSON/JCD and network
transports, but the exact field spellings below were observed in gateway data.
They are not presented as a publicly verified, complete manufacturer API contract.

Observed measurement messages use an envelope like this schematic example:

```json
{
  "Chain2Data": {
    "Id": "c2g-EXAMPLE",
    "Meter": "M1",
    "Type": "CF4",
    "Payload": {
      "MeasurePosixTimestamp": 1800000000,
      "CurrQuartActEnergy": 125,
      "QuartAveragePower": 500,
      "TotalActEnergy": 10000,
      "CurrQuartProdActEnergy": 25,
      "QuartAverageProdPower": 100,
      "TotalProdActEnergy": 2000
    }
  }
}
```

The example is synthetic and intentionally omits other fields. `Id` identifies
the gateway in the observed messages; it is not automatically a physical meter
serial number. `Meter` identifies the source role and `Type` the compact frame.

| Observed JSON field | Interpretation |
| --- | --- |
| `MessagePosixTimestamp` | Packet-generation timestamp |
| `MeasurePosixTimestamp` | Periodic measurement timestamp |
| `EventPosixTimestamp` | Event timestamp |
| `InstantPower` | Instantaneous import-direction active power |
| `QuartAveragePower` | Quarter-average import-direction active power |
| `CurrQuartActEnergy`, `PrevQuartActEnergy` | Current/previous completed import interval energy in the examined data |
| `TotalActEnergy` | Cumulative import-direction active energy |
| `InstantProdPower` | Instantaneous export-direction active power in observed periodic frames |
| `ProdInstantPower` | Export-direction/production instantaneous power spelling observed in CF41 |
| `QuartAverageProdPower` | Quarter-average export-direction active power |
| `CurrQuartProdActEnergy`, `PrevQuartProdActEnergy` | Current/previous export-direction interval energy |
| `TotalProdActEnergy` | Cumulative export-direction active energy; grid export for M1, production for M2 |
| `TariffCode` | Reported tariff-band code; do not assume a universal supplier schedule |
| `EventsCounter` | Event counter; do not equate it with the security invocation counter |
| `ContractPower`, `AvailablePower` | Contract/available power fields seen in decoded gateway data |
| `SwitchOffCountdownSeconds` | Remaining disconnection-time field observed in power-excess events |

Observed `Chain2Info` messages provide gateway information such as `Id` and
`ProgId`. They are not periodic energy measurements. A missing field, an empty
cached frame or an unrecognised source is not a zero reading.

### What the examined capture confirmed

This is empirical corroboration, **not an official-source claim**:

- 52 distinct CF4/M1 and 52 CF103/M2 measurement timestamps were examined.
- Each of the 52 reports per stream had quarter-average power equal to quarter
  active export/production energy in Wh multiplied by four.
- For 36 consecutive 900-second pairs per stream, the cumulative increment
  equalled the reported current-quarter energy, and the previous-quarter field
  matched the preceding report's current-quarter energy.
- One matching interval contained 369 Wh at M1's export boundary and 395 Wh at
  M2's production boundary: internally consistent but different measurements.

In those reports the current-quarter value describes the **completed interval
ending at the measurement timestamp**, not a lifetime counter or an arbitrary
partially elapsed quarter. This observation does not establish the timestamp
semantics of every other firmware or frame family.

## 10. Limits and practical interpretation rules

1. Keep meter identity/role, energy direction, quantity and time together.
2. Never combine counters just because they have the same JSON field name.
3. Distinguish interval amounts, average power, instantaneous power and registers.
4. Reject repeats without turning them into additional energy or new intervals.
5. Treat an absent report as missing information, not zero consumption/production.
6. Do not infer freshness from a live network connection or an HTTP success.
7. Check profile, edition, scaling, signedness, reset/rollover rules and metering
   boundary before implementing a decoder or interpreting an unusual value.

Public sources examined here do **not** establish a complete byte-level decoder,
all event-code enumerations, every sentinel value, complete tariff calendars,
or a universal Chain2Gate REST/WebSocket API. Some profiler field-size labels
are insufficient to independently reconstruct their advertised total frame
lengths; they should not be treated as authoritative binary layouts.

Service activation is separate from interpreting a message. E-Distribuzione's
FAQ describes eligible 2G low-voltage installations, the Asset Provider's role,
and possible meter/PLC reachability problems. Its eligibility statements apply
to its own distribution network, not automatically to every Italian distributor.
The current activation manual is linked from the FAQ. [1]

## References

**[1] E-Distribuzione — FAQ e Supporto Chain 2.** Official service, standards,
eligibility, activation and connectivity reference; consulted 27 October 2026.
<https://www.e-distribuzione.it/open-meter/chain-2/faq---esercizio-chain-2.html>

**[2] E-Distribuzione — Allegato 3: Modalità operative relative all'effettuazione
dei test di integrazione tra Dispositivo Utente e contatore 2G.** Issue I,
10 July 2020, 18 pages. Especially p. 4 (standards), §§3–4 (sources and protocol),
§4.2 (security), §5.1 (replicas), §§5.2–5.4 (reception diagnostics).
<https://www.e-distribuzione.it/content/dam/e-distribuzione/documenti/open-meter/chain2/Allegato_3_Specifiche_Test_Integrazione.pdf>

**[3] MAC s.r.l. — Chain2Gate Energy Meter datasheets.** Combined PDF; the 1P
sheet is dated 21 September 2023, release 1.8. Pages 1–2 describe PLC/COSEM,
referenced 2020 CEI editions, network interfaces and the JCD architecture.
Hardware capabilities are model-specific.
<https://www.mac-italia.com/wp-content/uploads/2024/02/Chain2Gate_EnergyMeter_eng.pdf>

**[4] MAC / JCD — CHAIN2 Profiler, Chain2 Certification Tool.** Public
manufacturer tool, displayed version 1.01; consulted 27 October 2026. Profile
reports and individual CF panels are the source for the extended catalogue.
No login or device interaction is required to read those static descriptions.
<https://chain2full.it/profiler.html>

**[5] ENEA Smart City Platform — M1 Electric User Device.** UrbanDataset model,
version 2.0, published 3 March 2025. Explains M1 withdrawal/feed-in semantics,
CF1–CF4 coverage and OBIS mappings.
<https://smartcityplatform.enea.it/UDWebLibrary/it/urbandataset?uri=smartcityplatform%3Aenea%3Asemantic%3Aontology%3Aurbandataset%23M1ElectricUserDevice>

**[6] ENEA Smart City Platform — M2 Electric User Device.** UrbanDataset model,
version 2.0, published 3 March 2025. Explains production semantics,
CF101/CF103 coverage and OBIS mappings.
<https://smartcityplatform.enea.it/UDWebLibrary/it/urbandataset?uri=smartcityplatform%3Aenea%3Asemantic%3Aontology%3Aurbandataset%23M2ElectricUserDevice>

**Additional official material referenced by [2], Appendix B:** a workbook of
monitoring-frame examples before/after encryption and authentication, with
setup data. Its contents were not independently parsed for this document; the
legacy URL below is recorded as printed in the PDF, not as a verified live link.
<https://www.e-distribuzione.it/content/dam/edistribuzione/documenti/open-meter/chain2/Contratto%20Esercizio%20Chain%202_Allegato%201_V20190205.xlsx>

For normative implementation details, obtain the applicable editions of
**CEI TS 13-82, 13-83 and 13-84** from CEI. Public summaries, the older monitoring
test procedure and the manufacturer's profiler are complementary references,
not interchangeable editions of the standard.
