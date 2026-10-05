import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import bot.core as core
from bot._kit import best_rule_index, clean_phrases, phrase_in_title
from pok.defs import BoostLevel, DealStage, ListingStage
from pok.models import ItemPriorityStatus, MyItem
from pok.transport import MutationOutcomeUnknown


@pytest.fixture(autouse=True)
def memory_db(monkeypatch):
    import copy
    store = {}
    fake = SimpleNamespace(get=lambda name: copy.deepcopy(store.get(name)),
                           set=lambda name, value: store.__setitem__(name, copy.deepcopy(value)))
    monkeypatch.setattr(core, "db", fake)
    return store


def my_item(**overrides):
    item = object.__new__(MyItem)
    defaults = dict(id="item", name="Telegram Premium", price=276, raw_price=310, status=ListingStage.SOLD,
                    priority=BoostLevel.PREMIUM, sequence=1, priority_position=5, keep_in_sale=False,
                    keep_in_sale_available=True, user=SimpleNamespace(id="seller"), slug="tg")
    defaults.update(overrides)
    for key, value in defaults.items():
        setattr(item, key, value)
    return item


def tier(price, kind=BoostLevel.PREMIUM, tier_id="tier"):
    return ItemPriorityStatus(id=tier_id, price=price, name=kind.name.title(), type=kind, period=30, price_range=None)


def bridge(config=None):
    instance = object.__new__(core.MarketBridge)
    instance.config = config or {
        "alerts": {"enabled": False, "on": {}},
        "features": {"deliveries": True, "greet": True, "watermark": {"enabled": False}},
        "auto": {
            "confirm": {"enabled": True, "all": True},
            "restore": {"sold": True, "expired": False, "all": True, "premium": False, "premium_max_price": 50, "keep_in_sale": False},
            "bump": {"enabled": True, "all": True, "max_price": 50},
        },
    }
    instance._stop_event = threading.Event()
    instance._mutation_guard = threading.Lock()
    instance._reactivating_items = set()
    instance._elevating_items = set()
    instance._delivery_lock = threading.Lock()
    instance.auto_restore_items = {"included": []}
    instance.auto_bump_items = {"included": [], "excluded": []}
    instance.auto_complete_deals = {"included": []}
    instance.initialized_users = ["buyer"]
    instance._notify_reactivated = Mock()
    instance._notify_elevated = Mock()
    instance._notify_uncertain = Mock()
    instance._push_notify = Mock()
    instance._trace_order = Mock()
    instance._render = Mock(return_value=None)
    return instance


@pytest.mark.parametrize("name,phrase,expected", [
    ("Robux 100", "", False),
    ("1000 звёзд Telegram", "100 звёзд", False),
    ("2100 звёзд", "100 звёзд", False),
    ("100 звёзд Telegram", "100 звёзд", True),
    ("Ключ Steam", "ключ steam", True),
    ("Ёлка премиум", "елка", True),
])
def test_phrase_matching_rules(name, phrase, expected):
    assert phrase_in_title(name, phrase) is expected


def test_clean_phrases_drop_empty_values():
    assert clean_phrases("Steam key, ,,Robux ") == ["Steam key", "Robux"]


def test_most_specific_delivery_rule_wins():
    rules = [{"keyphrases": ["звёзд"]}, {"keyphrases": ["1000 звёзд"]}, {"keyphrases": [""]}]
    assert best_rule_index("1000 звёзд Telegram", rules) == 1
    assert best_rule_index("Robux 100", rules) is None


def test_delivery_never_matches_unrelated_item(monkeypatch):
    rules = [{"piece": True, "keyphrases": ["Steam key", ""], "goods": ["KEY-1"]}]
    monkeypatch.setattr(core.cfg, "read", lambda name: rules)
    monkeypatch.setattr(core.cfg, "write", Mock())
    instance = bridge()
    instance._push = Mock(return_value=SimpleNamespace(id="m"))
    deal = SimpleNamespace(id="d", user=SimpleNamespace(id="buyer", username="buyer"), item=SimpleNamespace(name="Robux 100"))
    assert instance._deliver(deal, "chat") == "no_rule"
    instance._push.assert_not_called()


