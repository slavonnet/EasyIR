# Protocol onboarding task template (parallel agents)

Use this document when launching **implementation agents** to add **one protocol and one model** after the pilot vertical slice is stable. It aligns with the active project roadmap file (created from `docs/agents-roadmap-example.md`), `AGENTS.md` (compatibility, PR hygiene), and orchestrator rules in **AGENTS.md §13**.

## Preconditions (orchestrator)

- Roadmap **pilot-first** gate is satisfied: pilot APIs and patterns exist; scale-out is intentional, not speculative.
- Dependencies for the slice are satisfied per the roadmap workstream graph (do not parallelize blocked work).
- One agent → **one branch** → **one narrow PR** (orchestrator opens the PR to `dev`).

## Required context (paste into every agent brief)

- Active project roadmap file (created from `docs/agents-roadmap-example.md`) is the **source of truth** for architecture, sequencing, and templates.
- `README.md` describes the current release state; it does not cap the target architecture.
- **Backward compatibility** for existing installs is mandatory (see **Compatibility constraints** below).
- **AGENTS.md §6–7, §11–12**: small, reviewable commits; no unrelated refactors; no churn in `custom_components/easyir/profiles/climate/*.json` unless the task is explicitly profile-data work.

## Task packet (copy for the implementation agent)

Fill every field before the agent starts. Remove bracketed hints when sending.

| Field | Content |
| --- | --- |
| **Branch** | `cursor/<short-purpose>-<orchestrator-tag>` (unique per orchestrator run) |
| **Workstream** | Typically `ws-pilot-protocol` pattern / protocol-scale slice (per roadmap) |
| **Objective** | Add exactly **one** IR protocol implementation and **one** model capability mapping, following the merged pilot pattern. |
| **In scope** | Protocol descriptor (or schema artifact) for the target protocol; parser + generator; capability matrix for **one** target model; tests for encode/decode and capability mapping; integration only where the pilot already defined hooks. |
| **Out of scope** | Additional protocols or models; broad UI/sidebar work; transport refactors; unrelated helpers or climate behavior changes. |
| **Concrete paths** | List expected dirs/files (e.g. `custom_components/easyir/protocols/`, `tests/`, …) — match repo layout after pilot merge. |
| **Compatibility constraints** | Preserve `easyir.send_raw` and `easyir.send_profile_command` contracts. Do not break bundled **profile path** resolution; any `CONF_PROFILE_PATH` / bundled path change requires `async_migrate_entry` and tests proving legacy entries still send commands. Profile schema changes must be **additive** within the major line unless an explicit versioned break is approved. |
| **Migrations** | `none` **or** describe `async_migrate_entry` / alias stub if paths or stored config change. |
| **Tests** | `python3 -m unittest discover -s tests -v` plus any new unit tests for the slice; add migration/legacy-send tests if config or path resolution is touched. |
| **Acceptance criteria** | Command generation parity for covered actions; decode round-trip or mapping tests pass; capability-driven behavior matches the single model’s feature set; no regressions for existing transports/protocols not in scope. |
| **Risks / assumptions** | e.g. hardware samples unavailable → fixture-only validation; model variant ambiguity → document assumption. |

## Compatibility constraints (checklist)

Derived from the active project roadmap file (`technical_requirements.compatibility`) and `AGENTS.md` §2.

- [ ] Existing config entries keep working without re-adding devices/hubs.
- [ ] Service contracts unchanged: `easyir.send_raw`, `easyir.send_profile_command`.
- [ ] No rename/remove of released bundled profile paths without stub, alias, or migration.
- [ ] Profile schema changes are additive unless an explicit versioned break and migration exist.
- [ ] Profile/path resolution changes include **tests** proving legacy entries still send commands.

## PR hygiene (checklist)

From `AGENTS.md` §6 and §12.

- [ ] One logical, reviewable commit (or a few commits only if concerns are truly separate).
- [ ] No WIP/debug/exploratory noise on the shared branch.
- [ ] PR description (orchestrator may write in Russian per §13) covers: **what** / **why** / **validation** / **compatibility impact** / **risks and follow-ups**.
- [ ] Diff avoids unrelated modules and **no incidental formatting** in large profile JSON trees.

## Definition of done

- Scope matches the task packet; out-of-scope items are not bundled in the same PR.
- Tests requested in the packet pass; docs-only follow-ups are not mixed with runtime changes in the same slice unless unavoidable and explained.
- Roadmap **orchestrator workflow**: subagent completes work on its branch; orchestrator opens/updates the PR to `dev`; backlog status **Завершена** for the task is carried in the subagent branch (merged to `dev` with the PR).

## Reference anchors in the roadmap YAML

- **`pilot_first_rule`**: one full vertical slice before parallel protocol/model additions.
- **`phase_3_parallel_scale`**: repeat the validated pilot template in small PRs.
- **`agent_task_templates.protocol_slice`**: minimal YAML checklist for the same slice type.
- **`parallel_execution_template`**: generic required context and `task_packet_fields` for any parallel agent.

When this template and the roadmap diverge, **update the roadmap** in a dedicated docs PR rather than silently contradicting it.
