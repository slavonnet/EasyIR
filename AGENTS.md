# AGENTS.md

Operational rules for contributors and coding agents working on EasyIR.

## 1) Product vision (target architecture)

The current repository is an incomplete release. The target product is a full IR platform for Home Assistant:

- support multiple IR transports/hubs: Wi-Fi, ZigBee, USB, ESPHome;
- support multiple IR message encodings and conversion between formats;
- move from static command databases to protocol-aware generation and parsing;
- represent many virtual IR devices (AC, TV, etc.) behind one or many IR hubs;
- keep room-aware behavior for logging and state synchronization;
- provide first-class tools in a dedicated Home Assistant sidebar section (`EasyIR`).

If `README.md` and this file diverge, treat this file as roadmap and engineering policy for new work.
Current TS1201/ZHA logic in the release is a legacy adapter path, not a product-level architecture constraint.

## 2) Compatibility policy (hard requirement)

HACS upgrades must not break already configured devices.

Rules:

1. Existing config entries must continue to work after update, without re-adding hubs/devices.
2. Existing service contracts are stable API unless explicitly versioned:
   - `easyir.send_raw`
   - `easyir.send_profile_command`
3. Because config entries store `CONF_PROFILE_PATH`, bundled profile paths are compatibility contract in a major line:
   - do not rename/move/delete released profile files without migration,
   - if replacement is required, keep compatibility alias/stub at old path or migrate entries.
4. Profile schema evolution should be additive inside one major line.
5. If a breaking format change is intentional, introduce explicit schema/version field and compatibility layer (or migration) before release.
6. Any change touching profile resolution/path logic must include `async_migrate_entry` (when needed) and tests proving old entries still send commands.

## 3) Long-term functional scope

### 3.1 Universal IR core
- Canonical internal IR model (normalized frame representation).
- Codec registry for encode/decode/convert between supported binary formats.
- Protocol definitions with capability map (for example: ionizer supported or not).

### 3.2 Hub and transport support
- Automatic discovery and filtering by supported IR hub type/model.
- Suggest adding newly detected supported hubs not yet configured.
- Multi-hub operation with many virtual end devices.

### 3.3 Device model and automation
- Virtual device entities for AC/TV/etc. derived from protocol capabilities.
- Dynamic widgets/cards that adapt to feature availability.

### 3.4 Signal ingest and intelligence
- IR signal logging with room scoping.
- Decode incoming remote commands and sync HA widget/entity state.
- Auto-detection with remote (capture -> decode -> infer capabilities).
- Guided no-remote assistant (send candidates, user confirms reaction, infer best profile/protocol).
- If decoded signal cannot be mapped to known device in room, suggest adding device type.
- If room filter says a device is not visible there, do not trigger add/sync actions.

### 3.5 Home Assistant UX
- Sidebar section `EasyIR` with tools:
  - IR signal log,
  - format transcoder,
  - remote auto-detection,
  - guided pairing/selection helpers.

## 4) Repository map (current layout)

- `custom_components/easyir/`
  - `__init__.py` integration setup and service registration.
  - `config_flow.py` UI flow defaults and validation.
  - `climate.py` optimistic climate entity behavior.
  - `helpers.py` profile parsing, raw encoding, cache/rate-limit helpers.
  - `bundled_profiles.py` bundled profile resolution helpers.
  - `services.yaml`, `strings.json`, `translations/*.json` service and UI text.
- `custom_components/easyir/profiles/`
  - `registry.json`, `climate_index.json`, `demo_ac.json`
  - `climate/*.json` bundled command library (large data set).
- `tests/`
  - `test_helpers.py` unit tests for encoding/profile resolution/cache behavior.
- `examples/` and `blueprints/` usage and automation examples.

## 5) Parallel execution plan for multiple agents

This section below was originally drafted as a minimal execution example.
For active multi-agent planning and task orchestration, use [`docs/roadmap.yaml`](docs/roadmap.yaml)
as the primary source of truth (detailed TR, dependencies, pilot-first sequencing, task templates).
Template structure: [`docs/agents-roadmap-example.md`](docs/agents-roadmap-example.md).