def test_out_of_stock_skips_auto_confirmation(monkeypatch):
    rules = [{"piece": True, "keyphrases": ["Premium"], "goods": []}]
    monkeypatch.setattr(core.cfg, "read", lambda name: rules)
    monkeypatch.setattr(core.cfg, "write", Mock())
    instance = bridge()
    instance._push = Mock(return_value=SimpleNamespace(id="m"))
    item = my_item(status=ListingStage.SOLD)
    deal = SimpleNamespace(id="d", status=DealStage.PAID, user=SimpleNamespace(id="buyer", username="buyer"),
                           item=item, chat=SimpleNamespace(id="chat"))
    instance.account = SimpleNamespace(id="seller", system_chat_id="s", support_chat_id="p",
                                       load_deal=lambda _id: deal, load_listing=lambda _id: item, patch_deal=Mock())
    asyncio.run(instance._on_order(SimpleNamespace(deal=deal, chat=SimpleNamespace(id="chat"))))
    instance.account.patch_deal.assert_not_called()


def test_delivered_good_is_removed_from_fresh_file(monkeypatch):
    stored = {"rules": [{"piece": True, "keyphrases": ["Premium"], "goods": ["A", "B"]}]}
    monkeypatch.setattr(core.cfg, "read", lambda name: [dict(r, goods=list(r["goods"])) for r in stored["rules"]])
    monkeypatch.setattr(core.cfg, "write", lambda name, value: stored.update(rules=value))
    instance = bridge()
    instance._push = Mock(return_value=SimpleNamespace(id="m"))
    deal = SimpleNamespace(id="d", user=SimpleNamespace(id="buyer", username="buyer"), item=SimpleNamespace(name="Telegram Premium"))
    assert instance._deliver(deal, "chat") == "delivered"
    assert stored["rules"][0]["goods"] == ["B"]
    instance._push.assert_called_once_with("chat", "A")


def test_message_delivery_fills_variables_but_keys_stay_raw(monkeypatch):
    rules = [{"piece": False, "keyphrases": ["Premium"], "message": ["Привет, $buyer! Ваш $product: $unknown"]},
             {"piece": True, "keyphrases": ["Steam"], "goods": ["KEY-$buyer"]}]
    monkeypatch.setattr(core.cfg, "read", lambda name: [dict(r) for r in rules])
    monkeypatch.setattr(core.cfg, "write", Mock())
    instance = bridge()
    instance.account = SimpleNamespace(username="seller")
    instance._push = Mock(return_value=SimpleNamespace(id="m"))
    deal = SimpleNamespace(id="d", user=SimpleNamespace(id="buyer", username="anna"), item=SimpleNamespace(name="Premium", price=10))
    assert instance._deliver(deal, "chat") == "delivered"
    instance._push.assert_called_once_with("chat", "Привет, anna! Ваш Premium: $unknown")
    instance._push.reset_mock()
    deal.item = SimpleNamespace(name="Steam key", price=10)
    assert instance._deliver(deal, "chat") == "delivered"
    instance._push.assert_called_once_with("chat", "KEY-$buyer")


def test_own_outgoing_messages_are_not_logged(monkeypatch, caplog):
    import logging
    instance = bridge()
    instance.account = SimpleNamespace(id="seller")
    monkeypatch.setattr(core, "active_engine", lambda: instance)
    room = SimpleNamespace(users=[SimpleNamespace(id="buyer", username="buyer")])
    own = SimpleNamespace(user=SimpleNamespace(id="seller", username="seller"), text="KEY-SECRET-123", event=None, file=None, images=[], buttons=[])
    incoming = SimpleNamespace(user=SimpleNamespace(id="buyer", username="buyer"), text="где ключ?", event=None, file=None, images=[], buttons=[])
    with caplog.at_level(logging.INFO, logger="cxh.bot"):
        instance._trace_msg(own, room)
        instance._trace_msg(incoming, room)
    assert "KEY-SECRET-123" not in caplog.text and "исходящее сообщение" in caplog.text
    assert "где ключ?" in caplog.text


