# EasyIR (HACS)

Author: Badalyan Vyacheslav

**  THIS IS in DEV STATE. Warch for Releases **

Custom Home Assistant integration for IR command delivery in Home Assistant with
backward-compatible services and an expanding protocol/transport core.

**License and contributing:** see [`LICENSE`](LICENSE) and [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Features

- Creates climate entity in Home Assistant (`climate.easyir_ac`).
- Converts IR `Raw` timings to TS1201-compatible base64 payload.
- Sends code using ZHA cluster command (`0xE004`, `IRSend`).
- Provides two services:
  - `easyir.send_raw`
  - `easyir.send_profile_command`
- Ships **built-in IR profiles** in the integration package; after install you pick a profile from a list (no file hunt for the default demo).
- Supports defaults from UI: ZHA device → resolved `ieee`, resolved `profile_path`, `endpoint_id`.
- Includes built-in send rate-limit and profile file caching.

## Статус проекта

Текущая ветка — **недоделанный релиз**, а не MVP:

- базовый рабочий сценарий для Zigbee TS1201/ZHA реализован;
- добавлены универсальные IR-преобразования и пилотные protocol-aware механизмы;
- часть целевых возможностей (полный мульти-транспорт, расширенные UI-тулы, масштабирование по протоколам) еще в развитии.

## Quick start (текущий релиз)

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
   - pick your **ZHA IR device** (IEEE is filled automatically)
   - pick an **IR profile** from the list (built-in codes ship with EasyIR — start with **Demo AC** to verify wiring)
   - optional: **Custom path** only if you chose «Custom path» in the profile list
   - optional `endpoint_id` (often `1`)

## Built-in profiles (works out of the box)

IR command tables ship **inside the integration**:

| Path | Role |
|------|------|
| `custom_components/easyir/profiles/registry.json` | Small list of extras (e.g. **Demo AC**). |
| `custom_components/easyir/profiles/climate/*.json` | **356** bundled climate code files (numeric `NNNN.json`). |
| `custom_components/easyir/profiles/climate_index.json` | Human titles for the setup dropdown (manufacturer / model). |

**Normal user path:** install EasyIR → add integration → pick **Demo AC** (sanity check) or search the long list for your code set (e.g. **LG — P12RK** = file `7062` → value `climate/7062.json`) → no manual `/config/...` path.

**Bundled climate library (bootstrap):** the `climate/*.json` set is a compatibility layer: same general layout (`commands`, etc.) as common community climate dumps (see e.g. [this tree](https://github.com/smartHomeHub/SmartIR/tree/master/codes/climate) for reference). Long term EasyIR is meant to rely more on protocol-driven generation; refreshing this bundle is a maintainer-side offline step, not part of the runtime integration.

**Advanced:** if your codes only exist under `/config/...`, choose **Custom path** and paste the full path.

Format reference: [examples/profile.example.json](examples/profile.example.json).

### LG universal bit engine (bundled P12RK / `7062`)

The bundled LG P12RK profile (`climate/7062.json`) sets **`easyir_protocol`: `lg_universal_v1`** and **`easyir_encoding`: `lg28`**. For those profiles, `easyir.send_profile_command` builds the 28-bit LG AC state frame first (same packing as the pilot encoder, cross-checked with Arduino-IRremote [`ac_LG.h`](https://raw.githubusercontent.com/Arduino-IRremote/Arduino-IRremote/refs/heads/master/src/ac_LG.h) / [`ac_LG.hpp`](https://raw.githubusercontent.com/Arduino-IRremote/Arduino-IRremote/refs/heads/master/src/ac_LG.hpp)), then expands it to nominal microsecond mark/space timings (header ~8.9 ms / ~4.15 ms as noted in `ac_LG.hpp`). The large `commands.cool` / `commands.dry` matrix remains in the file as a **compatibility fallback** if `easyir_encoding` is not `lg28`. Optional **`easyir_feature_flags`** on the profile lists decode contract keys (`mode_temp_fan`, `power_off`) and **gates** which LG command-word extras are allowed on the send path (for example `ionizer`, `energy_saving`, `auto_clean`); strict inbound decode can require profile support before applying HVAC deltas. Other LG extras from `ac_LG.h` (swing, jet, timers, etc.) follow the same pattern but are not enabled on the bundled pilot profile until listed there.

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

## Документы для агентной разработки

- [`AGENTS.md`](AGENTS.md) — актуальные правила разработки, совместимости и оркестрации.
- [`docs/agents-roadmap-example.md`](docs/agents-roadmap-example.md) — пример структуры нового roadmap-файла, если нужно собрать план с нуля.

## Tests

- Run unit tests from repository root:
  - `python3 -m unittest discover -s tests -v`
