# 🏪 CXH Playerok

**Telegram-панель для продавцов на [Playerok](https://playerok.com)** — уведомления, ответы покупателям из Telegram, автоматизация лотов и сделок, расширяемость через модули.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Telegram — канал](https://img.shields.io/badge/Telegram-канал-26A5E4?logo=telegram)](https://t.me/coxerhub_playerok)
[![Telegram — чат](https://img.shields.io/badge/Telegram-чат-26A5E4?logo=telegram)](https://t.me/coxerhub_ch)

Перед настройкой загляните в [**чат проекта**](https://t.me/coxerhub_ch) — помогут с запуском и вопросами. Новости — в [**канале CoxerHub**](https://t.me/coxerhub_playerok).

**Репозиторий:** [github.com/exfador/playerok-api](https://github.com/exfador/playerok-api)

---

## 📋 Содержание

Контакты · Возможности · Стек · Структура репозитория · Конфигурация · Установка (Ubuntu / вручную / Windows) · Расширения · Ответственность · Лицензия

---

## 🤝 Контакты

| | |
| --- | --- |
| **Канал** | [@coxerhub_playerok](https://t.me/coxerhub_playerok) |
| **Чат проекта** | [@coxerhub_ch](https://t.me/coxerhub_ch) |
| **Авторы** | [@exfador](https://t.me/exfador) · [@terop11](https://t.me/terop11) |

Баги и обсуждения удобнее вести в чате сообщества.

---

## 🤖 Возможности

### Playerok — автоматизация

- **Автоподтверждение** сделок по правилам (название лота и списки фраз).
- **Автоподнятие** лотов по расписанию — весь каталог или только лоты по списку фраз в названии.
- **Автовосстановление** проданных и истёкших лотов на витрину.
- **Автовыдача** — текст или пакет файлов при продаже, привязка к ключевым фразам в названии.
- **Свои команды** — ответы на триггеры в чате на площадке.
- **Ватермарк** к исходящим сообщениям на Playerok.
- Работа с сайтом по **HTTP** и **WebSocket**, авторизация через **JWT** и **User-Agent**.

### Telegram — панель и уведомления

- Уведомления о **чатах**, **сделках**, **отзывах**, жалобах и системных событиях — что слать, настраивается переключателями.
- **Ответ покупателю** из Telegram текстом или фото.
- **Шаблоны** с подстановкой переменных (например, покупатель и продавец), просмотр истории чата, ссылка на чат на сайте.
- Из уведомления по сделке: ответ, шаблоны, **закрытие** и **возврат**.
- **Профиль** — баланс, активные лоты и сделки.
- **Статистика** сессии (сделки, возвраты, заработок), сброс из настроек.
- **Пароль** для входа в панель (хэш SHA-256); после входа ваш Telegram user id попадает в список администраторов.
- Отдельные **прокси** для запросов к Playerok и к API Telegram (в том числе SOCKS5), проверка при первом запуске.

### Дополнительно

- **Расширения** — каталог `ext/`, хуки событий и роутеры [aiogram](https://docs.aiogram.dev/) 3.
- Команды бота: `/start`, `/stats`, `/logs`, `/restart`, `/reboot`.
- Логи с ограничением размера файла; локальные данные в JSON (`conf/`, `db/`).

Подробные имена файлов и полей конфига — в разделе **Конфигурация** ниже на этой странице.

---

## 💻 Стек

| Компонент | Примечание |
| --- | --- |
| Python | **3.11+** |
| aiogram | ≥ 3.11 |
| HTTP | `requests`, `httpx`, `curl-cffi`, `wrapper-tls-requests` |
| WebSocket | `websocket-client` |
| Прокси | PySocks, `aiohttp-socks` |
| Прочее | colorama, colorlog, tqdm, beautifulsoup4, lxml |

Полный список зависимостей: [`requirements.txt`](requirements.txt).

---

## 📁 Структура репозитория

| Папка | Назначение |
| --- | --- |
| `pok/` | Клиент и модели Playerok (HTTP, GraphQL, лента событий) |
| `bot/` | Движок рантайма: сделки, чаты, автоматизация |
| `ctrl/` | Telegram-бот: хендлеры, меню, настройки |
| `lib/` | Конфиг, БД (JSON), шина событий, утилиты, загрузка расширений |
| `ext/` | Подключаемые расширения (пакет `ext`) |
| `conf/` | JSON-конфигурация |
| `db/` | Сохранённое состояние (пользователи, статистика и т.д.) |

---

## ⚙️ Конфигурация

Основной файл: **`conf/config.json`** — при обновлении приложения недостающие ключи дополняются из значений по умолчанию.

| Раздел / поле | Описание |
| --- | --- |
| `bot.token` | Токен от [@BotFather](https://t.me/BotFather) |
| `bot.password_hash` | SHA-256 пароля (задаётся при первом запуске в консоли) |
| `bot.proxy` | Прокси для Telegram API |
| `bot.admins` | Список Telegram user id с доступом к панели |
| `account.token` | JWT сессии Playerok (cookie `token`) |
| `account.user_agent` | User-Agent браузера |
| `account.proxy` | Прокси для запросов к Playerok |
| `account.timeout` | Таймаут HTTP-запросов, сек. |
| `features` | Ватермарк, приветствие, чат, команды, автовыдача и др. |
| `auto` | Автовосстановление, автоподтверждение, автоподнятие |
| `alerts` | Какие типы уведомлений отправлять в Telegram |
| `logs.max_mb` | Максимальный размер файла логов |
| `debug.verbose` | Подробный лог |

Дополнительные файлы в `conf/`:

- `messages.json` — шаблоны сообщений  
- `custom_commands.json` — пользовательские команды  
- `auto_deliveries.json` — правила автовыдачи  
- `auto_restore_items.json` — правила автовосстановления  
- `auto_complete_deals.json` — правила автоподтверждения  
- `auto_bump_items.json` — список фраз для режима «не весь каталог» при поднятии  

---

## ⬇️ Установка и запуск

### Ubuntu / Debian (скрипт)

Скрипт [`install_playerok_api.sh`](install_playerok_api.sh) рассчитан на **Ubuntu/Debian под root**: ставит зависимости для сборки Python, собирает **Python 3.11.8** (`make altinstall` → команда `python3.11`), скачивает архив с GitHub по **последнему релизу** или, если релиза нет, по **последнему тегу** ([теги](https://github.com/exfador/playerok-api/tags)), распаковывает в каталог установки и выполняет `pip install -r requirements.txt`. Сборка интерпретатора может занять **несколько минут**.

Скачать и запустить:

```bash
wget https://raw.githubusercontent.com/exfador/playerok-api/main/install_playerok_api.sh -O install_playerok_api.sh
chmod +x install_playerok_api.sh
sudo bash install_playerok_api.sh
```

По умолчанию проект ставится в **`/root/playerok-api`**. Свой путь:

```bash
sudo INSTALL_DIR=/opt/playerok-api bash install_playerok_api.sh
```

Запуск в фоне через **screen**:

```bash
screen -S playerok
cd /root/playerok-api
python3.11 main.py
```

Отсоединиться: `Ctrl+A`, затем `D`. Вернуться: `screen -r playerok`.

Скрипт **всегда** подтягивает код с GitHub (релиз/тег), а не из текущей папки. Установка из уже склонированной копии без скачивания архива — см. блок **«Вручную»** ниже.

### Вручную (любая ОС, из клона репозитория)

Нужен **Python 3.11+** и зависимости из репозитория:

```bash
pip install -r requirements.txt
python main.py
```

**Первый запуск:** в консоли задаются токен бота, пароль панели, при необходимости прокси, JWT Playerok и User-Agent; выполняется проверка доступа к Playerok и Telegram.

**В Telegram:** `/start` → ввод пароля → главное меню. Дальнейшие настройки — в разделе «Настройки» в боте.

### Windows

Можно использовать [`start.bat`](start.bat) (запускает `python main.py`), предварительно установив Python 3.11+ и зависимости: `pip install -r requirements.txt`.

---

## 🧩 Расширения

- Каталог: **`ext/`** (Python-пакет `ext`).
- В модулях задаются хуки системы и рынка и при необходимости роутеры Telegram.
- Управление — пункт **«Расширения»** в меню бота.

---

## ⚠️ Ответственность

Использование должно соответствовать правилам **Playerok** и **Telegram**. Вы несёте ответственность за действия с аккаунтом и за соблюдение законодательства. **Не публикуйте** токены, пароли и JWT.

---

## ⭐ Лицензия и версия

Проект распространяется по лицензии **MIT** — см. файл [`LICENSE`](LICENSE).

Версия приложения задаётся в [`lib/consts.py`](lib/consts.py) (`VERSION`).

Если репозиторий оказался полезен — можно поставить ⭐ на GitHub.