def test_good_that_cannot_return_is_saved_not_logged(monkeypatch, tmp_path, caplog):
    import logging
    import lib.util as util
    monkeypatch.setattr(util, "project_root_dir", lambda: str(tmp_path))
    monkeypatch.setattr(core.cfg, "read", lambda name: [])
    instance = bridge()
    with caplog.at_level(logging.ERROR, logger="cxh.bot"):
        instance._return_delivery({"keyphrases": ["Premium"]}, "KEY-LOST-9")
    assert "KEY-LOST-9" not in caplog.text
    assert "KEY-LOST-9" in (tmp_path / "conf" / "lost_goods.txt").read_text(encoding="utf-8")
    instance._push_notify.assert_called_once()


def test_failed_send_returns_good_to_stock(monkeypatch):
    stored = {"rules": [{"piece": True, "keyphrases": ["Premium"], "goods": ["A"]}]}
    monkeypatch.setattr(core.cfg, "read", lambda name: [dict(r, goods=list(r["goods"])) for r in stored["rules"]])
    monkeypatch.setattr(core.cfg, "write", lambda name, value: stored.update(rules=value))
    instance = bridge()
    instance._push = Mock(return_value=None)
    deal = SimpleNamespace(id="d", user=SimpleNamespace(id="buyer", username="buyer"), item=SimpleNamespace(name="Premium"))
    assert instance._deliver(deal, "chat") == "failed"
    assert stored["rules"][0]["goods"] == ["A"]


def test_paid_restore_is_skipped_when_premium_disabled():
    instance = bridge()
    instance.account = SimpleNamespace(load_listing=lambda _id: my_item(), load_boost_tiers=lambda *a: [tier(19)],
                                       activate_listing=Mock())
    assert instance._reactivate(my_item(), retry_delays=[0]) == "skip_paid_disabled"
    instance.account.activate_listing.assert_not_called()


def test_paid_restore_respects_price_limit():
    instance = bridge()
    instance.config["auto"]["restore"].update(premium=True, premium_max_price=10)
    instance.account = SimpleNamespace(load_listing=lambda _id: my_item(), load_boost_tiers=lambda *a: [tier(19)],
                                       activate_listing=Mock())
    assert instance._reactivate(my_item(), retry_delays=[0]) == "skip_over_limit"
    instance.account.activate_listing.assert_not_called()


def test_paid_restore_uses_cheapest_tier_and_keep_in_sale():
    instance = bridge()
    instance.config["auto"]["restore"].update(premium=True, premium_max_price=50, keep_in_sale=True)
    activate = Mock(return_value=SimpleNamespace(status=ListingStage.PENDING_APPROVAL))
    instance.account = SimpleNamespace(load_listing=lambda _id: my_item(),
                                       load_boost_tiers=lambda *a: [tier(40, tier_id="expensive"), tier(19, tier_id="cheap")],
                                       activate_listing=activate)
    assert instance._reactivate(my_item(), retry_delays=[0]) == "restored"
    activate.assert_called_once_with("item", "cheap", keep_in_sale=True)


def test_active_listing_is_never_paid_again():
    instance = bridge()
    instance.config["auto"]["restore"]["premium"] = True
    activate = Mock()
    instance.account = SimpleNamespace(load_listing=lambda _id: my_item(status=ListingStage.APPROVED),
                                       load_boost_tiers=lambda *a: [tier(19)], activate_listing=activate)
    assert instance._reactivate(my_item(), retry_delays=[0]) == "already_active"
    activate.assert_not_called()


def test_uncertain_restore_is_verified_before_reporting():
    instance = bridge()
    instance.config["auto"]["restore"]["premium"] = True
    states = iter([my_item(status=ListingStage.SOLD), my_item(status=ListingStage.APPROVED)])
    instance.account = SimpleNamespace(load_listing=lambda _id: next(states), load_boost_tiers=lambda *a: [tier(19)],
                                       activate_listing=Mock(side_effect=MutationOutcomeUnknown("publishItem")))
    assert instance._reactivate(my_item(), retry_delays=[0]) == "restored"
    instance._notify_uncertain.assert_not_called()


def test_bump_respects_price_limit():
    instance = bridge()
    instance.config["auto"]["bump"]["max_price"] = 10
    boost = Mock()
    instance.account = SimpleNamespace(load_listing=lambda _id: my_item(status=ListingStage.APPROVED),
                                       load_boost_tiers=lambda *a: [tier(19)], apply_boost=boost)
    assert instance._elevate(my_item(status=ListingStage.APPROVED)) == "skip_price"
    boost.assert_not_called()


