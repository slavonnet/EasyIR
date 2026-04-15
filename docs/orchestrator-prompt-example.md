# Оркестратор EasyIR: пример промпта запуска

Ниже шаблон промпта для запуска оркестратора. Он учитывает правила из `AGENTS.md`
и предполагает, что в репозитории есть **активный roadmap-файл**, собранный по
шаблону `docs/agents-roadmap-example.md`.

## Пример промпта

```text
Ты оркестратор EasyIR.

Обязательные правила:
- Источник правды по задачам и зависимостям: активный roadmap-файл проекта (структура как в docs/agents-roadmap-example.md)
- Правила оркестрации и PR hygiene: AGENTS.md
- Обратная совместимость обязательна:
  - easyir.send_raw
  - easyir.send_profile_command
  - существующие config entries и profile paths
- Чистая история: только финальные логические коммиты, без WIP
- Узкие PR, без нерелевантных рефакторингов
- PR (title/body) только на русском
- Base branch для рабочих PR: dev

Режим работы:
1) Придумай уникальный TAG оркестратора (например: orch47b4).
2) Прочитай roadmap и выбери до 10 задач, у которых ВСЕ зависимости уже выполнены.
3) Перед запуском сабагентов:
   - для каждой выбранной задачи выставь status: "В Работе" в активном roadmap-файле;
   - закоммить и запушь это изменение в dev БЕЗ PR.
4) Запусти задачи параллельно через сабагентов:
   - каждый сабагент в своей ветке;
   - имя ветки содержит TAG оркестратора;
   - сабагенту явно сообщи, что он запущен оркестратором;
   - сабагент делает: implementation + validation + commit + push;
   - сабагент НЕ делает PR (PR делает оркестратор).
5) Сабагент в своем PR-ветке переводит статус своей задачи в roadmap на "Завершена".
6) Оркестратор создает/обновляет draft PR в dev по каждой ветке сабагента.
7) Если по итогам задачи выявлены новые work items (например, сделано для частного случая), оркестратор открывает ОТДЕЛЬНЫЙ PR с обновлением roadmap и docs.
```

## Пример: как выделить до 10 ready-задач из ROADMAP

Используйте правило: задача считается **ready**, если для нее в `workstreams` все
`depends_on` уже закрыты (или список пуст).

Пример "до 10" задач для оркестрации с учетом зависимостей:

1. `baseline-audit` — ready сразу (`depends_on: []`)
2. `ws-legal-governance` (`legal-docs-alignment`) — ready сразу (`depends_on: []`)
3. `ws-core-codec` (`core-codec-foundation`) — ready после завершения `baseline-audit`
4. `ws-transport-hub` (`transport-abstraction`) — ready после завершения `ws-core-codec`
5. `ws-compat-guardrails` (`compat-migrations-tests`) — ready после `ws-core-codec` и `ws-transport-hub`
6. `ws-pilot-protocol` (`pilot-ac-vertical-slice`) — ready после `ws-core-codec`
7. `ws-room-log-sync` (`room-aware-log-sync`) — ready после `ws-core-codec` и `ws-transport-hub`
8. `ws-sidebar-widgets` (`sidebar-signal-log`) — ready после `ws-pilot-protocol` и `ws-room-log-sync`
9. `ws-assistants` (`assistants-pilot`) — ready после `ws-pilot-protocol` и `ws-room-log-sync`
10. `protocol-scale-template` — можно выполнять как отдельную roadmap-задачу, когда зафиксирован пилотный шаблон и правила параллельного масштабирования

> Важно: перед запуском каждой волны сверяйте фактические `status` и `depends_on`
> в активном roadmap-файле, а также текущее состояние merged PR в `dev`.
