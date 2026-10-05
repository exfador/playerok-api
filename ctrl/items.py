import asyncio
import html
from logging import getLogger

from aiogram import Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from . import keys as calls
from . import ui as templ
from .helpers import emit_overlay
from .ui import items as items_ui
from pok.conn import PUBLISHABLE_STAGES
from pok.transport import MutationOutcomeUnknown

logger = getLogger('cxh.ctrl')
router = Router(name='items')
_PAID_IN_FLIGHT: set[str] = set()


def _engine():
    from bot.core import live_bridge
    engine = live_bridge()
    if engine is None:
        raise RuntimeError('Движок Playerok ещё не запущен')
    return engine


def _back_to_menu():
    return templ.fac_023(calls.PduRootNav(to='default').pack())


async def _show(callback: CallbackQuery, state: FSMContext, text: str, kb) -> None:
    shown = await emit_overlay(state=state, message=callback.message, text=text, reply_markup=kb, callback=callback)
    await state.update_data(item_message_id=getattr(shown, 'message_id', None) or callback.message.message_id)


async def _stale(callback: CallbackQuery, data: dict) -> bool:
    if data.get('item_message_id') == callback.message.message_id:
        return False
    await callback.answer('Этот экран устарел — откройте лот заново', show_alert=True)
    return True


async def _fail(callback: CallbackQuery, state: FSMContext, exc: Exception, item_id: str | None = None) -> None:
    logger.warning('[tg] мои лоты: %s', exc)
    kb = items_ui.uncertain_kb(item_id) if item_id and isinstance(exc, MutationOutcomeUnknown) else (
        templ.fac_023(calls.PduItemOpen(id=item_id).pack()) if item_id else _back_to_menu()
    )
    await _show(callback, state, f'📦 <b>Мои лоты</b>\n\n❌ {html.escape(str(exc))}', kb)


async def _open_item(callback: CallbackQuery, state: FSMContext, item_id: str, note: str | None = None) -> None:
    item = await asyncio.to_thread(_engine().listing_card, item_id)
    data = await state.get_data()
    await state.update_data(item_id=item.id, item_tiers=None, item_tier=None)
    await _show(callback, state, items_ui.item_text(item, note), items_ui.item_kb(item, data.get('items_page', 0)))


@router.callback_query(calls.PduItemsGrid.filter())
async def on_items_grid(callback: CallbackQuery, callback_data: calls.PduItemsGrid, state: FSMContext):
    await state.set_state(None)
    try:
        items = items_ui.sort_items(await asyncio.to_thread(_engine().my_items))
    except Exception as exc:
        return await _fail(callback, state, exc)
    page = max(0, callback_data.page)
    await state.update_data(items_page=page)
    await _show(callback, state, items_ui.items_text(items, page), items_ui.items_kb(items, page))


@router.callback_query(calls.PduItemOpen.filter())
async def on_item_open(callback: CallbackQuery, callback_data: calls.PduItemOpen, state: FSMContext):
    await state.set_state(None)
    try:
        await _open_item(callback, state, callback_data.id)
    except Exception as exc:
        await _fail(callback, state, exc)


@router.callback_query(calls.PduItemTier.filter())
async def on_item_tier(callback: CallbackQuery, callback_data: calls.PduItemTier, state: FSMContext):
    data = await state.get_data()
    if await _stale(callback, data):
        return
    item_id, tiers = data.get('item_id'), data.get('item_tiers') or []
    if not item_id or not 0 <= callback_data.i < len(tiers):
        return await callback.answer('Список тарифов устарел — откройте лот заново', show_alert=True)
    try:
        item = await asyncio.to_thread(_engine().listing_card, item_id)
    except Exception as exc:
        return await _fail(callback, state, exc, item_id)
    tier = tiers[callback_data.i]
    keep = bool(item.keep_in_sale)
    await state.update_data(item_tier=tier, item_keep=keep)
    await _show(callback, state, items_ui.confirm_text(item, tier, keep), items_ui.confirm_kb(item, tier, keep))


@router.callback_query(calls.PduItemObtain.filter())
async def on_item_obtain(callback: CallbackQuery, callback_data: calls.PduItemObtain, state: FSMContext):
    data = await state.get_data()
    if await _stale(callback, data):
        return
    item_id, options = data.get('item_id'), data.get('item_obtains') or []
    if not item_id or not 0 <= callback_data.i < len(options):
        return await callback.answer('Список устарел — откройте лот заново', show_alert=True)
    option = options[callback_data.i]
    if option['locked']:
        return await callback.answer(f'Playerok требует {option["required"]}+ отзывов для этого способа', show_alert=True)
    await state.update_data(item_obtain=option['id'])
    name = html.escape(option['name'] or '—')
    await _show(callback, state, f'📄 Создать черновик-копию со способом получения «{name}»?', items_ui.yes_no_kb('clone_go', item_id))