def test_bump_keeps_existing_keep_in_sale_flag():
    instance = bridge()
    boost = Mock()
    item = my_item(status=ListingStage.APPROVED, keep_in_sale=True)
    instance.account = SimpleNamespace(load_listing=lambda _id: item, load_boost_tiers=lambda *a: [tier(19)], apply_boost=boost)
    assert instance._elevate(item) == "bumped"
    boost.assert_called_once_with("item", "tier", keep_in_sale=True)


def test_items_screens_render_with_escaping():
    from ctrl.ui import items as items_ui
    item = my_item(name="<3 Premium & co", status=ListingStage.SOLD, views_counter=5, status_description=None)
    text = items_ui.item_text(item)
    assert "&lt;3 Premium &amp; co" in text
    keyboard = items_ui.item_kb(item)
    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert any("Выставить" in label for label in labels)
    assert not any("Оставлять в продаже" in label for label in labels)
    listing = items_ui.items_kb(items_ui.sort_items([item, my_item(id="b", status=ListingStage.APPROVED)]), 0)
    first = listing.inline_keyboard[0][0].text
    assert first.startswith("🟢")
    confirm = items_ui.confirm_text(item, {"name": "Премиум", "price": 19, "type": "PREMIUM"}, True)
    assert "19 ₽" in confirm


@pytest.mark.parametrize("status, priority, shown", [
    (ListingStage.APPROVED, BoostLevel.PREMIUM, True),
    (ListingStage.PENDING_MODERATION, BoostLevel.PREMIUM, True),
    (ListingStage.APPROVED, BoostLevel.DEFAULT, False),
    (ListingStage.SOLD, BoostLevel.PREMIUM, False),
    (ListingStage.EXPIRED, BoostLevel.PREMIUM, False),
])
def test_keep_in_sale_toggle_only_for_active_premium(status, priority, shown):
    from ctrl.ui import items as items_ui
    item = my_item(status=status, priority=priority, status_description=None, views_counter=0)
    labels = [button.text for row in items_ui.item_kb(item).inline_keyboard for button in row]
    assert any("Оставлять в продаже" in label for label in labels) is shown
    assert items_ui.keep_in_sale_editable(item) is shown


def test_set_keep_in_sale_refuses_inactive_or_free_listing():
    instance = bridge()
    edit = Mock()
    for item in (my_item(status=ListingStage.SOLD), my_item(status=ListingStage.APPROVED, priority=BoostLevel.DEFAULT)):
        instance.account = SimpleNamespace(load_listing=lambda _id, item=item: item, set_keep_in_sale=edit)
        with pytest.raises(ValueError, match="PREMIUM"):
            instance.set_keep_in_sale("item", True)
    edit.assert_not_called()


def gated_item(reviews=5, required=20, **overrides):
    values = dict(user=SimpleNamespace(id="seller", reviews_count=reviews),
                  obtaining_type=SimpleNamespace(name="Со входом в аккаунт", props=SimpleNamespace(min_reviews_for_seller=required)),
                  category=SimpleNamespace(props=SimpleNamespace(min_reviews_for_seller=0)))
    values.update(overrides)
    return my_item(**values)


def test_restore_skips_listing_that_needs_more_reviews():
    instance = bridge()
    instance.config["auto"]["restore"]["premium"] = True
    tiers = Mock(return_value=[tier(19)])
    activate = Mock()
    instance.account = SimpleNamespace(load_listing=lambda _id: gated_item(), load_boost_tiers=tiers, activate_listing=activate)
    assert instance._reactivate(my_item(), retry_delays=[0]) == "skip_reviews"
    tiers.assert_not_called()
    activate.assert_not_called()


def test_restore_allowed_when_reviews_are_enough():
    instance = bridge()
    instance.config["auto"]["restore"]["premium"] = True
    activate = Mock(return_value=SimpleNamespace(status=ListingStage.PENDING_APPROVAL))
    instance.account = SimpleNamespace(load_listing=lambda _id: gated_item(reviews=25),
                                       load_boost_tiers=lambda *a: [tier(19)], activate_listing=activate)
    assert instance._reactivate(my_item(), retry_delays=[0]) == "restored"


