from aiogram.filters.callback_data import CallbackData
from uuid import UUID


class MenuNavigation(CallbackData, prefix='menpag'):
    to: str


class SettingsNavigation(CallbackData, prefix='sepag'):
    to: str


class BotSettingsNavigation(CallbackData, prefix='bspag'):
    to: str


class ItemsSettingsNavigation(CallbackData, prefix='ispag'):
    to: str


class InstructionNavigation(CallbackData, prefix='inspag'):
    to: str


class ExtPage(CallbackData, prefix='extpage'):
    uuid: UUID


class MessagePage(CallbackData, prefix='messpage'):
    message_id: str


class CustomCommandPage(CallbackData, prefix='cucopage'):
    cmd_id: str


class CustomCommandToggleEvent(CallbackData, prefix='ccmbev'):
    cmd_id: str
    kind: str


class AutoDeliveryPage(CallbackData, prefix='audepage'):
    index: int


class ExtPagination(CallbackData, prefix='extpag'):
    page: int


class IncludedRestoreItemsPagination(CallbackData, prefix='inrepag'):
    page: int


class IncludedCompleteDealsPagination(CallbackData, prefix='incopag'):
    page: int


class IncludedBumpItemsPagination(CallbackData, prefix='inbupag'):
    page: int


class ExcludedBumpItemsPagination(CallbackData, prefix='exbupag'):
    page: int


class CustomCommandsPagination(CallbackData, prefix='cucopag'):
    page: int


class AutoDeliveriesPagination(CallbackData, prefix='audepag'):
    page: int


class DelivGoodsPagination(CallbackData, prefix='godspag'):
    page: int


class MessagesPagination(CallbackData, prefix='messpag'):
    page: int


class RememberUsername(CallbackData, prefix='rech'):
    name: str
    do: str


class RememberDealId(CallbackData, prefix='rede'):
    de_id: str
    do: str


class LogTemplateMenu(CallbackData, prefix='ltm'):
    page: int


class LogTemplateSend(CallbackData, prefix='lts'):
    idx: int


class LogChatHistory(CallbackData, prefix='lgch'):
    chat_id: str
    page: int = 0


class DeleteIncludedRestoreItem(CallbackData, prefix='delinre'):
    index: int


class DeleteIncludedCompleteDeal(CallbackData, prefix='delinco'):
    index: int


class DeleteIncludedBumpItem(CallbackData, prefix='delinbu'):
    index: int


class DeleteExcludedBumpItem(CallbackData, prefix='delexbu'):
    index: int


class SendLogsFile(CallbackData, prefix='selogs'):
    lines: int


class SetNewDelivPiece(CallbackData, prefix='sepiece'):
    val: bool


class DeleteDelivGood(CallbackData, prefix='delgod'):
    index: int


PluginPage = ExtPage
PluginsPagination = ExtPagination
