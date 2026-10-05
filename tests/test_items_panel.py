import asyncio
import threading
import time

import pytest

import bot.core as core
from ctrl import items as items_ctrl
from ctrl import keys
from pok.gql import item_priority_status, my_item
from pok.transport import MutationOutcomeUnknown
import tests.test_panel_smoke as smoke
from tests.test_panel_smoke import callback_update

smoke_panel = smoke.smoke_panel
SCREEN = 5000


def listing(item_id, status, priority="DEFAULT", keep=False, reviews=5, name="Telegram Premium 1 месяц"):
    return my_item({"__typename": "MyItem", "id": item_id, "slug": f"slug-{item_id}", "name": name, "price": 310,
                    "rawPrice": 330, "status": status, "priority": priority, "keepInSale": keep,
                    "keepInSaleAvailable": True, "viewsCounter": 12,
                    "user": {"__typename": "UserFragment", "id": "seller", "username": "seller", "role": "USER",
                             "testimonialCounter": reviews}})


TIERS = [
    item_priority_status({"__typename": "ItemPriorityStatus", "id": "free", "name": "Обычный", "price": 0, "type": "DEFAULT"}),
    item_priority_status({"__typename": "ItemPriorityStatus", "id": "prem", "name": "Премиум", "price": 19, "type": "PREMIUM", "period": 7}),
]


class FakeEngine:
    def __init__(self):
        self.items = {"sold": listing("sold", "SOLD"), "live": listing("live", "APPROVED", "PREMIUM", keep=True)}
        self.calls = []
        self.result = "published"
        self.delay = 0.0
        self.lock = threading.Lock()

    def my_items(self):
        return list(self.items.values())

    def listing_card(self, item_id):
        if item_id not in self.items:
            raise ValueError("Лот не найден или принадлежит другому продавцу")
        return self.items[item_id]

    def listing_tiers(self, item):
        return list(TIERS)

    def publish_or_boost(self, item_id, tier_id, keep, expected):
        with self.lock:
            self.calls.append(("pay", item_id, tier_id, keep, expected))
        time.sleep(self.delay)
        if self.result == "raise":
            raise MutationOutcomeUnknown("publishItem")
        if self.result == "uncertain":
            return "uncertain", None
        return self.result, self.items[item_id]

    def set_keep_in_sale(self, item_id, value):
        self.calls.append(("keep", item_id, value))
        return self.items[item_id]

    def clone_options(self, item_id):
        return self.items[item_id], [
            {"id": "auto", "name": "Автовыдача", "required": 0, "current": True, "locked": False},
            {"id": "login", "name": "Со входом в аккаунт", "required": 20, "current": False, "locked": True},
        ]

    def clone_listing(self, item_id, price, obtain):
        self.calls.append(("clone", item_id, price, obtain))
        self.items["copy"] = listing("copy", "DRAFT")
        return self.items["copy"]

    def remove_listing(self, item_id):
        self.calls.append(("remove", item_id))
        self.items.pop(item_id)

    def reset_listing_lock(self, item_id):
        self.calls.append(("unlock", item_id))


@pytest.fixture
def items_panel(smoke_panel, monkeypatch):
    instance, session = smoke_panel
    engine = FakeEngine()
    monkeypatch.setattr(core, "live_bridge", lambda: engine)
    items_ctrl._PAID_IN_FLIGHT.clear()
    return instance, session, engine


def press(instance, *datas, concurrent=False, message_id=SCREEN):
    async def go():
        updates = [callback_update(data, message_id) for data in datas]
        if concurrent:
            await asyncio.gather(*(instance.dp.feed_update(instance.bot, u) for u in updates))
        else:
            for update in updates:
                await instance.dp.feed_update(instance.bot, update)

    asyncio.run(go())


def act(do):
    return keys.PduItemAct(do=do).pack()


def open_item(item_id):
    return keys.PduItemOpen(id=item_id).pack()


def shown(session):
    return list(session.buttons.values())


def test_publish_sold_listing_with_paid_tier(items_panel):
    instance, session, engine = items_panel
    press(instance, keys.PduItemsGrid(page=0).pack(), open_item("sold"), act("tiers"), keys.PduItemTier(i=1).pack())
    assert "✅ Подтвердить · 19 ₽" in shown(session)
    press(instance, act("kis"), act("go"))
    assert engine.calls == [("pay", "sold", "prem", True, "published")]


def test_boost_with_free_tier_never_sends_keep_in_sale(items_panel):
    instance, _, engine = items_panel
    engine.result = "boosted"
    press(instance, open_item("live"), act("tiers"), keys.PduItemTier(i=0).pack(), act("go"))
    assert engine.calls == [("pay", "live", "free", None, "boosted")]


def test_double_tap_on_confirm_pays_once(items_panel):
    instance, _, engine = items_panel
    engine.delay = 0.3
    press(instance, open_item("sold"), act("tiers"), keys.PduItemTier(i=1).pack())
    press(instance, act("go"), act("go"), concurrent=True)
    press(instance, act("go"))
    assert [c for c in engine.calls if c[0] == "pay"] == [("pay", "sold", "prem", False, "published")]


def test_confirm_from_another_screen_is_rejected(items_panel):
    instance, session, engine = items_panel
    press(instance, open_item("sold"), act("tiers"), keys.PduItemTier(i=1).pack())
    press(instance, act("go"), message_id=SCREEN + 1)
    assert engine.calls == []
    assert "AnswerCallbackQuery" in session.calls


def test_tier_index_from_old_list_is_rejected(items_panel):
    instance, _, engine = items_panel
    press(instance, open_item("sold"), act("tiers"), keys.PduItemTier(i=7).pack(), act("go"))
    assert engine.calls == []


@pytest.mark.parametrize("result", ["uncertain", "raise"])
def test_uncertain_payment_offers_unlock(items_panel, result):
    instance, session, engine = items_panel
    engine.result = result
    press(instance, open_item("sold"), act("tiers"), keys.PduItemTier(i=1).pack(), act("go"))
    assert "🔓 Я проверил — снять блокировку" in shown(session)
    press(instance, act("unlock"))
    assert engine.calls[-1] == ("unlock", "sold")


def test_clone_refuses_locked_obtaining_type(items_panel):
    instance, session, engine = items_panel
    press(instance, open_item("sold"), act("clone"), keys.PduItemObtain(i=1).pack())
    assert engine.calls == []
    assert "✅ Да" not in shown(session)
    press(instance, keys.PduItemObtain(i=0).pack(), act("clone_go"))
    assert engine.calls == [("clone", "sold", None, "auto")]
    assert "copy" in engine.items


def test_remove_requires_confirmation(items_panel):
    instance, _, engine = items_panel
    press(instance, open_item("sold"), act("remove"))
    assert "sold" in engine.items
    press(instance, act("remove_go"))
    assert "sold" not in engine.items


def test_keep_in_sale_toggle(items_panel):
    instance, _, engine = items_panel
    press(instance, open_item("live"), act("keep"))
    assert engine.calls == [("keep", "live", False)]


def test_missing_engine_and_missing_listing_show_errors(items_panel, monkeypatch):
    instance, session, engine = items_panel
    press(instance, open_item("ghost"))
    assert engine.calls == []
    monkeypatch.setattr(core, "live_bridge", lambda: None)
    press(instance, keys.PduItemsGrid(page=0).pack())
    assert session.calls.count("EditMessageText") >= 2