def test_rejected_restore_is_cached_instead_of_retried():
    from pok.defs import RequestApiError
    rejection = RequestApiError(SimpleNamespace(json=lambda: {"errors": [{"message": "Необходимо иметь более 20 отзывов",
                                                                          "extensions": {"code": "FORBIDDEN"}}]}))
    instance = bridge()
    instance.config["auto"]["restore"]["premium"] = True
    instance._restore_skip_until = {}
    item = my_item(status=ListingStage.EXPIRED)
    activate = Mock(side_effect=rejection)
    instance._listings = Mock(return_value=[item])
    instance.account = SimpleNamespace(load_listing=lambda _id: item, load_boost_tiers=lambda *a: [tier(19)], activate_listing=activate)
    instance._restore_batch([ListingStage.EXPIRED])
    instance._restore_batch([ListingStage.EXPIRED])
    assert activate.call_count == 1
    assert "item" in instance._restore_skip_until


def test_restore_scope_change_takes_effect_on_next_cycle():
    instance = bridge()
    instance.config["auto"]["restore"].update(all=False, premium=True)
    instance._restore_skip_until = {}
    item = my_item(status=ListingStage.EXPIRED)
    activate = Mock(return_value=SimpleNamespace(status=ListingStage.APPROVED))
    instance._listings = Mock(return_value=[item])
    instance._reserve_spend = Mock(return_value=True)
    instance.account = SimpleNamespace(load_listing=lambda _id: item, load_boost_tiers=lambda *a: [tier(19)], activate_listing=activate)
    instance._restore_batch([ListingStage.EXPIRED])
    assert activate.call_count == 0
    assert instance._restore_skip_until == {}
    instance.config["auto"]["restore"]["all"] = True
    instance._restore_batch([ListingStage.EXPIRED])
    assert activate.call_count == 1


def test_restore_skip_cache_resets_when_limits_change():
    instance = bridge()
    instance.config["auto"]["restore"].update(premium=True, premium_max_price=10)
    instance._restore_skip_until = {}
    item = my_item(status=ListingStage.EXPIRED)
    activate = Mock(return_value=SimpleNamespace(status=ListingStage.APPROVED))
    instance._listings = Mock(return_value=[item])
    instance._reserve_spend = Mock(return_value=True)
    instance.account = SimpleNamespace(load_listing=lambda _id: item, load_boost_tiers=lambda *a: [tier(19)], activate_listing=activate)
    instance._restore_batch([ListingStage.EXPIRED])
    instance._restore_batch([ListingStage.EXPIRED])
    assert activate.call_count == 0
    assert "item" in instance._restore_skip_until
    instance.config["auto"]["restore"]["premium_max_price"] = 30
    instance._restore_batch([ListingStage.EXPIRED])
    assert activate.call_count == 1


def test_manual_publish_explains_review_requirement():
    instance = bridge()
    activate = Mock()
    instance.account = SimpleNamespace(load_listing=lambda _id: gated_item(), load_boost_tiers=lambda *a: [tier(19)],
                                       activate_listing=activate)
    with pytest.raises(ValueError, match="20"):
        instance.publish_or_boost("item", "tier")
    activate.assert_not_called()


def test_item_card_hides_publish_when_reviews_missing():
    from ctrl.ui import items as items_ui
    item = gated_item(status=ListingStage.EXPIRED, views_counter=1, status_description=None)
    text = items_ui.item_text(item)
    assert "20" in text and "Со входом в аккаунт" in text
    labels = [button.text for row in items_ui.item_kb(item).inline_keyboard for button in row]
    assert not any("Выставить" in label for label in labels)


@pytest.mark.parametrize("priority,premium,expected", [
    (BoostLevel.PREMIUM, True, "premium"),
    (BoostLevel.PREMIUM, False, "free"),
    (BoostLevel.DEFAULT, True, "free"),
    (BoostLevel.CUSTOM, True, "free"),
])
def test_restore_keeps_premium_placement_only_when_enabled(priority, premium, expected):
    instance = bridge()
    instance.config["auto"]["restore"]["premium"] = premium
    tiers = [tier(19, tier_id="premium"), tier(0, BoostLevel.DEFAULT, tier_id="free")]
    chosen, _ = instance._pick_restore_tier(tiers, priority)
    assert chosen.id == expected


