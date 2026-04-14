# EasyIR (HACS)

Author: Badalyan Vyacheslav

Custom Home Assistant integration to send IR profile commands via Tuya TS1201 over ZHA.

## Features

- Creates climate entity in Home Assistant (`climate.easyir_ac`).
- Converts IR `Raw` timings to TS1201-compatible base64 payload.
- Sends code using ZHA cluster command (`0xE004`, `IRSend`).
- Provides two services:
  - `easyir.send_raw`
  - `easyir.send_profile_command`
- Supports default values from UI setup (`ieee`, `profile_path`, `endpoint_id`).
- Includes built-in send rate-limit and profile file caching.

## Quick start (MVP 0.0.1)

1. Put this project into a GitHub repository.
2. Update placeholders in `custom_components/easyir/manifest.json`:
   - `documentation`
   - `issue_tracker`
   - `codeowners`
3. In Home Assistant HACS:
   - `Integrations` -> menu (3 dots) -> `Custom repositories`
   - add your GitHub repository URL
   - category: `Integration`
4. Install `EasyIR` (version `0.0.1`).
5. Restart Home Assistant.
6. Add integration from UI:
   - `Settings -> Devices & Services -> Add Integration -> EasyIR`
   - fill default `ieee`, `profile_path`, optional `endpoint_id`

## Service examples

### Send profile command (using defaults from config flow)

```yaml
service: easyir.send_profile_command
data:
  action: "off"
```

```yaml
service: easyir.send_profile_command
data:
  action: "cool"
  fan_mode: "auto"
  temperature: 24
```

### Send profile command (explicit values in call)

```yaml
service: easyir.send_profile_command
data:
  ieee: "8c:65:a3:ff:fe:92:63:ce"
  profile_path: "/config/ir/7062.json"
  action: "off"
```

### Send raw timings directly

```yaml
service: easyir.send_raw
data:
  ieee: "8c:65:a3:ff:fe:92:63:ce"
  raw_timings: [3198, -9806, 487, -1553, 579, -518]
```

## Working AC setup (widget + scenarios)

Goal: after connecting repo in HACS, get working AC device in a room and use it as automation target.

1. Create helpers (or use examples from `examples/helpers.yaml`):
   - `input_select.easyir_hvac_mode`
   - `input_select.easyir_fan_mode`
   - `input_number.easyir_target_temp`
2. Import/create scripts from `examples/scripts.yaml`.
3. Create automation from blueprint:
   - `blueprints/automation/easyir/ac_from_helpers.yaml`
   - this sends command when helper values change (widget-style control).
4. Use ready examples:
   - blueprint instances: `examples/automations.yaml`
   - dashboard card template: `examples/dashboard.yaml`
5. Assign EasyIR device to room in Home Assistant UI.
6. Example automation targeting climate entity:

```yaml
alias: EasyIR cool on arrival
triggers:
  - trigger: state
    entity_id: person.me
    to: "home"
actions:
  - action: climate.set_hvac_mode
    target:
      entity_id: climate.easyir_ac
    data:
      hvac_mode: cool
  - action: climate.set_temperature
    target:
      entity_id: climate.easyir_ac
    data:
      temperature: 24
mode: single
```

## Notes

- Profile file must be readable by Home Assistant (typically under `/config`).
- Large timing values are capped to `65535` (TS1201 uses uint16 durations).
- Integration enforces a small delay between sends to the same device.
- Climate entity is optimistic and stores last sent state.

## Tests

- Run unit tests from repository root:
  - `python -m unittest discover -s tests -v`