Use separate branches and PRs per workstream. Keep each PR narrow and mergeable.

Recommended workstreams:

1. **Core IR Model + Codec Registry**
   - Define canonical IR frame model.
   - Add first codec abstraction interfaces and conversion pipeline.
2. **Protocol Capability Layer**
   - Protocol descriptors + capability schema (features matrix per protocol/device family).
3. **Hub Discovery and Onboarding**
   - Supported hub filtering and auto-suggest flow for newly found supported hubs.
4. **Room-aware Signal Log and Sync**
   - Logging storage model, room mapping, and scoped sync logic.
5. **Incoming Command Decode Pipeline**
   - Parse captured IR command, map to virtual device state updates.
6. **Auto-detection (with remote)**
   - Capture/decode/infer assistant flow.
7. **Guided Pairing (without remote)**
   - Interactive probing workflow based on user feedback.
8. **Dynamic UI / Sidebar Tools**
   - Sidebar section and tool pages (log, transcoder, assistants).
9. **Compatibility and Migration Guardrail**
   - Config entry/profile migrations, compatibility tests, upgrade regression suite.
10. **Legal/Contribution Governance**
   - Contributor rights statement and license policy documentation.

Each agent must:
- know this target vision before implementing;
- state assumptions if current code cannot yet support target behavior;
- deliver incremental, backward-compatible slices.

## 6) Git and PR hygiene (public history policy)

Public branches/PRs should contain final, reviewable results, not noisy trial-and-error history.

Rules:

1. Work locally until the solution is stable, then create focused commits.
2. Prefer one logical commit per PR (or a few clean commits if truly separate concerns).
3. Do not push WIP/debug commits to shared/public branch.
4. Keep PR description concise: final implementation + validation + compatibility impact.
5. Avoid unrelated refactors and file churn.

## 7) Change rules

1. Keep service schemas backward compatible unless task explicitly calls for a versioned break.
2. If behavior changes for users, update docs in `README.md` and examples when relevant.
3. Do not refactor unrelated modules in the same PR.
4. Prefer minimal, focused edits with clear rationale.
5. Treat `custom_components/easyir/profiles/climate/*.json` as data artifacts:
   - avoid incidental formatting churn,
   - only change them when task explicitly targets profile data.

## 8) Validation commands

Run from repo root:

```bash
python3 -m unittest discover -s tests -v
```

If only docs changed, mention tests were not required. If runtime code changed, run tests before finalizing.

## 9) Home Assistant integration specifics

- Keep optimistic climate state logic coherent with commands sent.
- Preserve existing fan-mode aliases and command resolution behavior unless tests are updated accordingly.
- Keep payload encoding/decoding adapters backward compatible for already supported hubs/transports.
- Be careful with config-flow defaults and avoid transport-specific assumptions in shared core logic.

## 10) Licensing and contribution policy (project requirement)

This section describes project policy expectations that must be reflected in repository legal docs.

1. Code reuse is allowed only with mandatory attribution to author and project name.
2. Forking with a new name is allowed only if original project had no changes for at least one year.
3. PR-based contribution policy: contributor grants the rights described in [`CONTRIBUTING.md`](CONTRIBUTING.md) for submitted code and warrants that submitted material does not include anything they cannot license to the project under those terms.

Repository legal and contribution text lives in [`LICENSE`](LICENSE), [`CONTRIBUTING.md`](CONTRIBUTING.md), and [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md); keep them consistent with this section when policy wording changes.

## 11) Definition of done

A change is ready when:

1. Scope is limited to requested task/workstream.
2. Tests pass for code changes (or rationale provided for docs-only changes).
3. User-facing behavior changes are documented.
4. Diff avoids unrelated noise, especially in bundled profile data files.
5. HACS update does not break already configured devices.

## 12) PR checklist

Include in PR description:

1. What changed.
2. Why it changed.
3. How it was validated.
4. Compatibility and migration impact.
5. Risks, limitations, and follow-ups.

## 13) Orchestrator and subagent execution policy

These rules are mandatory for both directly started agents and agents started by an orchestrator.

### 13.1 Agent run modes