def test_premium_restore_over_limit_falls_back_to_free():
    instance = bridge()
    instance.config["auto"]["restore"].update(premium=True, premium_max_price=10)
    chosen, reason = instance._pick_restore_tier([tier(19, tier_id="premium"), tier(0, BoostLevel.DEFAULT, tier_id="free")],
                                                 BoostLevel.PREMIUM)
    assert (chosen.id, reason) == ("free", "free")


def test_keep_in_sale_requires_premium_placement():
    instance = bridge()
    setter = Mock()
    instance.account = SimpleNamespace(load_listing=lambda _id: my_item(priority=BoostLevel.DEFAULT), set_keep_in_sale=setter)
    with pytest.raises(ValueError):
        instance.set_keep_in_sale("item", True)
    setter.assert_not_called()
    instance.set_keep_in_sale("item", False)
    setter.assert_called_once_with("item", False)


def test_keep_toggle_hidden_for_regular_placement():
    from ctrl.ui import items as items_ui
    item = my_item(status=ListingStage.APPROVED, priority=BoostLevel.DEFAULT, views_counter=0, status_description=None)
    labels = [button.text for row in items_ui.item_kb(item).inline_keyboard for button in row]
    assert not any("Оставлять" in label for label in labels)


def obtain_kind(kind_id, name, required, sequence):
    return SimpleNamespace(id=kind_id, name=name, sequence=sequence, props=SimpleNamespace(min_reviews_for_seller=required))


def test_clone_options_lock_types_needing_more_reviews():
    instance = bridge()
    source = gated_item(category=SimpleNamespace(id="cat", props=SimpleNamespace(min_reviews_for_seller=0)))
    source.obtaining_type.id = "login"
    page = SimpleNamespace(obtaining_types=[obtain_kind("gift", "Подарок", 0, 2), obtain_kind("login", "Со входом в аккаунт", 20, 1)])
    instance.account = SimpleNamespace(load_listing=lambda _id: source, load_obtain_types=lambda _cat: page)
    _, options = instance.clone_options("item")
    assert [(o["id"], o["locked"], o["current"]) for o in options] == [("login", True, True), ("gift", False, False)]
    from ctrl.ui import items as items_ui
    labels = [button.text for row in items_ui.clone_kb(options, "item").inline_keyboard for button in row]
    assert labels[0].startswith("🔒") and "Подарок" in labels[1]


def test_clone_with_locked_type_is_refused_but_other_type_works():
    instance = bridge()
    source = gated_item()
    source.obtaining_type.id = "login"
    clone = Mock(return_value=SimpleNamespace(id="copy"))
    instance.account = SimpleNamespace(load_listing=lambda _id: source, clone_listing=clone)
    with pytest.raises(ValueError):
        instance.clone_listing("item")
    clone.assert_not_called()
    assert instance.clone_listing("item", None, "gift").id == "copy"
    clone.assert_called_once_with(source, price=None, obtaining_type_id="gift")


def test_notifications_are_dropped_safely_without_panel(monkeypatch):
    monkeypatch.setattr(core, "_get_panel", lambda: None)
    monkeypatch.setattr(core, "_get_panel_loop", lambda: None)
    core.MarketBridge._emit("text")
    instance = bridge({"alerts": {"enabled": True, "on": {"deal": False}}})
    emitted = Mock()
    instance._emit = emitted
    core.MarketBridge._push_notify(instance, "deal", "text", None)
    core.MarketBridge._push_notify(instance, "review", "text", None)
    emitted.assert_called_once_with("text", None, None)


def test_review_edit_with_empty_rating_is_reported(monkeypatch):
    instance = bridge({"alerts": {"enabled": True, "on": {"review": True}}})
    instance._emit = Mock()
    instance.account = SimpleNamespace(id="seller")
    monkeypatch.setattr(core, "draw_box", lambda *a, **k: None)
    deal = SimpleNamespace(id="deal", user=SimpleNamespace(id="buyer", username="buyer"), item=SimpleNamespace(name="Лот"),
                           review=SimpleNamespace(rating=None, text=None), chat=None)
    event = SimpleNamespace(deal=deal, previous_fp='{"rating": null, "text": null}')
    asyncio.run(instance._on_review_edit(event))
    instance._emit.assert_called_once()


