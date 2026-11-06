# Sharp Air Purifier (ECHONET Lite, local) for Home Assistant

Local control of a Sharp humidifying air purifier over **ECHONET Lite**, with no cloud
and no Sharp account. The protocol details were worked out and checked against a real unit.
They're written up in [docs/PROTOCOL.md](docs/PROTOCOL.md), in case they're useful outside
Home Assistant too.

> **Tested on one model only: Sharp UA-KIN42E-H** (product code `KIN42`), Home Assistant 2026.10.
> Other KIN-series models may well work but are refused by the config flow until someone
> confirms them. See [Other models](#other-models).

## What you get

| Entity | What it does |
|---|---|
| Fan | On/off, 3 speeds (Silent / Medium / High) and presets: Auto, AI Auto, Night, Pollen, Plasmacluster, Silent, Medium, High |
| Switch | Humidify |
| Sensors | Temperature, humidity, PM2.5, air-quality level, power (W), energy (Wh), filter usage counter |
| Binary sensors | Air pollution (the blue/yellow lamp), water tank empty, fault |

Sensors show *unknown* while the unit is off (it reports zeros then), and PM2.5 shows
*unknown* while the sensor warms up after power-on.

## Requirements

- The purifier connected to your Wi-Fi (set it up once with Sharp's app).
- A **fixed IP** for the purifier (DHCP reservation in your router).
- Home Assistant must be able to **receive UDP on port 3610**. With Docker, use
  `network_mode: host`. If the host runs a firewall, allow it, e.g. for UFW:
  ```sh
  sudo ufw allow proto udp from <purifier-ip> to any port 3610
  ```
- No other ECHONET Lite integration on the same Home Assistant (only one can bind port 3610).

## Installation

### HACS (custom repository)

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/KrystianJonca/ha-sharp-echonet`, type *Integration*.
2. Install **Sharp Air Purifier (ECHONET Lite)** and restart Home Assistant.
3. *Settings → Devices & services → Add integration → Sharp Air Purifier* and enter the purifier's IP.

### Manual

Copy `custom_components/sharp_echonet` into your `config/custom_components/` and restart.

## Updates are polled

The purifier can push changes, but only via multicast (`224.0.23.0`), which many home
routers drop. So the integration **polls** (default every 60 s, adjustable 10–300 s in the
integration options). Changes made from Home Assistant are read back about 2 s after
the command, so the UI updates quickly. Button presses on the unit itself show up at the
next poll.

## Other models

If you have a different Sharp purifier with Wi-Fi, I'd love to hear whether it works:

1. Temporarily change `SUPPORTED_MODEL` in `custom_components/sharp_echonet/const.py` to
   your model's product code (the config flow error tells you what the unit reports).
2. Add the integration, try the controls, and download diagnostics
   (*device page → ⋮ → Download diagnostics*). It contains the raw property bytes with the
   IP and MAC redacted.
3. Open an issue with the diagnostics and what worked or didn't.

## Development

The protocol and decoding code (`protocol.py`, `device.py`) has no Home Assistant imports,
and its tests use only the standard library:

```sh
python -m unittest discover -s tests -v
```

## Credits and license

Thanks to the authors of the `aiosharp` library for prior work, and to the ECHONET Consortium for its public
specification. This project is not affiliated with or endorsed by Sharp.

MIT. See [LICENSE](LICENSE).
