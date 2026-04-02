from aiogram.types import BotCommand

PANEL_COMMANDS: dict[str, tuple[str, str]] = {
    'start': ('handler_start', '🏠 Меню и панель'),
    'logs': ('handler_logs', '📁 Скачать логи'),
    'restart': ('handler_restart', '🔄 Перезапуск бота'),
}


def panel_bot_command_list() -> list[BotCommand]:
    return [BotCommand(command=k, description=v[1]) for k, v in PANEL_COMMANDS.items()]