def test_author_broadcast_is_opt_in():
    from lib.cfg import _DEFAULTS
    assert _DEFAULTS["broadcast"]["enabled"] is False
    assert _DEFAULTS["updater"]["enabled"] is False


def test_bus_accepts_unregistered_market_event():
    from lib import bus
    received = []

    async def handler(*args):
        received.append(args)

    marker = "CUSTOM_EVENT"
    bus.wire_mkt(marker, handler)
    asyncio.run(bus.fire_mkt(marker, [1]))
    bus.mkt_table().pop(marker, None)
    assert received == [(1,)]


def test_logs_are_compressed_and_trimmed_for_telegram(monkeypatch, tmp_path):
    import io
    import os
    import zipfile
    from ctrl import cmd
    path = tmp_path / "bot.log"
    path.write_bytes(b"line | ERROR | x\n" * 10)
    payload, filename, *_ , trimmed = cmd._pack_log(str(path), "log")
    assert filename == "log.txt" and not trimmed
    monkeypatch.setattr(cmd, "_LOG_PLAIN_LIMIT", 64)
    monkeypatch.setattr(cmd, "_LOG_SEND_LIMIT", 600)
    path.write_bytes(os.urandom(4096))
    payload, filename, size, *_ , trimmed = cmd._pack_log(str(path), "log")
    assert filename == "log.zip" and trimmed and size == 4096 and len(payload) <= 600
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert path.read_bytes().endswith(archive.read("log.txt"))


def test_daily_limit_stops_bumps_and_notifies_once(memory_db):
    instance = bridge()
    instance.config["auto"]["daily_limit"] = 20
    boost = Mock()
    item = my_item(status=ListingStage.APPROVED)
    instance.account = SimpleNamespace(load_listing=lambda _id: item, load_boost_tiers=lambda *a: [tier(9)], apply_boost=boost)
    assert [instance._elevate(item) for _ in range(4)] == ["bumped", "bumped", "skip_budget", "skip_budget"]
    assert boost.call_count == 2
    assert memory_db["spend_state"]["total"] == 18
    assert instance._push_notify.call_count == 1


def test_rejected_restore_returns_reserved_money(memory_db):
    from pok.defs import RequestApiError
    rejection = RequestApiError(SimpleNamespace(json=lambda: {"errors": [{"message": "нет", "extensions": {"code": "FORBIDDEN"}}]}))
    instance = bridge()
    instance.config["auto"]["restore"]["premium"] = True
    instance.account = SimpleNamespace(load_listing=lambda _id: my_item(), load_boost_tiers=lambda *a: [tier(19)],
                                       activate_listing=Mock(side_effect=rejection))
    assert instance._reactivate(my_item(), retry_delays=[0]) == "skip_rejected"
    assert memory_db["spend_state"]["total"] == 0


def test_uncertain_paid_restore_keeps_reservation(memory_db):
    instance = bridge()
    instance.config["auto"]["restore"]["premium"] = True
    instance.account = SimpleNamespace(load_listing=lambda _id: my_item(), load_boost_tiers=lambda *a: [tier(19)],
                                       activate_listing=Mock(side_effect=MutationOutcomeUnknown("publishItem")))
    assert instance._reactivate(my_item(), retry_delays=[0]) == "uncertain"
    assert memory_db["spend_state"]["total"] == 19


def test_exhausted_budget_restores_for_free_when_possible(memory_db):
    instance = bridge()
    instance.config["auto"]["restore"]["premium"] = True
    instance.config["auto"]["daily_limit"] = 10
    activate = Mock(return_value=SimpleNamespace(status=ListingStage.PENDING_APPROVAL))
    instance.account = SimpleNamespace(load_listing=lambda _id: my_item(),
                                       load_boost_tiers=lambda *a: [tier(19, tier_id="premium"), tier(0, BoostLevel.DEFAULT, tier_id="free")],
                                       activate_listing=activate)
    assert instance._reactivate(my_item(), retry_delays=[0]) == "restored"
    activate.assert_called_once_with("item", "free", keep_in_sale=None)
    assert (memory_db.get("spend_state") or {}).get("total", 0) == 0


