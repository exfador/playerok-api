from aiogram.filters.callback_data import CallbackData
from uuid import UUID


class PduRootNav(CallbackData, prefix='cxMn'):
    to: str


class PduPrefsScope(CallbackData, prefix='cxSt'):
    to: str


class PduBotPrefsNav(CallbackData, prefix='cxBs'):
    to: str


class PduCatalogPrefsNav(CallbackData, prefix='cxIs'):
    to: str


class PduHelpNav(CallbackData, prefix='cxIn'):
    to: str


class PduAddonOpen(CallbackData, prefix='cxExP'):
    uuid: UUID


class PduTplOpen(CallbackData, prefix='cxMsP'):
    message_id: str


class PduCmdOpen(CallbackData, prefix='cxCcP'):
    cmd_id: str


class PduCmdEvtFlip(CallbackData, prefix='cxCcE'):
    cmd_id: str
    kind: str


class PduFulfillOpen(CallbackData, prefix='cxAdP'):
    index: int


class PduAddonGrid(CallbackData, prefix='cxExG'):
    page: int


class PduReviveAllowPage(CallbackData, prefix='cxRsP'):
    page: int


class PduSealAllowPage(CallbackData, prefix='cxShP'):
    page: int


class PduBoostAllowPage(CallbackData, prefix='cxBiP'):
    page: int


class PduBoostDenyPage(CallbackData, prefix='cxBxP'):
    page: int


class PduCmdGrid(CallbackData, prefix='cxCcG'):
    page: int


class PduFulfillGrid(CallbackData, prefix='cxAdG'):
    page: int


class PduFulfillFilesPage(CallbackData, prefix='cxDgP'):
    page: int


class PduTplGrid(CallbackData, prefix='cxMgP'):
    page: int


class PduNickMemo(CallbackData, prefix='cxRu'):
    name: str
    do: str


class PduDealMemo(CallbackData, prefix='cxRd'):
    de_id: str
    do: str


class PduLogTplMenu(CallbackData, prefix='cxLm'):
    page: int


class PduLogTplFire(CallbackData, prefix='cxLs'):
    idx: int


class PduLogChatScroll(CallbackData, prefix='cxLc'):
    chat_id: str
    page: int = 0


class PduReviveAllowDrop(CallbackData, prefix='cxDRi'):
    index: int


class PduSealAllowDrop(CallbackData, prefix='cxDSh'):
    index: int


class PduBoostAllowDrop(CallbackData, prefix='cxDBi'):
    index: int


class PduBoostDenyDrop(CallbackData, prefix='cxDBx'):
    index: int


class PduLogExport(CallbackData, prefix='cxSL'):
    lines: int


class PduFulfillModePick(CallbackData, prefix='cxAP'):
    val: bool


class PduFulfillFileDrop(CallbackData, prefix='cxDG'):
    index: int
