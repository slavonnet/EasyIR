#!/usr/bin/env python3
"""Кристаллизация EasyIR cloud-сессии через REST API AgentMemory."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("AGENTMEMORY_URL", "https://aimem.git.obs.group").rstrip("/")
TOKEN = os.environ.get("AGENTMEMORY_TOKEN", "iddqd")
PROJECT = "easyir"
SESSION_ID = "cursor-easyir-zha-panel-ea9f-2026-07-01"
CWD = "/workspace"

ACTIONS = [
    {
        "title": "EasyIR v4: subentries ir_hub/ir_remote",
        "description": "single_config_entry + integration_type hub + migration v3→v4. PR #55, rc1-rc3.",
        "priority": 10,
        "tags": ["architecture", "subentries"],
        "result": "Архитектура v4 реализована, 148 тестов OK",
    },
    {
        "title": "Онбординг один шаг hub+name+room",
        "description": "Объединён user step: hub_pick, hub_name, area_id.",
        "priority": 9,
        "tags": ["config_flow", "onboarding"],
        "result": "Один экран онбординга в config_flow.py",
    },
    {
        "title": "Фикс CONF_AREA_ID import rc2",
        "description": "NameError в hub_registry.py",
        "priority": 8,
        "tags": ["bugfix"],
        "result": "Импорт добавлен, rc2",
    },
    {
        "title": "Фикс area_id async_update_device rc3",
        "description": "TypeError в devices.py get_or_create",
        "priority": 8,
        "tags": ["bugfix"],
        "result": "area через async_update_device, rc3",
    },
    {
        "title": "MCP shim + session JSONL export",
        "description": "memory_crystallize недоступен в MCP; REST workaround",
        "priority": 6,
        "tags": ["agentmemory"],
        "result": "JSONL экспорт в docs/, REST crystallize",
    },
]


def api(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode()
        print(f"HTTP {exc.code} {path}: {err_body}", file=sys.stderr)
        raise


def main() -> int:
    print("== health ==")
    health = api("GET", "/agentmemory/health")
    print(json.dumps({"status": health.get("status"), "version": health.get("version")}, ensure_ascii=False))

    print("== session start ==")
    start = api(
        "POST",
        "/agentmemory/session/start",
        {
            "sessionId": SESSION_ID,
            "project": PROJECT,
            "cwd": CWD,
            "title": "EasyIR ZHA panel cloud session crystallize",
        },
    )
    print(json.dumps(start, ensure_ascii=False, indent=2))

    action_ids: list[str] = []
    for spec in ACTIONS:
        print(f"== create: {spec['title']} ==")
        created = api(
            "POST",
            "/agentmemory/actions",
            {
                "title": spec["title"],
                "description": spec["description"],
                "priority": spec["priority"],
                "project": PROJECT,
                "tags": spec["tags"],
            },
        )
        action = created.get("action") or created
        aid = action.get("id")
        if not aid:
            print(json.dumps(created, ensure_ascii=False, indent=2))
            raise SystemExit(f"no action id in response for {spec['title']}")
        action_ids.append(aid)
        print(f"  id={aid}")

        print(f"== complete: {aid} ==")
        updated = api(
            "POST",
            "/agentmemory/actions/update",
            {"actionId": aid, "status": "done", "result": spec["result"]},
        )
        print(json.dumps(updated, ensure_ascii=False, indent=2))

    print("== crystallize ==")
    crystal = api(
        "POST",
        "/agentmemory/crystals/create",
        {"actionIds": action_ids, "project": PROJECT, "sessionId": SESSION_ID},
    )
    print(json.dumps(crystal, ensure_ascii=False, indent=2))

    print("== crystal list ==")
    crystals = api("GET", f"/agentmemory/crystals?project={PROJECT}&sessionId={SESSION_ID}")
    print(json.dumps(crystals, ensure_ascii=False, indent=2))

    print("== session end ==")
    end = api("POST", "/agentmemory/session/end", {"sessionId": SESSION_ID})
    print(json.dumps(end, ensure_ascii=False, indent=2))

    print(json.dumps({"success": True, "action_ids": action_ids, "session_id": SESSION_ID}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