def test_numeric_settings_keep_fractional_values():
    from lib.cfg import _restore
    assert _restore({"limit": 49.5, "flag": 1}, {"limit": 50, "flag": True}) == {"limit": 49.5, "flag": True}


def _cookie_engine(monkeypatch):
    import copy
    from pok.conn import Conn
    stored = {"config": {"account": {"cookies": "token=old; __ddg5_=d", "token": "old", "ddg5": "d"}}}
    monkeypatch.setattr(core.cfg, "read", lambda name: copy.deepcopy(stored[name]))
    monkeypatch.setattr(core.cfg, "write", lambda name, value: stored.__setitem__(name, copy.deepcopy(value)))
    instance = bridge()
    instance.account = Conn(cookies="token=old; __ddg5_=d")
    return instance, stored


def test_rotated_session_cookies_are_saved_once(monkeypatch):
    instance, stored = _cookie_engine(monkeypatch)
    assert instance._persist_rotated_cookies() is False
    instance.account.cookies["token"] = instance.account.token = "new"
    assert instance._persist_rotated_cookies() is True
    assert stored["config"]["account"]["token"] == "new"
    assert "token=new" in stored["config"]["account"]["cookies"]
    assert instance._persist_rotated_cookies() is False


def test_cookies_uploaded_in_panel_are_applied_not_overwritten(monkeypatch):
    instance, stored = _cookie_engine(monkeypatch)
    assert instance._persist_rotated_cookies() is False
    stored["config"]["account"].update(cookies="token=fresh; __ddg5_=e", token="fresh", ddg5="e")
    assert instance._persist_rotated_cookies() is False
    assert stored["config"]["account"]["token"] == "fresh"
    assert instance.account.token == "fresh" and "token=fresh" in instance.account._cookie_header()
    assert instance._persist_rotated_cookies() is False
    assert stored["config"]["account"]["token"] == "fresh"
    instance.account.close()


def test_invalid_session_is_reported_once():
    instance = bridge()
    instance._report_auth_failure(RuntimeError("expired"))
    instance._report_auth_failure(RuntimeError("expired"))
    assert instance._push_notify.call_count == 1


def test_confirmed_publish_does_not_turn_into_paid_boost():
    instance = bridge()
    boost = Mock()
    instance.account = SimpleNamespace(load_listing=lambda _id: my_item(status=ListingStage.APPROVED),
                                       load_boost_tiers=lambda *a: [tier(9)], apply_boost=boost, activate_listing=Mock())
    with pytest.raises(ValueError, match="изменился"):
        instance.publish_or_boost("item", "tier", None, "published")
    boost.assert_not_called()


def test_manual_action_waits_for_running_automation():
    instance = bridge()
    activate = Mock()
    instance.account = SimpleNamespace(load_listing=lambda _id: my_item(), load_boost_tiers=lambda *a: [tier(19)],
                                       activate_listing=activate)
    instance._reactivating_items.add("item")
    with pytest.raises(ValueError, match="автоматика"):
        instance.publish_or_boost("item", "tier")
    activate.assert_not_called()
    instance._reactivating_items.clear()
    instance.publish_or_boost("item", "tier")
    activate.assert_called_once()
    assert not instance._reactivating_items and not instance._elevating_items


def test_template_card_explains_when_it_is_sent(monkeypatch):
    from ctrl.ui import settings
    messages = {"first_message": {"enabled": True, "text": ["Привет"]}, "t_custom": {"enabled": True, "text": ["x"]},
                "deal_pending": {"enabled": False, "text": ["y"]}}
    monkeypatch.setattr(settings.cfg, "read", lambda name: messages)
    assert "первая покупка" in settings.fac_088("first_message")
    assert "вручную" in settings.fac_088("t_custom")
    assert "не используется" in settings.fac_088("deal_pending")


def test_manual_publish_requires_known_tier():
    instance = bridge()
    instance.account = SimpleNamespace(load_listing=lambda _id: my_item(), load_boost_tiers=lambda *a: [tier(19)])
    with pytest.raises(ValueError):
        instance.publish_or_boost("item", "unknown-tier")
