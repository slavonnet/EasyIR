# AGENTS.md

Operational rules for contributors and coding agents working on EasyIR.

## 1) Product vision (target architecture)

The current repository is an MVP. The target product is a full IR platform for Home Assistant:

- support multiple IR transports/hubs: Wi-Fi, ZigBee, USB, ESPHome;
- support multiple IR message encodings and conversion between formats;
- move from static command databases to protocol-aware generation and parsing;
- represent many virtual IR devices (AC, TV, etc.) behind one or many IR hubs;
- keep room-aware behavior for logging and state synchronization;
- provide first-class tools in a dedicated Home Assistant sidebar section (`EasyIR`).

If `README.md` and this file diverge, treat this file as roadmap and engineering policy for new work.
Current TS1201/ZHA logic in the MVP is a legacy adapter path, not a product-level architecture constraint.

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

## 4) Repository map (current MVP layout)

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

This section below was originally drafted as a minimal MVP-oriented execution example.
For active multi-agent planning and task orchestration, use `docs/roadmap.multi-agent.yaml` as
the primary source of truth (detailed TR, dependencies, pilot-first sequencing, task templates).

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
- state assumptions if MVP code cannot yet support target behavior;
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
python -m unittest discover -s tests -v
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

1. Before launching any subagent for a task, orchestrator must change that task status in `docs/roadmap.multi-agent.yaml` to `В Работе`.
2. Orchestrator must commit and push this `В Работе` status change to `dev` **without PR** so other orchestrators can see task lock state.
3. Launching any subagent is allowed only after this push to `dev` is successfully completed (no exceptions).
4. Task status change to `Завершена` is done by the subagent inside its own task branch and included in task PR.
5. Therefore, merging that PR to `dev` is the completion event for roadmap status.

### 13.4 Shared workspace safety in parallel runs

1. Subagents operate in shared workspace infrastructure, so branch isolation is mandatory.
2. Each subagent must make changes only in its own branch and within assigned scope.
3. Subagent must not modify files/areas owned by another in-progress parallel task.
4. If overlap/conflict is discovered, subagent must stop cross-scope edits and report to orchestrator.
