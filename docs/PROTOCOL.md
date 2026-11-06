# Sharp KIN42 over ECHONET Lite: verified notes

Everything below was checked live on a **Sharp UA-KIN42E-H** (EU model) with a person
watching the unit's display and pressing buttons. Where something is a guess it says so.
If your model behaves differently, please open an issue with a diagnostics download.

## Transport

- ECHONET Lite over UDP **3610**, unicast to the purifier's IP. The controller must also
  *listen* on 3610, because replies are sent to that port. Only one process per host can do
  this, so this integration cannot run alongside another ECHONET Lite integration.
- Object: **air cleaner, EOJ `0x013501`**. Node profile: `0x0EF001`.
- `0x8C` (product code) on the air cleaner object reads `KIN42`.
- `0x83` (identification number) on the node profile holds the MAC as an EUI-64 in its
  last 8 bytes (`aa bb cc ff fe dd ee ff`), which is what the integration uses as the unique ID.
- **The unit often misses the first Get right after a SetC.** Retry (the integration does 3
  attempts, 2 s timeout each) and read back about 2 s after any write.
- **No push in practice.** The unit sends its INF announcements to multicast `224.0.23.0`.
  Many consumer routers don't forward that between Wi-Fi and Ethernet (on the test network
  even link-local mDNS passed but 224.0.23.0 did not). A unicast INF_REQ was not answered.
  So the integration polls (default 60 s). The INF handling code is there in case your
  network does pass the multicast.

## Standard properties

| EPC | Meaning | Notes |
|---|---|---|
| `0x80` | Power, `30` on / `31` off | Alone it fully powers the unit on or off; on power-on the unit resumes its last mode. |
| `0x84` | Instantaneous power, W (2 bytes) | |
| `0x85` | Cumulative energy, Wh (4 bytes) | |
| `0x88` | Fault, `41` yes / `42` no | |
| `0x8B` | Firmware/release (ASCII) | |
| `0xA0` | Airflow level | Snaps to presets: level 1 = Silent, 5 = Medium, 7/8 = High, `41` = Auto. Only 3 real manual speeds. Use F3 modes instead. |
| `0xC0` | Pollution lamp, `41` = yellow (dirty) / `42` = blue (clean) | |

## Sharp blob `0xF3` (27 bytes): state and commands

Reads all zeros while the unit is off.

**Mode** is in `F3[4]`. To set it, SetC `F3` = `01 01 00 00 <code>` followed by 22 zero bytes.

| Code | Mode |
|---|---|
| `10` | Auto |
| `20` | AI Auto |
| `11` | Night |
| `13` | Pollen |
| `14` | Silent |
| `15` | Medium |
| `16` | High |
| `40` | Plasmacluster (the `aiosharp` library calls this "Realize") |

**Humidify** state is in `F3[15]` (`FF` on / `00` off). To set it, SetC `F3` = `00 09` + zeros
with `F3[15]` = `FF` or `00`. It survives mode changes.

## Sharp blob `0xF1` (40 bytes): sensors

All of these read 0 while the unit is off.

| Bytes | Meaning | Status |
|---|---|---|
| `F1[3]` | Temperature, °C (signed) | Confirmed against the display |
| `F1[4]` | Humidity, % | Confirmed against the display |
| `F1[5]` | Air-quality level | Probably graded: 1 when clean, rose to 6 when the lamp went yellow. Exact scale unknown. Spikes to ~25–30 right after power-on. |
| `F1[21..24]` | Counter that rises while running | Exposed as "filter usage counter". Unit unknown. |
| `F1[27..28]` | PM2.5, µg/m³ (big-endian) | Confirmed against the display. **Bit 15 is set while the sensor warms up after power-on** (e.g. `0x8001`). Report unknown until it clears. |

The dust/smell offsets used by `aiosharp` gave wrong or constant values on this model.

## Sharp blob `0xF2` (40 bytes)

| Bytes | Meaning | Status |
|---|---|---|
| `F2[0] == 0x0A` | Water tank empty | Confirmed by pulling the tank |
| `F2[1] & 0x04` | **Not** "humidifying" | Disproved |

## Open questions

- The unit and scale of `F1[5]` and `F1[21..24]`.
- Whether other KIN-series models (KIN50, KIN60, KIN70…) use the same layout. The config
  flow currently refuses anything that doesn't report `KIN42`.
