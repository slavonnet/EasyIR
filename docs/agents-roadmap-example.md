# Пример структуры roadmap для агентной разработки EasyIR

Этот документ — шаблон, как с нуля собрать новый roadmap-файл для оркестраторов
и сабагентов. Он заменяет старый служебный файл roadmap и описывает удобную,
повторяемую структуру.

## 1) Зачем нужен этот шаблон

- Держать единый источник правды для зависимостей и статусов задач.
- Явно фиксировать требования совместимости.
- Упростить параллельный запуск сабагентов без конфликтов.
- Обеспечить стабильные и узкие PR-пакеты.

## 2) Рекомендуемый путь и формат

- Рекомендуемый путь: `docs/roadmap.yaml` (или другой один явный файл).
- Формат: YAML.
- Кодировка: UTF-8.

## 3) Рекомендуемые верхнеуровневые секции

```yaml
name: EasyIR roadmap
version: 1
last_updated: 2026-04-15
status: active

overview: >
  Кратко: цель релизной итерации и границы текущей фазы.

principles:
  - README описывает текущий релиз, roadmap задает целевую архитектуру.
  - Обратная совместимость обязательна.
  - Только чистые логические коммиты и узкие PR.

technical_requirements:
  compatibility:
    hard_requirements:
      - Существующие config entries не ломаются после обновления.
      - Контракты сервисов easyir.send_raw / easyir.send_profile_command стабильны.
      - Пути профилей не ломаются без migration/alias.
  ir_core: {}
  transports_and_hubs: {}
  incoming_pipeline_and_sync: {}
  assistants: {}
  ha_sidebar_and_tools: {}

workstreams:
  - id: ws-core-codec
    title: Canonical IR core and codec registry
    depends_on: []
    can_run_parallel: false
    scope: []
    pr_guidelines: []

initial_backlog:
  - id: core-codec-foundation
    content: Реализовать canonical frame + codec registry.
    status: Запланирована
    workstream: ws-core-codec

agent_task_templates:
  protocol_slice: {}
  transport_slice: {}
  assistant_slice: {}
```

## 4) Минимальные обязательные поля задачи

Для каждого элемента в `initial_backlog`:

- `id` — стабильный машинный идентификатор;
- `content` — краткое и проверяемое описание результата;
- `status` — одно из:
  - `Запланирована`
  - `В Работе`
  - `Завершена`
  - `Блокирована`
- `workstream` — ссылка на `workstreams[].id`;
- `depends_on` (опционально) — список `id` задач, если нужна task-level зависимость;
- `acceptance_criteria` (рекомендуется) — 2-5 проверяемых пунктов.

## 5) Правила зависимостей

- `workstreams[].depends_on` — архитектурный уровень.
- `initial_backlog[].depends_on` — конкретная задача.
- Задача считается **ready**, только если:
  - все зависимости закрыты (`Завершена`);
  - нет конфликтов по области изменений (scope overlap).

## 6) Правила статусов для оркестратора

1. Перед запуском сабагента оркестратор ставит задачу в `В Работе`.
2. Это изменение коммитится и пушится в `dev` без PR (lock-сигнал другим оркестраторам).
3. Сабагент переводит задачу в `Завершена` в своей PR-ветке.
4. Merge PR в `dev` является событием завершения.

## 7) Рекомендуемая структура packet-шаблонов

В `agent_task_templates` и/или `agent_prompt_packets` фиксируйте:

- `objective`
- `in_scope`
- `out_of_scope`
- `concrete_files_to_touch`
- `compatibility_constraints`
- `migrations_needed`
- `tests_to_add_or_run`
- `acceptance_criteria`
- `known_risks_and_assumptions`

## 8) Контроль качества roadmap-файла

Перед каждой волной оркестрации:

- проверить, что у всех `depends_on` существуют валидные `id`;
- убедиться, что только одна команда владеет задачей со статусом `В Работе`;
- проверить, что статус не расходится с фактически merged PR;
- удалить устаревшие packet-ветки и примеры, которые уже неактуальны.

## 9) Что не хранить в roadmap

- длинные протоколы обсуждений;
- временные отладочные заметки;
- дублирующие PR-описания;
- несвязанные продуктовые идеи без привязки к workstream/backlog.

## 10) Практический старт "с нуля"

1. Создать `docs/roadmap.yaml` по этому шаблону.
2. Добавить 5-15 задач ближайшей релизной итерации.
3. Для каждой задачи определить owner-область файлов.
4. Зафиксировать зависимости и acceptance criteria.
5. Запустить первую волну только по ready-задачам.
