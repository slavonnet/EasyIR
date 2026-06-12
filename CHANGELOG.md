# Changelog

All notable changes to EasyIR are documented here.

## [0.1.4] - 2026-06-12

### Fixed

- **Add remote** after hub confirm: continues in the same config flow (no lost checkbox).
- Blocking I/O in `bundled_profiles` during config flow (registry/climate scan) — load via executor + cache; fixes IR send stalls after onboarding.
- Discovery: unconfigured TS1201 opens **Add IR hub** flow, not «Add EasyIR» again.
- Device tree: IR hub is top-level; virtual remotes are children under the hub entry.

### Changed

- **Add entry** / repeat onboarding: main menu with two buttons (**Add IR hub** / **Add IR remote**) instead of dropdown manage step.
- Legacy `offer_remote_setup` chains remote flow after hub setup via deferred task (not during setup).

### Note

- Hub and remote remain separate config entries (HA may still ask name/area twice); unified wizard is on the roadmap (`docs/roadmap.yaml`).

## [0.1.3] - 2026-06-12

### Fixed

- Config flow: added missing `async_step_manage` handler (error «doesn't support step manage» when choosing **Add remote** on repeat onboarding).
- Options flow and post-hub remote chain: `await` on `config_entries.flow.async_init`.

## [0.1.2] - 2026-06-12

### Fixed

- Hub setup crash when adding a hub without remote (`MappingProxyType` has no `pop` on `entry.data`).
- Repeat EasyIR onboarding shows a manage step (add hub / add remote) instead of mixing hub and remote on one screen.
- Options menu on a hub entry: **Add IR hub** and **Add IR remote**.

### Changed

- ZHA endpoint is chosen automatically for TS1201 (default endpoint 1); removed from onboarding forms.
- Device registry tree: IR hub under ZHA blaster, virtual remotes under hub (`via_device`).
- Remote onboarding picks a hub when several hubs are configured.

### Documentation

- Added [`docs/roadmap.yaml`](docs/roadmap.yaml): приоритеты после v0.1.2 (миграция на HA `infrared` stack, мульти-транспорт, каталог хабов/пультов, визард, upstream PR).

## [0.1.1] - 2026-06-12

### Fixed

- Config flow hub picker: replace empty `async_show_menu` items with a dropdown listing discovered TS1201 hubs (labels visible).
- Sync `translations/ru.json` and `translations/en.json` with hub-centric steps (removed stale `%optional_supported` text).

## [0.1.0] - 2026-06-12

### Added

- **Hub-centric model**: IR hub (TS1201/ZHA) as primary config entry; virtual remotes attach separately.
- **Hub discovery**: unconfigured TS1201 devices suggested when EasyIR is installed.
- **Remote buttons** (`button` platform): power off, LG feature commands (ionizer, energy saving, auto clean, …).
- **Button command kinds**: grouped HVAC state frame vs separate feature command (LG universal).
- **On-demand IR**:
  - `easyir.start_learn`, `easyir.read_learned_ir`, `easyir.stop_learn`
  - `easyir.capture_inbound_ir` (temporary ZHA listener, no always-on loop)
- **Remote events**: `easyir_remote_button_pressed`, `easyir_remote_button_command` with `state_change_only`.
- Signal Log API: `POST /api/easyir/signal_log/read_learned`.

### Changed

- Config entry **v3** (hub + remote split; v1/v2 entries migrate to hub + imported remote).
- `learn_once` / `learn_code` start learn mode only (no attribute polling loop).
- Climate and buttons send IR through all hubs linked to a remote (`hub_ids`).
- Config flow: hub first, then optional remote profile.

### Requirements

- Home Assistant **2024.6.0+**
- **ZHA** configured before adding EasyIR

### Testing notes

1. Add EasyIR → pick discovered TS1201 hub (or manual ZHA device).
2. Add remote with profile (e.g. **LG P12RK / 7062**).
3. Use `climate.*` for mode/temp/fan; use `button.*` for off and extras (ionizer, …).
4. Learn: `easyir.start_learn` → press remote → `easyir.read_learned_ir`.
