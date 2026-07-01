#!/usr/bin/env bash
# Кристаллизация EasyIR cloud-сессии через REST API AgentMemory.
set -euo pipefail

BASE_URL="${AGENTMEMORY_URL:-https://aimem.git.obs.group}"
TOKEN="${AGENTMEMORY_TOKEN:-iddqd}"
AUTH="Authorization: Bearer ${TOKEN}"
PROJECT="easyir"
SESSION_ID="cursor-easyir-zha-panel-ea9f-2026-07-01"
CWD="/workspace"

api() {
  local method="$1" path="$2"
  shift 2
  curl -sS -X "$method" \
    -H "$AUTH" \
    -H "Content-Type: application/json" \
    "${BASE_URL}${path}" \
    "$@"
}

echo "== health =="
api GET "/agentmemory/health" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status'), d.get('version'))"

echo "== session start =="
api POST "/agentmemory/session/start" \
  -d "{\"sessionId\":\"${SESSION_ID}\",\"project\":\"${PROJECT}\",\"cwd\":\"${CWD}\",\"title\":\"EasyIR ZHA panel cloud session crystallize\"}" \
  | tee /tmp/am-session-start.json | python3 -m json.tool

ACTION_IDS=()

create_and_complete() {
  local title="$1" desc="$2" priority="$3" tags="$4" result="$5"
  echo "== create action: ${title} =="
  local create_resp
  create_resp=$(api POST "/agentmemory/actions" \
    -d "$(python3 - <<PY
import json
print(json.dumps({
  "title": ${title@Q},
  "description": ${desc@Q},
  "priority": ${priority},
  "project": "${PROJECT}",
  "tags": ${tags@Q}.split(",") if False else $(python3 -c "import json; print(json.dumps('${tags}'.split(',')))")
}))
PY
)")
  echo "$create_resp" | python3 -m json.tool
  local aid
  aid=$(echo "$create_resp" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('action',{}).get('id') or d.get('id',''))")
  if [[ -z "$aid" ]]; then
    echo "FAILED to parse action id from: $create_resp" >&2
    return 1
  fi
  echo "== complete action ${aid} =="
  api POST "/agentmemory/actions/update" \
    -d "{\"actionId\":\"${aid}\",\"status\":\"done\",\"result\":$(python3 -c "import json; print(json.dumps('${result}'))")}" \
    | python3 -m json.tool
  ACTION_IDS+=("$aid")
}

create_and_complete \
  "EasyIR v4: subentries ir_hub/ir_remote" \
  "single_config_entry + integration_type hub + migration v3→v4. PR #55, rc1-rc3." \
  10 "architecture,subentries" \
  "Архитектура v4 реализована, 148 тестов OK"

create_and_complete \
  "Онбординг один шаг hub+name+room" \
  "Объединён user step: hub_pick, hub_name, area_id." \
  9 "config_flow,onboarding" \
  "Один экран онбординга в config_flow.py"

create_and_complete \
  "Фикс CONF_AREA_ID import rc2" \
  "NameError в hub_registry.py" \
  8 "bugfix" \
  "Импорт добавлен, rc2"

create_and_complete \
  "Фикс area_id async_update_device rc3" \
  "TypeError в devices.py get_or_create" \
  8 "bugfix" \
  "area через async_update_device, rc3"

create_and_complete \
  "MCP shim + session JSONL export" \
  "memory_crystallize недоступен в MCP; REST workaround" \
  6 "agentmemory" \
  "JSONL экспорт в docs/, REST crystallize"

IDS_JSON=$(python3 -c "import json; print(json.dumps($(printf '%s\n' "${ACTION_IDS[@]}" | python3 -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))")))" )

echo "== crystallize actionIds=${IDS_JSON} =="
CRYSTAL_RESP=$(api POST "/agentmemory/crystals/create" \
  -d "{\"actionIds\":${IDS_JSON},\"project\":\"${PROJECT}\",\"sessionId\":\"${SESSION_ID}\"}")
echo "$CRYSTAL_RESP" | python3 -m json.tool || echo "$CRYSTAL_RESP"

echo "== crystal list =="
api GET "/agentmemory/crystals?project=${PROJECT}&sessionId=${SESSION_ID}" | python3 -m json.tool

echo "== session end =="
api POST "/agentmemory/session/end" -d "{\"sessionId\":\"${SESSION_ID}\"}" | python3 -m json.tool

echo "DONE action_ids=${ACTION_IDS[*]}"