1. **Directly started agent**
   - Creates/uses its own task branch.
   - Implements scoped task, validates, commits, pushes.
   - Creates/updates its own PR.
2. **Subagent started by orchestrator**
   - Must be explicitly informed that it runs under an orchestrator.
   - Works only in assigned task scope and assigned branch.
   - Implements, validates, commits, pushes.
   - Does **not** create PR unless orchestrator explicitly delegates this.

### 13.2 Orchestrator responsibilities

1. Orchestrator owns PR creation/update for subagent result branches.
2. PR title and description must be written in Russian.
3. Because several orchestrators can work in parallel, each orchestrator must choose a unique **TAG**.
4. Orchestrator TAG must be included in all branch names created by that orchestrator.
5. If subagent result indicates additional roadmap work is required (for example, feature done for one model but generic support still needed), orchestrator should open a separate roadmap-improvement PR with:
   - rationale for new/adjusted tasks,
   - roadmap updates,
   - related documentation updates so a new agent can execute directly from updated roadmap.
6. If a PR for a branch is already **merged**, orchestrator must **not** attempt to update that merged PR; any additional changes must go in a **new branch and new PR**.
7. Before any `update_pr` action, orchestrator must explicitly check PR state (OPEN/CLOSED/MERGED). Updates are allowed only for OPEN PRs; CLOSED or MERGED always require a new branch + new PR.

### 13.3 Roadmap status workflow

1. Before launching any subagent for a task, orchestrator must change that task status in the active roadmap file (created from `docs/agents-roadmap-example.md`) to `В Работе`.
2. Orchestrator must commit and push this `В Работе` status change to `dev` **without PR** so other orchestrators can see task lock state.
3. Launching any subagent is allowed only after this push to `dev` is successfully completed (no exceptions).
4. Task status change to `Завершена` is done by the subagent inside its own task branch and included in task PR.
5. Therefore, merging that PR to `dev` is the completion event for roadmap status.

### 13.4 Shared workspace safety in parallel runs

1. Subagents operate in shared workspace infrastructure, so branch isolation is mandatory.
2. Each subagent must make changes only in its own branch and within assigned scope.
3. Subagent must not modify files/areas owned by another in-progress parallel task.
4. If overlap/conflict is discovered, subagent must stop cross-scope edits and report to orchestrator.
5. Orchestrator-launched subagents **must use isolated workspace/worktree directories** (one filesystem workspace per subagent branch), not a shared working directory.
6. Running multiple subagents in the same physical workspace path is prohibited, even if branch names differ.
7. Orchestrator prompt must explicitly state the assigned workspace path for each subagent and require no writes outside that path.
8. Before any commit/push, subagent must verify `git branch --show-current` matches assigned branch and repository path matches assigned workspace.
9. If subagent detects unexpected files changed by another task in its workspace, it must stop and report conflict instead of trying to repair/revert others' changes.

## Cursor Cloud specific instructions

EasyIR is a Home Assistant **custom integration** (HACS), not a standalone app: it runs inside Home Assistant and its full IR-send path needs ZHA + a TS1201 Zigbee IR blaster. Default validation is the unit suite + exercising the IR core directly (below). For browser UX testing of the setup wizard there is a pre-built real-HA stack — see "Browser UX testing of the config-flow wizard" below.

- **Python deps are installed system-wide** by the startup update script (`pip install --break-system-packages "homeassistant==2025.1.4"`). There is no venv and no activation step — just use `python3` directly. (A venv is avoided on purpose: the base image lacks `python3.12-venv`, and adding apt installs to the reliability-critical update script is undesirable.)
- **HA version pin:** this base image ships Python 3.12, which caps `homeassistant` at `2025.1.4` (>= 2025.2 requires Python 3.13). `manifest.json` declares min HA `2025.7.0`, but the test suite is written to run on older HA via `tests/ha_subentry_stubs.py` (subentry API shim), so `2025.1.4` is the correct test target here — do not "fix" the version to match the manifest.
- **Tests:** run from repo root: `python3 -m unittest discover -s tests -v` (per section 8). `tests/__init__.py` imports `homeassistant`, so tests fail to even load without HA installed.
- **Lint:** no linter is configured in this repo. Use `python3 -m compileall custom_components/easyir` as a syntax check.
- **Exercising the IR core without HA:** modules under `custom_components/easyir/` (e.g. `helpers.resolve_profile_raw`, `encode_raw_to_tuya_base64`, `decode_ir_payload`) drive the real bundled profiles (`profiles/climate/7062.json` LG P12RK via the `lg28` engine, `profiles/demo_ac.json`). When importing these standalone, first call `tests.ha_subentry_stubs.install()` because `helpers.resolve_profile_raw` falls back to importing the full `custom_components.easyir` package, which needs the subentry shim on HA < 2025.7. Note: the final trailing IR gap is intentionally capped to uint16 (65535), so decode round-trips match on the frame body but not that last gap.

