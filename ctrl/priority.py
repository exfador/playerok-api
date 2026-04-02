import asyncio
from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from lib.cfg import AppConf as cfg
from lib.util import reboot
from .helpers import do_auth

router = Router()


@router.message(Command('restart', 'reboot'))
async def handler_restart(message: types.Message, state: FSMContext):
    await state.set_state(None)
    config = cfg.get('config')
    if message.from_user.id not in config['bot']['admins']:
        return await do_auth(message, state)
    try:
        await message.answer('🔄 Перезагружаюсь…')
    except Exception:
        pass
    await asyncio.sleep(0.6)
    try:
        reboot()
    except OSError as e:
        await message.answer(f'❌ Не удалось перезапустить процесс: {e}')
