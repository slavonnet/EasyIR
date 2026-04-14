# План переноса и продолжения (новый проект)

## Что уже подготовлено

В этой директории уже лежит отдельный HACS-проект:

- `hacs.json`
- `README.md`
- `custom_components/lg_tuya_ir/manifest.json`
- `custom_components/lg_tuya_ir/__init__.py`
- `custom_components/lg_tuya_ir/const.py`
- `custom_components/lg_tuya_ir/helpers.py`
- `custom_components/lg_tuya_ir/services.yaml`

Интеграция уже умеет:

- `lg_tuya_ir.send_raw` — отправка raw таймингов через TS1201 (ZHA)
- `lg_tuya_ir.send_profile_command` — чтение команды из profile JSON и отправка через TS1201

## Как переехать

1. Скопировать папку `ha-lg-tuya-ir-hacs` в отдельное место (или отдельный git-репозиторий).
2. Открыть эту папку в новом окне Cursor как корень проекта.
3. Инициализировать git в новой папке и запушить на GitHub.
4. Добавить репозиторий в HACS как Custom Repository (Integration).

## Что сделать в следующем шаге (в новом окне)

1. [частично] Заполнить в `manifest.json`:
   - [ ] `documentation`
   - [ ] `issue_tracker`
   - [ ] `codeowners`
   - [x] `config_flow`
2. [x] Добавить `config_flow.py` (UI-настройка устройства/IEEЕ и пути profile JSON).
3. [x] Добавить `translations/` и `strings.json`.
4. [x] Добавить rate-limit (задержка между send) на уровне интеграции.
5. [x] Добавить кеширование profile файла, чтобы не читать файл каждый вызов.
6. [x] Добавить unit-тесты на:
   - [x] encode raw -> tuya b64
   - [x] resolve command из profile дерева
   - [x] кеш profile (reuse + invalidation)
7. [x] Подготовить MVP release `v0.0.1`.

## Текущий статус (этап A)

- [x] `config_flow` + переводы добавлены
- [x] rate-limit между отправками добавлен
- [x] кеш profile файла добавлен
- [x] README обновлен под практический quick start
- [~] `manifest.json` подготовлен с плейсхолдерами под GitHub username (перед публикацией заменить)
- [ ] unit-тесты (этап B)
- [ ] релизный цикл с git tag/release notes (после публикации репозитория)
- [x] low-code слой: blueprint + examples/scripts.yaml
- [x] добавлена climate-сущность для управления как целью автоматизаций
- [x] примеры helpers/automations/dashboard для быстрого запуска виджета

## Цель на итог

Полноценная HACS-интеграция, которую можно устанавливать удаленно без ручных правок в Home Assistant.
