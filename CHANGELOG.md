# Changelog

All notable changes to EasyIR are documented here.

## [0.2.5] - 2026-06-12

### Fixed

- Hub/remote re-attach stability:
  - removed false-positive unique-id blocking in subentry add flows that could prevent re-adding a deleted hub/remote in the same HA session,
  - added cleanup of stale EasyIR device links in device registry after subentry deletion.
- EasyIR page tree/UX:
  - tree rendering is kept strictly two-level (`Hub -> Remote`) without an artificial empty second level for hubs that have no remotes yet,
  - when all supported hubs are already added, Add Hub now shows explicit message:
    "Нет устройств, которые можно добавить: все поддерживаемые хабы уже добавлены."
- Remote wizard UX:
  - brand and device steps now include local search fields while preserving strict filtering chain (`type -> brand -> device`).
- Hub discovery behavior:
  - discovery switched from one-time scan to event-driven monitoring (new/update in device registry),
  - EasyIR now re-requests scan after entry/subentry updates so new TS1201 devices are suggested without reinstall/restart.

## [0.2.4] - 2026-06-12

### Fixed

- EasyIR sidebar wizard: `POST /api/easyir/ui/remotes` now accepts optional `brand` field from step 2 state and no longer fails remote creation due to strict payload validation.

## [0.2.3] - 2026-06-12

### Added

- New **EasyIR sidebar page** (`/easyir`) with:
  - explicit labeled actions **Добавить хаб** / **Добавить пульт**,
  - two-level tree rendering **Hub -> Remote**,
  - remote onboarding wizard in 3 steps with card **grids**:
    1) type grid,
    2) brand grid,
    3) device grid (multi-column, scrollable).
- New backend UI API endpoints for EasyIR panel:
  - hub discovery + creation,
  - area list loading,
  - remote catalog by type/brand,
  - remote creation with duplicate-safe unique id generation.

### Changed

- Extracted remote profile catalog grouping logic into shared module `remote_catalog.py` and reused it in config flow + UI API.
- Sidebar panel registration now includes both:
  - `EasyIR` main management page,
  - `EasyIR Signal Log`.

## [0.2.2] - 2026-06-12

### Fixed

- Remote wizard step 1 now uses device-type choices (climate/TV/other) instead of the previous advanced-selector wording.
- Remote creation on step 3 no longer silently aborts when the same profile is chosen repeatedly for one hub; duplicate profiles now get a deterministic unique suffix and are created correctly.
- Brand/model catalogs are now type-aware (climate vs TV vs non-climate profile set), with explicit abort message when selected type has no available profiles.

## [0.2.1] - 2026-06-12

### Changed

- Stable release on top of merged PR #56 and #57 content.
- Keeps onboarding wizard fixes, learn UX updates, and expanded LG remote capabilities.

## [0.2.1-beta2] - 2026-06-12

### Changed

- Merged open PRs into `dev` and published consolidated beta release from `dev` head.
- Included environment setup notes update in `AGENTS.md` from the second open PR.

## [0.2.1-beta1] - 2026-06-12

### Fixed

- Add remote flow no longer crashes with `Handler IrRemoteSubentryFlow doesn't support step hub_remote`.
- Add hub (subentry) now aborts with explicit message when all supported discovered hubs are already added.
- Device registry tree sync is refreshed after entry/subentry updates, keeping hub -> remote hierarchy stable.

### Changed

- Remote onboarding wizard is now explicit and step-based:
  - step 1/3: remote type,
  - step 2/3: brand,
  - step 3/3: device/profile.
- Signal Log panel learn UX: added **GetLearned** button and split feedback into "learn started" vs "code read".
- LG bundled profile `7062` expanded with additional feature flags (`jet`, `swing`, `wall_swing`, `light`, `power_down`, `clear_timers`).
- Power button label on the virtual remote now reflects assumed state (`Power on` / `Power off`) instead of static `Power off`.

## [0.1.5] - 2026-06-12

### Fixed

- **First-time integration setup** again adds **only the IR hub** (hub picker), not the hub/remote menu.
- **Add entry** on the EasyIR card (when entries already exist) shows **Add IR hub / Add IR remote**.
- Hub picker form routed to `async_step_pick_hub` (fixes broken menu/hub steps after v0.1.4).

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
