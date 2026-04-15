# EasyIR MVP compatibility baseline

This document freezes **user-visible contracts** and **stored configuration shape** for the current MVP so later refactors (IR core, transports, migrations) can be checked against a stable baseline.

It does not replace `AGENTS.md` policy; it **records concrete artifacts** (service ids, config keys, bundled paths) that upgrades must preserve unless explicitly versioned.

## Stable service API (Home Assistant)

| Item | Value | Notes |
|------|--------|--------|
| Integration domain | `easyir` | `DOMAIN` in `const.py` |
| Service: raw send | `easyir.send_raw` | `SERVICE_SEND_RAW` = `send_raw` |
| Service: profile send | `easyir.send_profile_command` | `SERVICE_SEND_COMMAND` = `send_profile_command` |

### `easyir.send_raw`

- **Required in call data:** `raw_timings` (list of integers, mark/space alternation).
- **Optional:** `ieee`, `endpoint_id` (defaults from first config entry or TS1201 default when merged).
- **Behavior contract:** payload is encoded for TS1201 and sent via ZHA `issue_zigbee_cluster_command` (cluster `0xE004`, command `2`, params `{"code": "<base64>"}`). Any architectural change must keep this observable contract for existing setups unless a new versioned service is introduced.

### `easyir.send_profile_command`

- **Required in call data:** `action` (profile command key, e.g. `off`, `cool`).
- **Optional:** `ieee`, `profile_path`, `hvac_mode`, `fan_mode`, `temperature`, `endpoint_id` (defaults merged from first config entry).
- **Behavior contract:** `profile_path` must resolve to a JSON file with a `commands` tree; timings are resolved then encoded like `send_raw`. Non-`off` actions require mode parameters when the profile nests by mode/temperature.

Schema descriptions for UI live in `custom_components/easyir/services.yaml`; field names there align with the Voluptuous schemas in `__init__.py`.

## Config entry `data` (stored in Home Assistant)

Created by `config_flow.py` via `async_create_entry`. Expected keys:

| Key | Type | Meaning |
|-----|------|---------|
| `ieee` | `str` | Zigbee device IEEE for the IR hub |
| `profile_path` | `str` | Absolute path to profile JSON on disk (bundled file or user path) |
| `endpoint_id` | `int` | ZHA endpoint id (default `1`) |

Constants: `CONF_IEEE`, `CONF_PROFILE_PATH`, `CONF_ENDPOINT_ID` in `const.py`.

**Invariant:** existing entries must keep working after upgrade **without re-onboarding**; changing key names or meaning requires `async_migrate_entry` and tests.

## Bundled profile layout and compatibility-relevant paths

- Package root: `custom_components/easyir/profiles/`.
- **Registry:** `registry.json` — manual/demo entries with `id`, `title`, `file` (relative to `profiles/`).
- **Climate library:** `climate/*.json` + `climate_index.json` (labels for UI).
- **Contract:** within a major release line, **do not rename, move, or delete** shipped profile files that users may reference by resolved absolute path in `CONF_PROFILE_PATH` without a stub, alias, or migration. Adding new files is fine.

Resolution at setup time is implemented in `bundled_profiles.resolve_stored_profile_path` (registry id, `climate/<name>.json`, or custom absolute path).

## Regression fixtures

JSON under `tests/fixtures/legacy_config_entries/` models **legacy-shaped** `data` payloads. Files are named `*.entry.json` so they are distinct from tiny profile JSON used as custom-path targets. Paths may contain `${EASYIR_REPO_ROOT}`; tests expand this to the repository root so the same fixtures work locally and in CI.

Run: `python3 -m unittest discover -s tests -v`
