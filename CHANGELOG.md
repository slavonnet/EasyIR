# Changelog

All notable changes to EasyIR are documented here.

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
