<div align="center">

# 🏪 CXH Playerok

**Управляйте магазином на Playerok прямо из Telegram — без браузера, без лишних вкладок, 24/7.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Telegram — канал](https://img.shields.io/badge/Telegram-канал-26A5E4?logo=telegram)](https://t.me/coxerhub_playerok)
[![Telegram — чат](https://img.shields.io/badge/Telegram-чат-26A5E4?logo=telegram)](https://t.me/coxerhub_ch)
[![Version](https://img.shields.io/badge/версия-2.0.0-brightgreen)](lib/consts.py)

</div>

---

## Зачем это нужно

Продавцы на Playerok теряют сделки из-за медленных ответов. Сидеть за компьютером часами, обновлять страницу вручную, не пропустить ни одно сообщение покупателя — это физически невозможно без инструментов.

**CXH Playerok** переносит весь процесс работы с магазином в Telegram: уведомления о новых чатах и сделках, ответы покупателям в один клик, полная автоматизация рутины. Работает в фоне пока вы занимаетесь чем угодно другим.

```
Покупатель написал → уведомление в Telegram за секунды → ответили из чата → сделка закрыта.
Всё это без браузера и без компьютера.
```

---

## Для кого

- Продавцы с большим каталогом, которым нужно поднимать лоты регулярно и не забывать об этом
- Те, кто продаёт цифровые товары и хочет выдавать ключи/файлы автоматически при оплате
- Магазины с потоком сделок, где каждая минута задержки с ответом — это риск потери покупателя
- Разработчики, которые хотят строить собственную автоматизацию поверх Playerok API

---

## Возможности

### Уведомления и общение

- Мгновенные уведомления о **новых сообщениях, сделках, отзывах**, жалобах и системных событиях — всё в один Telegram-чат
- **Ответ покупателю** прямо из уведомления — текстом или фото, без перехода в браузер
- **Шаблоны ответов** с переменными (`{{buyer}}`, `{{seller}}` и другие) — готовые тексты для типовых ситуаций
- Просмотр истории переписки и ссылка на чат на сайте — из того же уведомления
- Тонкая настройка: выбираете, какие типы уведомлений получать, а какие отключить

### Автоматизация лотов и сделок

- **Автоподнятие** — поднимает весь каталог или только лоты по ключевым фразам по расписанию. Вы не теряете позиции в поиске, пока занимаетесь другим
- **Автовыдача** — при оплате автоматически отправляет покупателю текст или файл (ключи, инструкции, ссылки). Привязка к ключевым фразам в названии лота
- **Автоподтверждение сделок** — закрывает сделки по правилам без участия человека
- **Автовосстановление** — возвращает проданные и истёкшие лоты на витрину
- **Собственные команды** — настраиваемые триггеры: покупатель пишет слово — бот отвечает заготовленным текстом
- **Ватермарк** — автоматически добавляет подпись ко всем исходящим сообщениям

### Управление и безопасность

- **Профиль** прямо в боте: баланс, активные лоты, количество сделок
- **Статистика сессии**: сделки, возвраты, заработок — сброс в любой момент
- **Пароль доступа** (SHA-256) — никто не управляет вашим магазином кроме вас
- Раздельные **прокси** для Playerok и Telegram API (в том числе SOCKS5)
- **Логи** с ограничением размера; просмотр и скачивание прямо из бота командой `/logs`

### Расширения

Система плагинов, которая позволяет добавлять собственную логику без правки ядра. Расширение — это Python-модуль в папке `ext/` с хуками системных и рыночных событий и опциональным Telegram-роутером.

Расширения включаются, выключаются и **перезагружаются без перезапуска бота** — прямо из меню «Расширения».

---

## Быстрый старт

### 1. Ubuntu/Debian — одна команда

Скрипт сам поставит Python 3.11, скачает последний релиз с GitHub и установит зависимости:

```bash
wget https://raw.githubusercontent.com/exfador/playerok-api/main/install_playerok_api.sh -O install_playerok_api.sh
chmod +x install_playerok_api.sh
sudo bash install_playerok_api.sh
```

По умолчанию проект ставится в `/root/playerok-api`. Своя директория:

```bash
sudo INSTALL_DIR=/opt/playerok-api bash install_playerok_api.sh
```

Запуск в фоне:

```bash
screen -S playerok
cd /root/playerok-api
python3.11 main.py
```

Отсоединиться: `Ctrl+A` → `D`. Вернуться: `screen -r playerok`.

### 2. Вручную (любая ОС)

```bash
git clone https://github.com/exfador/playerok-api
cd playerok-api
pip install -r requirements.txt
python main.py
```

### 3. Windows

Установите Python 3.11+, зависимости — `pip install -r requirements.txt`, запустите `start.bat` или `python main.py`.

### Первый запуск

Консоль задаст несколько вопросов: токен Telegram-бота, пароль панели, JWT Playerok, User-Agent браузера, прокси (если нужны). После этого — `/start` в боте, вводите пароль — и вы в главном меню.

> Не знаете, где взять JWT токен Playerok? Загляните в [чат проекта](https://t.me/coxerhub_ch) — там есть инструкция.

---

## Конфигурация

Основной файл: `conf/config.json`. Создаётся автоматически при первом запуске; при обновлении недостающие ключи дополняются из значений по умолчанию.

| Поле | Описание |
|---|---|
| `bot.token` | Токен от [@BotFather](https://t.me/BotFather) |
| `bot.password_hash` | SHA-256 пароля (задаётся при первом запуске) |
| `bot.proxy` | Прокси для Telegram API |
| `bot.admins` | Список Telegram user id с доступом |
| `account.token` | JWT-сессия Playerok (`cookie: token`) |
| `account.user_agent` | User-Agent браузера |
| `account.proxy` | Прокси для запросов к Playerok |
| `account.timeout` | Таймаут HTTP-запросов, сек. |
| `features` | Ватермарк, команды, автовыдача, приветствие и прочее |
| `auto` | Автовосстановление, автоподтверждение, автоподнятие |
| `alerts` | Фильтры уведомлений |
| `logs.max_mb` | Максимальный размер файла логов |
| `debug.verbose` | Подробный лог |

Дополнительные файлы в `conf/`:

| Файл | Назначение |
|---|---|
| `messages.json` | Шаблоны сообщений |
| `custom_commands.json` | Пользовательские команды |
| `auto_deliveries.json` | Правила автовыдачи |
| `auto_restore_items.json` | Правила автовосстановления |
| `auto_complete_deals.json` | Правила автоподтверждения |
| `auto_bump_items.json` | Фразы для режима «не весь каталог» при поднятии |

---

## Структура репозитория

```
playerok-api/
├── pok/          # Клиент Playerok: HTTP, GraphQL, лента событий (WebSocket + polling)
├── bot/          # Движок рантайма: сделки, чаты, вся автоматизация
├── ctrl/         # Telegram-бот: хендлеры, меню, настройки
├── lib/          # Конфиг, БД (JSON), шина событий, утилиты, загрузчик расширений
├── ext/          # Подключаемые расширения (Python-пакет)
├── conf/         # JSON-конфигурация (создаётся при первом запуске)
├── db/           # Сохранённое состояние (пользователи, статистика и т.д.)
└── main.py       # Точка входа
```

---

## Разработка расширений

Расширение — папка в `ext/` с файлом `__init__.py`. Минимальная структура:

```python
PREFIX      = 'my_ext'
VERSION     = '1.0.0'
NAME        = 'Моё расширение'
DESCRIPTION = 'Что делает'
AUTHORS     = '@username'
LINKS       = 'https://t.me/username'

# Хуки системных событий (BOOT, ALIVE, PANEL_UP, BOT_UP, PLUG_IN, PLUG_OUT)
EVT_WIRE = {
    'BOOT': [on_boot],
}

# Хуки рыночных событий Playerok
from pok.defs import MarketEvent

MKT_WIRE = {
    MarketEvent.NEW_DEAL:     [on_new_deal],
    MarketEvent.NEW_MESSAGE:  [on_new_message],
    MarketEvent.NEW_REVIEW:   [on_new_review],
    # и другие...
}

# Опциональный aiogram-роутер для новых команд/хендлеров в боте
BOT_PATHS = [my_aiogram_router]
```

Полный список рыночных событий: `CHAT_INITIALIZED`, `NEW_MESSAGE`, `NEW_DEAL`, `NEW_REVIEW`, `DEAL_CONFIRMED`, `DEAL_CONFIRMED_AUTOMATICALLY`, `DEAL_ROLLED_BACK`, `DEAL_HAS_PROBLEM`, `DEAL_PROBLEM_RESOLVED`, `DEAL_STATUS_CHANGED`, `ITEM_PAID`, `ITEM_SENT`, `REVIEW_REMOVED`, `REVIEW_UPDATED`.

Расширения можно перезагружать «на горячую» без перезапуска бота через меню **Расширения → Перезагрузить**.

---

## Стек

| Компонент | |
|---|---|
| Python | **3.11+** |
| Telegram | aiogram ≥ 3.11 |
| HTTP | `requests`, `httpx`, `curl-cffi`, `wrapper-tls-requests` |
| WebSocket | `websocket-client` |
| Прокси | PySocks, `aiohttp-socks` |
| Прочее | colorama, colorlog, tqdm, beautifulsoup4, lxml |

---

## Контакты

| | |
|---|---|
| Канал | [@coxerhub_playerok](https://t.me/coxerhub_playerok) |
| Чат проекта | [@coxerhub_ch](https://t.me/coxerhub_ch) |
| Авторы | [@exfador](https://t.me/exfador) · [@terop11](https://t.me/terop11) |
| GitHub | [exfador/playerok-api](https://github.com/exfador/playerok-api) |

Баги, вопросы и предложения — удобнее всего в [чате сообщества](https://t.me/coxerhub_ch).

---

## Ответственность

Используйте в соответствии с правилами Playerok и Telegram. Вы несёте ответственность за действия с вашим аккаунтом и соблюдение применимого законодательства. **Не публикуйте** токены, пароли и JWT.

---

## Лицензия

MIT — см. файл [LICENSE](LICENSE). Версия приложения: [`lib/consts.py`](lib/consts.py).

Если проект оказался полезен — поставьте ⭐ на GitHub.
