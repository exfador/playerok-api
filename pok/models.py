from __future__ import annotations
from typing import *
import json
from . import gql as parser
from .defs import *
from .gql import PERSISTED_QUERIES

class FileObject:

    def __init__(self, id: str, url: str, filename: str | None, mime: str | None):
        self.id: str = id
        self.url: str = url
        self.filename: str | None = filename
        self.mime: str | None = mime

class AccountBalance:

    def __init__(self, id: str, value: int, frozen: int, available: int, withdrawable: int, pending_income: int):
        self.id: str = id
        self.value: int = value
        self.frozen: int = frozen
        self.available: int = available
        self.withdrawable: int = withdrawable
        self.pending_income: int = pending_income

class AccountIncomingDealsStats:

    def __init__(self, total: int, finished: int):
        self.total: int = total
        self.finished: int = finished

class AccountOutgoingDealsStats:

    def __init__(self, total: int, finished: int):
        self.total = total
        self.finished = finished

class AccountDealsStats:

    def __init__(self, incoming: AccountIncomingDealsStats, outgoing: AccountOutgoingDealsStats):
        self.incoming: AccountIncomingDealsStats = incoming
        self.outgoing: AccountOutgoingDealsStats = outgoing

class AccountItemsStats:

    def __init__(self, total: int, finished: int):
        self.total: int = total
        self.finished: int = finished

class AccountStats:

    def __init__(self, items: AccountItemsStats, deals: AccountDealsStats):
        self.items: AccountItemsStats = items
        self.deals: AccountDealsStats = deals

class AccountProfile:

    def __init__(self, id: str, username: str, email: str, balance: AccountBalance, stats: AccountStats, role: AccountRole, avatar_url: str, is_online: bool, is_blocked: bool, is_blocked_for: str, is_verified: bool, rating: int, reviews_count: int, created_at: str, support_chat_id: str, system_chat_id: str, has_frozen_balance: bool, has_enabled_notifications: bool, unread_chats_counter: int | None):
        self.id: str = id
        self.username: str = username
        self.email: str = email
        self.balance: AccountBalance = balance
        self.stats: AccountStats = stats
        self.role: AccountRole = role
        self.avatar_url: str = avatar_url
        self.is_online: bool = is_online
        self.is_blocked: bool = is_blocked
        self.is_blocked_for: str = is_blocked_for
        self.is_verified: bool = is_verified
        self.rating: int = rating
        self.reviews_count: int = reviews_count
        self.created_at: str = created_at
        self.support_chat_id: str = support_chat_id
        self.system_chat_id: str = system_chat_id
        self.has_frozen_balance: bool = has_frozen_balance
        self.has_enabled_notifications: bool = has_enabled_notifications
        self.unread_chats_counter: bool | None = unread_chats_counter