### Browser UX testing of the config-flow wizard (real Home Assistant)

A full HA browser stack for walking the setup wizard (hub onboarding + the `type → brand → model` "Add remote" subentry flow) is **pre-built in the VM snapshot** (it is intentionally NOT in the startup update script — too heavy/brittle). It lives outside the repo so it does not pollute `/workspace`:

- `~/ha-dev/` — a **Python 3.13** venv (deadsnakes; `~/.venv` only has 3.12) with `homeassistant` (native `ConfigSubentryFlow`, which the unit-test target 2025.1.4 lacks) plus ZHA deps (`zha`, `serialx`, `aiousbwatcher`, `pyserial`, `universal-silabs-flasher`, `ha-silabs-firmware-client`).
- `~/ha-config/` — HA config dir. `custom_components/easyir` is a **symlink to `/workspace/custom_components/easyir`** (repo edits apply on HA restart). Onboarding is already done (owner **`admin` / `admin1234`**).
- `~/ha-config/configuration.yaml` replaces `default_config:` with an explicit integration set, because `default_config` pulls `go2rtc`, which needs a Docker binary absent here and otherwise blocks the `config` UI.

Start / restart HA (tmux session `ha-server`), then open `http://localhost:8123` in the Desktop/Chrome pane:

```bash
tmux -f /exec-daemon/tmux.portal.conf send-keys -t ha-server:0.0 C-c            # stop if running
tmux -f /exec-daemon/tmux.portal.conf send-keys -t ha-server:0.0 \
  '~/ha-dev/bin/hass -c ~/ha-config --log-file ~/ha-config/home-assistant.log' C-m
```

- **No real Zigbee hardware:** a fake ZHA config entry + a TS1201 device (`zha` identifier `8c:65:a3:ff:fe:92:63:ce`, model `TS1201`) are seeded into `~/ha-config/.storage/{core.config_entries,core.device_registry}`. This is enough for the EasyIR config flow to pass its `async_entries("zha")` check and to **discover the TS1201 hub** in the wizard. The fake ZHA entry stays in **"Failed setup, will retry"** (no radio) — that is expected and harmless.
- **Re-seeding gotcha:** completing the hub wizard makes EasyIR rewrite that device (model → `IR Hub`, adds an `easyir` identifier). After deleting the EasyIR integration to re-test discovery, reset the device back to `model`/`model_id` `TS1201` with `identifiers` = `[["zha", "8c:65:a3:..."]]` only (edit `core.device_registry` with HA stopped), or discovery will no longer list it.

**Known bug surfaced by this flow (not an env issue):** the **"Add remote" subentry submit fails** with "Unknown error occurred". `config_flow.py` `_async_create_remote_subentry` (and `IrHubSubentryFlow.async_step_user`) call `self.async_set_unique_id(...)` / `self._abort_if_unique_id_configured()`, which **do not exist on `ConfigSubentryFlow`** — confirmed absent even in HA 2025.7.4 (the manifest's min), so this is a genuine product bug, not version drift. The correct API is to pass `unique_id=` to `async_create_entry` (already done alongside the bad calls). The runtime path is uncovered by unit tests (`tests/test_config_flow_steps.py` only checks the unique-id helper and that step methods exist). Hub creation and all three remote wizard steps (type → brand → model) render and navigate correctly; only the final remote-create call raises.