@router.callback_query(calls.PduItemAct.filter())
async def on_item_action(callback: CallbackQuery, callback_data: calls.PduItemAct, state: FSMContext):
    data = await state.get_data()
    if await _stale(callback, data):
        return
    item_id = data.get('item_id')
    if not item_id:
        return await callback.answer('Откройте лот заново', show_alert=True)
    action = callback_data.do
    try:
        engine = _engine()
        if action == 'tiers':
            item = await asyncio.to_thread(engine.listing_card, item_id)
            tiers = await asyncio.to_thread(engine.listing_tiers, item)
            stored = [{'id': t.id, 'name': t.name, 'price': t.price, 'type': getattr(t.type, 'name', None), 'period': t.period} for t in tiers]
            intent = 'published' if item.status in PUBLISHABLE_STAGES else 'boosted'
            await state.update_data(item_tiers=stored, item_intent=intent)
            return await _show(callback, state, items_ui.tiers_text(item, tiers), items_ui.tiers_kb(tiers, item.id))
        if action == 'kis':
            tier = data.get('item_tier')
            if not tier:
                return await _open_item(callback, state, item_id)
            item = await asyncio.to_thread(engine.listing_card, item_id)
            keep = not bool(data.get('item_keep'))
            await state.update_data(item_keep=keep)
            return await _show(callback, state, items_ui.confirm_text(item, tier, keep), items_ui.confirm_kb(item, tier, keep))
        if action == 'go':
            tier = data.get('item_tier')
            if not tier:
                return await _open_item(callback, state, item_id)
            if item_id in _PAID_IN_FLIGHT:
                return await callback.answer('Операция с этим лотом уже выполняется', show_alert=True)
            _PAID_IN_FLIGHT.add(item_id)
            try:
                await state.update_data(item_tier=None)
                keep = bool(data.get('item_keep')) if tier.get('type') == 'PREMIUM' else None
                result, _ = await asyncio.to_thread(engine.publish_or_boost, item_id, tier['id'], keep, data.get('item_intent'))
            finally:
                _PAID_IN_FLIGHT.discard(item_id)
            if result == 'uncertain':
                return await _show(
                    callback, state,
                    '❔ <b>Результат неизвестен</b>\n\nPlayerok не ответил однозначно. Проверьте лот на сайте — '
                    'повторная платная операция с ним заблокирована, чтобы не списать деньги дважды.',
                    items_ui.uncertain_kb(item_id),
                )
            note = '✅ Лот выставлен.' if result == 'published' else '✅ Лот поднят.'
            return await _open_item(callback, state, item_id, note)
        if action == 'keep':
            item = await asyncio.to_thread(engine.listing_card, item_id)
            updated = await asyncio.to_thread(engine.set_keep_in_sale, item_id, not bool(item.keep_in_sale))
            return await _open_item(callback, state, updated.id, '✅ Настройка сохранена.')
        if action == 'clone':
            source, options = await asyncio.to_thread(engine.clone_options, item_id)
            await state.update_data(item_obtains=options, item_obtain=None)
            return await _show(callback, state, items_ui.clone_text(source, options), items_ui.clone_kb(options, item_id))
        if action == 'clone_go':
            obtain = data.get('item_obtain')
            await state.update_data(item_obtain=None, item_obtains=None)
            created = await asyncio.to_thread(engine.clone_listing, item_id, None, obtain)
            return await _open_item(callback, state, created.id, '✅ Копия создана как черновик.')
        if action == 'remove':
            return await _show(callback, state, '🗑 Удалить лот с Playerok? Отменить нельзя.', items_ui.yes_no_kb('remove_go', item_id))
        if action == 'remove_go':
            await asyncio.to_thread(engine.remove_listing, item_id)
            await state.update_data(item_id=None)
            items = items_ui.sort_items(await asyncio.to_thread(engine.my_items))
            page = data.get('items_page', 0)
            return await _show(callback, state, '✅ Лот удалён.\n\n' + items_ui.items_text(items, page), items_ui.items_kb(items, page))
        if action == 'unlock':
            engine.reset_listing_lock(item_id)
            return await _open_item(callback, state, item_id, '🔓 Блокировка снята.')
        await callback.answer('Неизвестное действие', show_alert=True)
    except Exception as exc:
        await _fail(callback, state, exc, item_id)