class UserProfile:

    def __init__(self, id: str, username: str, role: AccountRole, avatar_url: str, is_online: bool, is_blocked: bool, rating: int, reviews_count: int, support_chat_id: str, system_chat_id: str | None, created_at: str | None):
        self.id: str = id
        self.username: str = username
        self.role: AccountRole = role
        self.avatar_url: str = avatar_url
        self.is_online: bool = is_online
        self.is_blocked: bool = is_blocked
        self.rating: int = rating
        self.reviews_count: int = reviews_count
        self.support_chat_id: str | None = support_chat_id
        self.system_chat_id: str | None = system_chat_id
        self.created_at: str = created_at

    def load_listings(self, count: int=24, game_id: str | None=None, category_id: str | None=None, statuses: list[ListingStage] | None=None, after_cursor: str | None=None) -> ItemProfileList:
        from .client import get_account
        account = get_account()
        headers = {'Accept': '*/*', 'Content-Type': 'application/json', 'Origin': account.base_url}
        filter = {'userId': self.id, 'status': [status.name for status in statuses] if statuses else None}
        if game_id:
            filter['gameId'] = game_id
        elif category_id:
            filter['gameCategoryId'] = category_id
        payload = {'operationName': 'items', 'variables': json.dumps({'pagination': {'first': count, 'after': after_cursor}, 'filter': filter, 'showForbiddenImage': False}), 'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('items')}})}
        r = account.request('get', f'{account.base_url}/graphql', headers, payload).json()
        return parser.item_profile_list(r['data']['items'])

    def get_reviews(self, count: int=24, status: ReviewState=ReviewState.APPROVED, comment_required: bool=False, rating: int | None=None, game_id: str | None=None, category_id: str | None=None, min_item_price: int | None=None, max_item_price: int | None=None, sort_direction: OrderDir=OrderDir.DESC, sort_field: str='createdAt', after_cursor: str | None=None) -> ReviewList:
        from .client import get_account
        account = get_account()
        headers = {'Accept': '*/*', 'Content-Type': 'application/json', 'Origin': account.base_url}
        filters = {'userId': self.id, 'status': [status.name] if status else None}
        if comment_required is not None:
            filters['hasComment'] = comment_required
        if game_id is not None:
            filters['gameId'] = game_id
        if category_id is not None:
            filters['categoryId'] = category_id
        if rating is not None:
            filters['rating'] = rating
        if min_item_price is not None or max_item_price is not None:
            item_price = {}
            if min_item_price is not None:
                item_price['min'] = min_item_price
            if max_item_price is not None:
                item_price['max'] = max_item_price
            filters['itemPrice'] = item_price
        payload = {'operationName': 'testimonials', 'variables': json.dumps({'pagination': {'first': count, 'after': after_cursor}, 'filter': filters, 'sort': {'direction': sort_direction.name if sort_direction else None, 'field': sort_field}}), 'extensions': json.dumps({'persistedQuery': {'version': 1, 'sha256Hash': PERSISTED_QUERIES.get('testimonials')}})}
        r = account.request('get', f'{account.base_url}/graphql', headers, payload).json()
        return parser.review_list(r['data']['testimonials'])

class Event:

    def __init__(self):
        pass

class ItemDeal:

    def __init__(self, id: str, status: DealStage, status_expiration_date: str | None, status_description: str | None, direction: DealFlow, obtaining: str | None, has_problem: bool, report_problem_enabled: bool | None, completed_user: UserProfile | None, props: str | None, previous_status: DealStage | None, completed_at: str, created_at: str, logs: list[ItemLog] | None, transaction: Transaction | None, user: UserProfile, chat: Chat | None, item: Item, review: Review | None, obtaining_fields: list[GameCategoryDataField] | None, comment_from_buyer: str | None):
        self.id: str = id
        self.status: DealStage = status
        self.status_expiration_date: str | None = status_expiration_date
        self.status_description: str | None = status_description
        self.direction: DealFlow = direction
        self.obtaining: str | None = obtaining
        self.has_problem: bool = has_problem
        self.report_problem_enabled: bool | None = report_problem_enabled
        self.completed_user: UserProfile | None = completed_user
        self.props: str | None = props
        self.previous_status: DealStage | None = previous_status
        self.completed_at: str | None = completed_at
        self.created_at: str | None = created_at
        self.logs: list[ItemLog] | None = logs
        self.transaction: Transaction | None = transaction
        self.user: UserProfile = user
        self.chat: Chat | None = chat
        self.item: Item = item
        self.review: Review | None = review
        self.obtaining_fields: list[GameCategoryDataField] | None = obtaining_fields
        self.comment_from_buyer: str | None = comment_from_buyer

class ItemDealPageInfo:

    def __init__(self, start_cursor: str, end_cursor: str, has_previous_page: bool, has_next_page: bool):
        self.start_cursor: str = start_cursor
        self.end_cursor: str = end_cursor
        self.has_previous_page: bool = has_previous_page
        self.has_next_page: bool = has_next_page

class ItemDealList:

    def __init__(self, deals: list[ItemDeal], page_info: ItemDealPageInfo, total_count: int):
        self.deals: list[ItemDeal] = deals
        self.page_info: ItemDealPageInfo = page_info
        self.total_count: int = total_count

class GameCategoryAgreement:

    def __init__(self, id: str, description: str, icontype: GameCategoryAgreementIconTypes, sequence: int):
        self.id: str = id
        self.description: str = description
        self.icontype: GameCategoryAgreementIconTypes = icontype
        self.sequence: str = sequence

class GameCategoryAgreementPageInfo:

    def __init__(self, start_cursor: str, end_cursor: str, has_previous_page: bool, has_next_page: bool):
        self.start_cursor: str = start_cursor
        self.end_cursor: str = end_cursor
        self.has_previous_page: bool = has_previous_page
        self.has_next_page: bool = has_next_page

class GameCategoryAgreementList:

    def __init__(self, agreements: list[GameCategoryAgreement], page_info: GameCategoryAgreementPageInfo, total_count: int):
        self.agreements: list[GameCategoryAgreement] = agreements
        self.page_info: GameCategoryAgreementPageInfo = page_info
        self.total_count: int = total_count

class GameCategoryObtainingType:

    def __init__(self, id: str, name: str, description: str, game_category_id: str, no_comment_from_buyer: bool, instruction_for_buyer: str | None, instruction_for_seller: str | None, sequence: int, fee_multiplier: float, agreements: list[GameCategoryAgreement], props: GameCategoryProps):
        self.id: str = id
        self.name: str = name
        self.description: str = description
        self.game_category_id: str = game_category_id
        self.no_comment_from_buyer: bool = no_comment_from_buyer
        self.instruction_for_buyer: str | None = instruction_for_buyer
        self.instruction_for_seller: str | None = instruction_for_seller
        self.sequence: int = sequence
        self.fee_multiplier: float = fee_multiplier
        self.agreements: list[GameCategoryAgreement] = agreements
        self.props: GameCategoryProps = props

class GameCategoryObtainingTypePageInfo:

    def __init__(self, start_cursor: str, end_cursor: str, has_previous_page: bool, has_next_page: bool):
        self.start_cursor: str = start_cursor
        self.end_cursor: str = end_cursor
        self.has_previous_page: bool = has_previous_page
        self.has_next_page: bool = has_next_page

class GameCategoryObtainingTypeList:

    def __init__(self, obtaining_types: list[GameCategoryObtainingType], page_info: GameCategoryObtainingTypePageInfo, total_count: int):
        self.obtaining_types: list[GameCategoryObtainingType] = obtaining_types
        self.page_info: GameCategoryAgreementPageInfo = page_info
        self.total_count: int = total_count

class GameCategoryDataField:

    def __init__(self, id: str, label: str, type: FieldScope, input_type: GameCategoryDataFieldInputTypes, copyable: bool, hidden: bool, required: bool, value: str | None):
        self.id: str = id
        self.label: str = label
        self.type: FieldScope = type
        self.input_type: GameCategoryDataFieldInputTypes = input_type
        self.copyable: bool = copyable
        self.hidden: bool = hidden
        self.required: bool = required
        self.value: str | None = value

class GameCategoryDataFieldPageInfo:

    def __init__(self, start_cursor: str, end_cursor: str, has_previous_page: bool, has_next_page: bool):
        self.start_cursor: str = start_cursor
        self.end_cursor: str = end_cursor
        self.has_previous_page: bool = has_previous_page
        self.has_next_page: bool = has_next_page

class GameCategoryDataFieldList:

    def __init__(self, data_fields: list[GameCategoryDataField], page_info: GameCategoryDataFieldPageInfo, total_count: int):
        self.data_fields: list[GameCategoryDataField] = data_fields
        self.page_info: GameCategoryDataFieldPageInfo = page_info
        self.total_count: int = total_count

class GameCategoryProps:

    def __init__(self, min_reviews: int, min_reviews_for_seller: int):
        self.min_reviews: int = min_reviews
        self.min_reviews_for_seller: int = min_reviews_for_seller

class GameCategoryOption:

    def __init__(self, id: str, group: str, label: str, type: OptionStyle, field: str, value: str, value_range_limit: int | None):
        self.id: str = id
        self.group: str = group
        self.label: str = label
        self.type: OptionStyle = type
        self.field: str = field
        self.value: str = value
        self.value_range_limit: int | None = value_range_limit

class GameCategoryInstruction:

    def __init__(self, id: str, text: str):
        self.id: str = id
        self.text: str = text

class GameCategoryInstructionPageInfo:

    def __init__(self, start_cursor: str, end_cursor: str, has_previous_page: bool, has_next_page: bool):
        self.start_cursor: str = start_cursor
        self.end_cursor: str = end_cursor
        self.has_previous_page: bool = has_previous_page
        self.has_next_page: bool = has_next_page

class GameCategoryInstructionList:

    def __init__(self, instructions: list[GameCategoryInstruction], page_info: GameCategoryInstructionPageInfo, total_count: int):
        self.instructions: list[GameCategoryInstruction] = instructions
        self.page_info: GameCategoryInstructionPageInfo = page_info
        self.total_count: int = total_count

class GameCategory:

    def __init__(self, id: str, slug: str, name: str, category_id: str | None, game_id: str | None, obtaining: str | None, options: list[GameCategoryOption] | None, props: GameCategoryProps | None, no_comment_from_buyer: bool | None, instruction_for_buyer: str | None, instruction_for_seller: str | None, use_custom_obtaining: bool, auto_confirm_period: GameCategoryAutoConfirmPeriods | None, auto_moderation_mode: bool | None, agreements: list[GameCategoryAgreement] | None, fee_multiplier: float | None):
        self.id: str = id
        self.slug: str = slug
        self.name: str = name
        self.category_id: str | None = category_id
        self.game_id: str | None = game_id
        self.obtaining: str | None = obtaining
        self.options: list[GameCategoryOption] | None = options
        self.props: str | None = props
        self.no_comment_from_buyer: bool | None = no_comment_from_buyer
        self.instruction_for_buyer: str | None = instruction_for_buyer
        self.instruction_for_seller: str | None = instruction_for_seller
        self.use_custom_obtaining: bool = use_custom_obtaining
        self.auto_confirm_period: GameCategoryAutoConfirmPeriods | None = auto_confirm_period
        self.auto_moderation_mode: bool | None = auto_moderation_mode
        self.agreements: list[GameCategoryAgreement] | None = agreements
        self.fee_multiplier: float | None = fee_multiplier

class Game:

    def __init__(self, id: str, slug: str, name: str, type: GameTypes, logo: FileObject, banner: FileObject, categories: list[GameCategory], created_at: str):
        self.id: str = id
        self.slug: str = slug
        self.name: str = name
        self.type: GameTypes = type
        self.logo: FileObject = logo
        self.banner: FileObject = banner
        self.categories: list[GameCategory] = categories
        self.created_at: str = created_at

class GameProfile:

    def __init__(self, id: str, slug: str, name: str, type: GameTypes, logo: FileObject):
        self.id: str = id
        self.slug: str = slug
        self.name: str = name
        self.type: GameTypes = id
        self.logo: FileObject = logo

class GamePageInfo:

    def __init__(self, start_cursor: str, end_cursor: str, has_previous_page: bool, has_next_page: bool):
        self.start_cursor: str = start_cursor
        self.end_cursor: str = end_cursor
        self.has_previous_page: bool = has_previous_page
        self.has_next_page: bool = has_next_page

class GameList:

    def __init__(self, games: list[Game], page_info: GamePageInfo, total_count: int):
        self.games: list[Game] = games
        self.page_info: ChatPageInfo = page_info
        self.total_count: int = total_count

class ItemPriorityStatusPriceRange:

    def __init__(self, min: int, max: str):
        self.min: int = min
        self.max: int = max

class ItemPriorityStatus:

    def __init__(self, id: str, price: int, name: str, type: BoostLevel, period: int, price_range: ItemPriorityStatusPriceRange):
        self.id: str = id
        self.price: int = price
        self.name: str = name
        self.type: BoostLevel = type
        self.period: int = period
        self.price_range: ItemPriorityStatusPriceRange = price_range

class ItemLog:

    def __init__(self, id: str, event: ItemLogEvents, created_at: str, user: UserProfile):
        self.id: str = id
        self.event: ItemLogEvents = event
        self.created_at: str = created_at
        self.user: UserProfile = user

class Item:

    def __init__(self, id: str, slug: str, name: str, description: str, obtaining_type: GameCategoryObtainingType | None, price: int, raw_price: int, priority_position: int, attachments: list[FileObject], attributes: dict, category: GameCategory, comment: str | None, data_fields: list[GameCategoryDataField] | None, fee_multiplier: float, game: GameProfile, seller_type: AccountRole, status: ListingStage, user: UserProfile):
        self.id: str = id
        self.slug: str = slug
        self.name: str = name
        self.description: str = description
        self.obtaining_type: GameCategoryObtainingType | None = obtaining_type
        self.price: int = price
        self.raw_price: int = raw_price
        self.priority_position: int = priority_position
        self.attachments: list[FileObject] = attachments
        self.attributes: dict = attributes
        self.category: GameCategory = category
        self.comment: str | None = comment
        self.data_fields: list[GameCategoryDataField] | None = data_fields
        self.fee_multiplier: float = fee_multiplier
        self.game: GameProfile = game
        self.seller_type: AccountRole = seller_type
        self.slug: str = slug
        self.status: ListingStage = status
        self.user: UserProfile = user

class MyItem:

    def __init__(self, id: str, slug: str, name: str, description: str, obtaining_type: GameCategoryObtainingType | None, price: int, raw_price: int, priority_position: int, attachments: list[FileObject], attributes: dict, buyer: UserProfile, category: GameCategory, comment: str | None, data_fields: list[GameCategoryDataField] | None, fee_multiplier: float, game: GameProfile, seller_type: AccountRole, status: ListingStage, user: UserProfile, prev_price: int, prev_fee_multiplier: float, seller_notified_about_fee_change: bool, priority: BoostLevel, priority_price: int, sequence: int | None, status_expiration_date: str | None, status_description: str | None, status_payment: Transaction | None, views_counter: int, is_editable: bool, approval_date: str | None, deleted_at: str | None, updated_at: str | None, created_at: str | None):
        self.id: str = id
        self.slug: str = slug
        self.name: str = name
        self.status: ListingStage = status
        self.description: str = description
        self.obtaining_type: GameCategoryObtainingType | None = obtaining_type
        self.price: int = price
        self.prev_price: int = prev_price
        self.raw_price: int = raw_price
        self.priority_position: int = priority_position
        self.attachments: list[FileObject] = attachments
        self.attributes: dict = attributes
        self.category: GameCategory = category
        self.comment: str | None = comment
        self.data_fields: list[GameCategoryDataField] | None = data_fields
        self.fee_multiplier: float = fee_multiplier
        self.prev_fee_multiplier: float = prev_fee_multiplier
        self.seller_notified_about_fee_change: bool = seller_notified_about_fee_change
        self.game: GameProfile = game
        self.seller_type: AccountRole = seller_type
        self.user: UserProfile = user
        self.buyer: UserProfile = buyer
        self.priority: BoostLevel = priority
        self.priority_price: int = priority_price
        self.sequence: int | None = sequence
        self.status_expiration_date: str | None = status_expiration_date
        self.status_description: str | None = status_description
        self.status_payment: str | None = status_payment
        self.views_counter: int = views_counter
        self.is_editable: bool = is_editable
        self.approval_date: str | None = approval_date
        self.deleted_at: str | None = deleted_at
        self.updated_at: str | None = updated_at
        self.created_at: str | None = created_at

class ItemProfile:

    def __init__(self, id: str, slug: str, priority: BoostLevel, status: ListingStage, name: str, price: int, raw_price: int, seller_type: AccountRole, attachment: FileObject, user: UserProfile, approval_date: str, priority_position: int, views_counter: int | None, fee_multiplier: float, created_at: str):
        self.id: str = id
        self.slug: str = slug
        self.priority: BoostLevel = priority
        self.status: ListingStage = status
        self.name: str = name
        self.price: int = price
        self.raw_price: int = raw_price
        self.seller_type: AccountRole = seller_type
        self.attachment: FileObject = attachment
        self.user: UserProfile = user
        self.approval_date: str = approval_date
        self.priority_position: int = priority_position
        self.views_counter: int | None = views_counter
        self.fee_multiplier: float = fee_multiplier
        self.created_at: str = created_at

class ItemProfilePageInfo:

    def __init__(self, start_cursor: str, end_cursor: str, has_previous_page: bool, has_next_page: bool):
        self.start_cursor: str = start_cursor
        self.end_cursor: str = end_cursor
        self.has_previous_page: bool = has_previous_page
        self.has_next_page: bool = has_next_page

class ItemProfileList:

    def __init__(self, items: list[ItemProfile], page_info: ItemProfilePageInfo, total_count: int):
        self.items: list[ItemProfile] = items
        self.page_info: ItemProfilePageInfo = page_info
        self.total_count: int = total_count

class SBPBankMember:

    def __init__(self, id: str, name: str, icon: str):
        self.id: str = id
        self.name: str = name
        self.icon: str = icon

class TransactionPaymentMethod:

    def __init__(self, id: PayMethod, name: str, fee: int, provider_id: PayGateway, account: AccountProfile | None, props: TransactionProviderProps, limits: TransactionProviderLimits):
        self.id: PayMethod = id
        self.name: str = name
        self.fee: int = fee
        self.provider_id: PayGateway = provider_id
        self.account: AccountProfile | None = account
        self.props: TransactionProviderProps = props
        self.limits: TransactionProviderLimits = limits

class TransactionProviderLimitRange:

    def __init__(self, min: int, max: int):
        self.min: int = min
        self.max: int = max

class TransactionProviderLimits:

    def __init__(self, incoming: TransactionProviderLimitRange, outgoing: TransactionProviderLimitRange):
        self.incoming: TransactionProviderLimitRange = incoming
        self.outgoing: TransactionProviderLimitRange = outgoing

class TransactionProviderRequiredUserData:

    def __init__(self, email: bool, phone_number: bool, erip_account_number: bool | None):
        self.email: bool = email
        self.phone_number: bool = phone_number
        self.erip_account_number: bool | None = erip_account_number

class TransactionProviderProps:

    def __init__(self, required_user_data: TransactionProviderRequiredUserData, tooltip: str | None):
        self.required_user_data: TransactionProviderRequiredUserData = required_user_data
        self.tooltip: str | None = tooltip

class TransactionProvider:

    def __init__(self, id: PayGateway, name: str, fee: int, min_fee_amount: int | None, description: str | None, account: AccountProfile | None, props: TransactionProviderProps, limits: TransactionProviderLimits, payment_methods: list[TransactionPaymentMethod]):
        self.id: PayGateway = id
        self.name: str = name
        self.fee: int = fee
        self.min_fee_amount: int | None = min_fee_amount
        self.description: str | None = description
        self.account: AccountProfile | None = account
        self.props: TransactionProviderProps = props
        self.limits: TransactionProviderLimits = limits
        self.payment_methods: list[TransactionPaymentMethod] = payment_methods

class Transaction:

    def __init__(self, id: str, operation: TxKind, direction: TransactionDirections, provider_id: PayGateway, provider: TransactionProvider, user: UserProfile, creator: UserProfile, status: TxStage, status_description: str | None, status_expiration_date: str | None, value: int, fee: int, created_at: str, verified_at: str | None, verified_by: UserProfile | None, completed_at: str | None, completed_by: UserProfile | None, payment_method_id: str | None, is_suspicious: bool | None, sbp_bank_name: str | None):
        self.id: str = id
        self.operation: TxKind = operation
        self.direction: TransactionDirections = direction
        self.provider_id: PayGateway = provider_id
        self.provider: TransactionProvider = provider
        self.user: UserProfile = user
        self.creator: UserProfile | None = creator
        self.status: TxStage = status
        self.status_description: str | None = status_description
        self.status_expiration_date: str | None = status_expiration_date
        self.value: int = value
        self.fee: int = fee
        self.created_at: str = created_at
        self.verified_at: str | None = verified_at
        self.verified_by: UserProfile | None = verified_by
        self.completed_at: str | None = completed_at
        self.completed_by: UserProfile | None = completed_by
        self.payment_method_id: str | None = payment_method_id
        self.is_suspicious: bool | None = is_suspicious
        self.sbp_bank_name: str | None = sbp_bank_name

class TransactionPageInfo:

    def __init__(self, start_cursor: str, end_cursor: str, has_previous_page: bool, has_next_page: bool):
        self.start_cursor: str = start_cursor
        self.end_cursor: str = end_cursor
        self.has_previous_page: bool = has_previous_page
        self.has_next_page: bool = has_next_page

class TransactionList:

    def __init__(self, transactions: list[Transaction], page_info: TransactionPageInfo, total_count: int):
        self.transactions: list[Transaction] = transactions
        self.page_info: TransactionPageInfo = page_info
        self.total_count: int = total_count

class UserBankCard:

    def __init__(self, id: str, card_first_six: str, card_last_four: str, card_type: BankCardTypes, is_chosen: bool):
        self.id: str = id
        self.card_first_six: str = card_first_six
        self.card_last_four: str = card_last_four
        self.card_type: BankCardTypes = card_type
        self.is_chosen: bool = is_chosen

class UserBankCardPageInfo:

    def __init__(self, start_cursor: str, end_cursor: str, has_previous_page: bool, has_next_page: bool):
        self.start_cursor: str = start_cursor
        self.end_cursor: str = end_cursor
        self.has_previous_page: bool = has_previous_page
        self.has_next_page: bool = has_next_page

class UserBankCardList:

    def __init__(self, bank_cards: list[UserBankCard], page_info: UserBankCardPageInfo, total_count: int):
        self.bank_cards: list[UserBankCard] = bank_cards
        self.page_info: UserBankCardPageInfo = page_info
        self.total_count: int = total_count

class Moderator:

    def __init__(self):
        pass

class ChatMessageButton:

    def __init__(self, type: ChatMessageButtonTypes, url: str | None, text: str):
        self.type: ChatMessageButtonTypes = type
        self.url: str | None = url
        self.text: str = text

class ChatMessage:

    def __init__(self, id: str, text: str, created_at: str, deleted_at: str | None, is_read: bool, is_suspicious: bool, is_bulk_messaging: bool, game: Game | None, file: FileObject | None, images: list[FileObject] | None, user: UserProfile, deal: ItemDeal | None, item: ItemProfile | None, transaction: Transaction | None, moderator: Moderator | None, event_by_user: UserProfile | None, event_to_user: UserProfile | None, is_auto_response: bool, event: Event | None, buttons: list[ChatMessageButton]):
        self.id: str = id
        self.text: str = text
        self.created_at: str = created_at
        self.deleted_at: str | None = deleted_at
        self.is_read: bool = is_read
        self.is_suspicious: bool = is_suspicious
        self.is_bulk_messaging: bool = is_bulk_messaging
        self.game: Game | None = game
        self.file: FileObject | None = file
        self.images: list[FileObject] = images or []
        self.user: UserProfile = user
        self.deal: ItemDeal | None = deal
        self.item: ItemProfile | None = item
        self.transaction: Transaction | None = transaction
        self.moderator: Moderator = moderator
        self.event_by_user: UserProfile | None = event_by_user
        self.event_to_user: UserProfile | None = event_to_user
        self.is_auto_response: bool = is_auto_response
        self.event: Event | None = event
        self.buttons: list[ChatMessageButton] = buttons

class ChatMessagePageInfo:

    def __init__(self, start_cursor: str, end_cursor: str, has_previous_page: bool, has_next_page: bool):
        self.start_cursor: str = start_cursor
        self.end_cursor: str = end_cursor
        self.has_previous_page: bool = has_previous_page
        self.has_next_page: bool = has_next_page

class ChatMessageList:

    def __init__(self, messages: list[ChatMessage], page_info: ChatMessagePageInfo, total_count: int):
        self.messages: list[ChatMessage] = messages
        self.page_info: ChatMessagePageInfo = page_info
        self.total_count: int = total_count

class Chat:

    def __init__(self, id: str, type: RoomKind, status: RoomState | None, unread_messages_counter: int, bookmarked: bool | None, is_texting_allowed: bool | None, owner: UserProfile | None, deals: list[ItemDeal] | None, started_at: str | None, finished_at: str | None, last_message: ChatMessage | None, users: list[UserProfile]):
        self.id: str = id
        self.type: RoomKind = type
        self.status: RoomState | None = status
        self.unread_messages_counter: int = unread_messages_counter
        self.bookmarked: bool | None = bookmarked
        self.is_texting_allowed: bool | None = is_texting_allowed
        self.owner: UserProfile = owner
        self.deals: list[ItemDeal] | None = deals
        self.last_message: ChatMessage | None = last_message
        self.users: list[UserProfile] = users
        self.started_at: str | None = started_at
        self.finished_at: str | None = finished_at

class ChatPageInfo:

    def __init__(self, start_cursor: str, end_cursor: str, has_previous_page: bool, has_next_page: bool):
        self.start_cursor: str = start_cursor
        self.end_cursor: str = end_cursor
        self.has_previous_page: bool = has_previous_page
        self.has_next_page: bool = has_next_page

class ChatList:

    def __init__(self, chats: list[Chat], page_info: ChatPageInfo, total_count: int):
        self.chats: list[Chat] = chats
        self.page_info: ChatPageInfo = page_info
        self.total_count: int = total_count

class Review:

    def __init__(self, id: str, status: ReviewState, text: str | None, rating: int, created_at: str, updated_at: str, deal: ItemDeal, creator: UserProfile, moderator: Moderator | None, user: UserProfile):
        self.id: str = id
        self.status: ReviewState = status
        self.text: str | None = text
        self.rating: int = rating
        self.created_at: str = created_at
        self.updated_at: str = updated_at
        self.deal: ItemDeal = deal
        self.creator: UserProfile = creator
        self.moderator: Moderator | None = moderator
        self.user: UserProfile = user

class ReviewPageInfo:

    def __init__(self, start_cursor: str, end_cursor: str, has_previous_page: bool, has_next_page: bool):
        self.start_cursor: str = start_cursor
        self.end_cursor: str = end_cursor
        self.has_previous_page: bool = has_previous_page
        self.has_next_page: bool = has_next_page

class ReviewList:

    def __init__(self, reviews: list[Review], page_info: ReviewPageInfo, total_count: int):
        self.reviews: list[Review] = reviews
        self.page_info: ReviewPageInfo = page_info
        self.total_count: int = total_count
