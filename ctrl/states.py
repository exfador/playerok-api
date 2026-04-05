from aiogram.fsm.state import State, StatesGroup


class PduGateGrp(StatesGroup):
    pdu_gate_secret = State()


class PduReplyDraftGrp(StatesGroup):
    pdu_reply_body = State()


class PduConnGrp(StatesGroup):
    pdu_golden_key = State()
    pdu_browser_ua = State()
    pdu_http_timeout = State()
    pdu_listener_delay = State()
    pdu_pl_proxy_line = State()
    pdu_tg_proxy_line = State()
    pdu_wm_text = State()
    pdu_log_tail = State()


class PduTplGrp(StatesGroup):
    pdu_tpl_sheet = State()
    pdu_tpl_body = State()
    pdu_tpl_name_new = State()
    pdu_tpl_text_new = State()


class PduAddonGrp(StatesGroup):
    pdu_addon_sheet = State()


class PduReviveGrp(StatesGroup):
    pdu_revive_poll_sec = State()
    pdu_revive_phrase_line = State()
    pdu_revive_phrase_bulk = State()


class PduSealGrp(StatesGroup):
    pdu_seal_phrase_line = State()
    pdu_seal_phrase_bulk = State()


class PduBoostGrp(StatesGroup):
    pdu_boost_interval_sec = State()
    pdu_boost_allow_line = State()
    pdu_boost_allow_bulk = State()
    pdu_boost_deny_line = State()
    pdu_boost_deny_bulk = State()


class PduCmdGrp(StatesGroup):
    pdu_cmd_body_new = State()
    pdu_cmd_sheet = State()
    pdu_cmd_reply = State()


class PduFulfillGrp(StatesGroup):
    pdu_ff_sheet = State()
    pdu_ff_keys_new = State()
    pdu_ff_piece_new = State()
    pdu_ff_msg_new = State()
    pdu_ff_goods_new = State()
    pdu_ff_keys_edit = State()
    pdu_ff_piece_edit = State()
    pdu_ff_msg_edit = State()
    pdu_ff_goods_add = State()


PluginsStates = PduAddonGrp
