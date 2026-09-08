<div align="center">

# 🏪 Playerok API — Python-клиент и Telegram-бот | CXH

### Управление магазином Playerok из Telegram — сообщения, сделки и автоматизация 24/7

[![Release](https://img.shields.io/github/v/release/exfador/playerok-api?style=for-the-badge&color=7c3aed)](https://github.com/exfador/playerok-api/releases/latest)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-56%20passed-22c55e?style=for-the-badge)](#тестирование)
[![License](https://img.shields.io/github/license/exfador/playerok-api?style=for-the-badge&color=0ea5e9)](LICENSE)

**Уведомления в реальном времени · Ответы покупателям · Автовыдача · Автоподнятие · Мониторинг соединения**

[Скачать последнюю версию](https://github.com/exfador/playerok-api/releases/latest) · [Релиз 2.0.5](https://github.com/exfador/playerok-api/releases/tag/2.0.5) · [Сообщить об ошибке](https://github.com/exfador/playerok-api/issues)

</div>

---

## О проекте

**CXH Playerok** — неофициальный Python-клиент и Telegram-панель для автоматизации магазина на Playerok.

Бот работает в фоне, получает события через GraphQL WebSocket и переносит основные операции продавца в Telegram: новые сообщения, сделки, отзывы, жалобы, управление объявлениями и автоматическую выдачу товара.

```text
Покупатель пишет → бот присылает уведомление → продавец отвечает из Telegram
                           ↓
             автоматизация обрабатывает сделку
```

> [!IMPORTANT]
> Статус «онлайн» поддерживается, пока процесс бота запущен, интернет доступен, а cookies или токен Playerok остаются действительными.

## Возможности

<table>
<tr>
<td width="50%" valign="top">

### 💬 Чаты и уведомления

- новые сообщения и чаты;
- ответы текстом и фотографиями;
- уведомления о сделках, отзывах и жалобах;
- история переписки;
- шаблоны ответов с переменными;
- пользовательские команды-триггеры.

</td>
<td width="50%" valign="top">

### ⚙️ Автоматизация

- автовыдача цифрового товара;
- автоподтверждение сделок;
- восстановление проданных и истёкших лотов;
- поднятие объявлений по расписанию;
- фильтры по ключевым словам;
- настраиваемый watermark.

</td>
</tr>
<tr>
<td width="50%" valign="top">

### 🟢 Работа 24/7

- WebSocket `ping/pong` и heartbeat;
- контроль ACK и зависших соединений;
- автоматический reconnect с backoff;
- восстановление подписок;
- supervisor Playerok Feed;
- восстановление Telegram polling.

</td>
<td width="50%" valign="top">

### 🔐 Безопасность

- salted PBKDF2 для пароля панели;
- фильтрация доменов cookies;
- поддержка HTTPS и SOCKS-прокси;
- скрытие секретов в health-ответах;
- приватные разрешения конфигурации;
- резервные копии повреждённых JSON.

</td>
</tr>
</table>

## Быстрый старт

### Требования

- Python **3.10+**;
- токен Telegram-бота от [@BotFather](https://t.me/BotFather);
- cookies или токен активной сессии Playerok;
- прокси или VPN, если сервисы недоступны напрямую.

### Linux, macOS и Windows

```bash
git clone https://github.com/exfador/playerok-api.git
cd playerok-api

python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

python3 main.py
```

Активация виртуального окружения в Windows:

```powershell
.venv\Scripts\activate
python -m pip install -r requirements.txt
python main.py
```

Также в Windows можно использовать `start.bat` после установки зависимостей.

### Ubuntu/Debian одной командой

```bash
wget https://raw.githubusercontent.com/exfador/playerok-api/main/install_playerok_api.sh
chmod +x install_playerok_api.sh
sudo bash install_playerok_api.sh
```

По умолчанию проект устанавливается в `/root/playerok-api`. Чтобы выбрать другой каталог:

```bash
sudo INSTALL_DIR=/opt/playerok-api bash install_playerok_api.sh
```

> [!WARNING]
> Установочный скрипт заменяет содержимое каталога `INSTALL_DIR`. Не указывайте домашнюю папку, корень системы или каталог с важными файлами.

## Первый запуск

Интерактивный мастер попросит указать:

1. токен Telegram-бота;
2. пароль администратора;
3. cookies или токен Playerok;
4. User-Agent браузера;
5. прокси — при необходимости.

После запуска откройте своего Telegram-бота, отправьте `/start` и пройдите авторизацию администратора.

Основная конфигурация создаётся в `conf/config.json` и автоматически дополняется новыми параметрами после обновлений.

> [!CAUTION]
> Не публикуйте `conf/config.json`, cookies, токены, пароли, содержимое `db/` и рабочие логи.

## Команды Telegram

| Команда | Назначение |
|---|---|
| `/start` | Открыть главное меню и пройти авторизацию |
| `/status` | Проверить Playerok, WebSocket, Telegram API и фоновые процессы |
| `/online` | Короткий алиас команды `/status` |
| `/logs` | Скачать журнал работы за выбранную дату |
| `/restart` | Корректно перезапустить приложение |

### Что показывает `/status`

- аптайм приложения;
- подключение к Playerok;
- время последнего WebSocket-ответа;
- количество reconnect;
- активные подписки;
- состояние Telegram polling и API;
- состояние supervisor и фоновых workers;
- последнюю ошибку без cookies, токенов и паролей.

## Конфигурация

| Раздел | Назначение |
|---|---|
| `account` | Авторизация Playerok, User-Agent, timeout и прокси |
| `bot` | Токен Telegram, прокси, пароль и список администраторов |
| `features` | Watermark, команды, приветствия и автовыдача |
| `auto.restore` | Восстановление проданных и истёкших лотов |
| `auto.confirm` | Автоматическое подтверждение сделок |
| `auto.bump` | Поднятие объявлений по расписанию |
| `alerts` | Фильтры Telegram-уведомлений |
| `updater` | Проверка и установка обновлений |
| `broadcast` | Системные объявления проекта |
| `logs` | Ограничение размера журналов |
| `debug` | Подробное логирование запросов и событий |

Дополнительные данные находятся в отдельных файлах:

| Файл | Содержимое |
|---|---|
| `conf/messages.json` | Шаблоны сообщений |
| `conf/custom_commands.json` | Пользовательские команды |
| `conf/auto_deliveries.json` | Правила автовыдачи |
| `conf/auto_restore_items.json` | Фильтры восстановления |
| `conf/auto_complete_deals.json` | Правила подтверждения сделок |
| `conf/auto_bump_items.json` | Фильтры поднятия объявлений |

## Использование Playerok API

Минимальный пример авторизации и получения чатов:

```python
from pok.conn import Conn

account = Conn(
    cookies="token=YOUR_PLAYEROK_TOKEN",
    user_agent="YOUR_BROWSER_USER_AGENT",
).get()

print(account.username)

chat_list = account.load_chats(count=20)
for chat in chat_list.chats:
    print(chat.id)
```

Доступные группы методов:

- профиль и пользователи;
- игры и категории;
- объявления и приоритеты;
- чаты, сообщения и загрузка изображений;
- сделки и изменение их статуса;
- транзакции и платёжные провайдеры.

> [!NOTE]
> API Playerok не является публично документированным и может изменяться без предупреждения. Перед массовыми или платными операциями проверяйте поведение на тестовом объявлении.

## Запуск 24/7

Для сервера удобно использовать `systemd` или `screen`.

Пример запуска через `screen`:

```bash
screen -S playerok
cd /root/playerok-api
python3.11 main.py
```

- Отсоединиться: `Ctrl+A`, затем `D`.
- Вернуться: `screen -r playerok`.
- Проверить состояние: отправить `/status` в Telegram.

Для production-сервера рекомендуется создать отдельного системного пользователя, использовать виртуальное окружение и настроить автоматический перезапуск процесса.

## Архитектура

```text
playerok-api/
├── pok/       Playerok HTTP, GraphQL, модели и WebSocket Feed
├── bot/       движок сделок, чатов и автоматизации
├── ctrl/      Telegram-панель, команды, FSM и интерфейс
├── lib/       конфигурация, БД, updater, event bus и утилиты
├── tests/     regression- и hardening-тесты
├── conf/      локальная конфигурация
├── db/        рабочее состояние приложения
└── main.py    точка входа
```

## Тестирование

```bash
python3 -m unittest -q
python3 -m ruff check .
python3 -m compileall -q .
```

Текущее состояние версии 2.0.5:

| Проверка | Результат |
|---|:---:|
| Автоматические тесты | **56/56** ✅ |
| Ruff | **Passed** ✅ |
| `compileall` | **Passed** ✅ |
| WebSocket ACK | **Passed** ✅ |
| Reconnect и восстановление подписок | **Passed** ✅ |
| Graceful shutdown | **Passed** ✅ |

## Обновление

Последний релиз доступен на странице [Releases](https://github.com/exfador/playerok-api/releases/latest).

При ручном обновлении обязательно сохраните приватные данные вне публичного архива:

```text
conf/config.json
conf/cookies.json
db/
logs/
```

Механизм встроенного обновления использует staging и откат при ошибке, чтобы приложение не запускалось из частично обновлённого каталога.

## Контакты

| Ресурс | Ссылка |
|---|---|
| Telegram-канал | [@coxerhub_playerok](https://t.me/coxerhub_playerok) |
| Чат сообщества | [@coxerhub_ch](https://t.me/coxerhub_ch) |
| Авторы | [@exfador](https://t.me/exfador) · [@terop11](https://t.me/terop11) |
| GitHub Issues | [Сообщить об ошибке](https://github.com/exfador/playerok-api/issues) |

## Ответственность

Проект не является официальным продуктом Playerok. Используйте его в соответствии с правилами Playerok и Telegram, а также применимым законодательством.

Вы самостоятельно отвечаете за действия с аккаунтом, автоматические операции, сохранность авторизационных данных и возможные ограничения со стороны платформы.

## Лицензия

Проект распространяется по лицензии [MIT](LICENSE).

<div align="center">

---

Если проект оказался полезен — поставьте ⭐ на [GitHub](https://github.com/exfador/playerok-api).

**CXH Playerok — меньше рутины, быстрее ответы, стабильнее магазин.**

</div>
