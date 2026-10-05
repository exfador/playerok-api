from .contract import PERSISTED_QUERIES as PERSISTED_QUERIES
from .contract import QUERIES as QUERIES
from .response import enrich_response, image_rows, message_event
from typing import TYPE_CHECKING
from .defs import *
if TYPE_CHECKING:
    from .models import *

def decode_account_profile(data: dict) -> 'AccountProfile':
    from .models import AccountProfile
    if not data:
        return None
    profile: dict = data.get('profile') or {}
    return AccountProfile(id=data.get('id'), username=profile.get('username'), email=data.get('email'), balance=decode_account_balance(data.get('balance')), stats=decode_account_stats(data.get('stats')), role=AccountRole.__members__.get(data.get('role')), avatar_url=profile.get('avatarURL'), is_online=profile.get('isOnline'), is_blocked=data.get('isBlocked'), is_blocked_for=data.get('isBlockedFor'), is_verified=data.get('isVerified'), rating=profile.get('rating'), reviews_count=profile.get('testimonialCounter'), created_at=profile.get('createdAt'), support_chat_id=profile.get('supportChatId'), system_chat_id=profile.get('systemChatId'), has_frozen_balance=data.get('hasFrozenBalance'), has_enabled_notifications=data.get('hasEnabledNotifications'), unread_chats_counter=data.get('unreadChatsCounter'))

def decode_account_stats(data: dict) -> 'AccountStats':
    from .models import AccountStats
    if not data:
        return None
    items = decode_account_items_stats(data.get('items'))
    deals = decode_account_deals_stats(data.get('deals'))
    return AccountStats(items=items, deals=deals)

def decode_account_balance(data: dict) -> 'AccountBalance':
    from .models import AccountBalance
    if not data:
        return None
    return AccountBalance(id=data.get('id'), value=data.get('value'), frozen=data.get('frozen'), available=data.get('available'), withdrawable=data.get('withdrawable'), pending_income=data.get('pendingIncome'))

def decode_account_deals_stats(data: dict) -> 'AccountDealsStats':
    from .models import AccountDealsStats
    if not data:
        return None
    return AccountDealsStats(incoming=decode_account_incoming_deals_stats(data.get('incoming')), outgoing=decode_account_outgoing_deals_stats(data.get('outgoing')))

def decode_account_incoming_deals_stats(data: dict) -> 'AccountIncomingDealsStats':
    from .models import AccountIncomingDealsStats
    if not data:
        return None
    return AccountIncomingDealsStats(total=data.get('total'), finished=data.get('finished'))

def decode_account_outgoing_deals_stats(data: dict) -> 'AccountOutgoingDealsStats':
    from .models import AccountOutgoingDealsStats
    if not data:
        return None
    return AccountOutgoingDealsStats(total=data.get('total'), finished=data.get('finished'))

def decode_account_items_stats(data: dict) -> 'AccountItemsStats':
    from .models import AccountItemsStats
    if not data:
        return None
    return AccountItemsStats(total=data.get('total'), finished=data.get('finished'))

def decode_item_deal(data: dict) -> 'ItemDeal':
    from .models import ItemDeal
    if not data:
        return None
    logs = []
    data_logs: dict[dict] = data.get('logs')
    if data_logs:
        for log in data_logs:
            logs.append(decode_item_log(log))
    obtaining_fields = []
    data_obtaining_fields = data.get('obtainingFields')
    if data_obtaining_fields:
        for field in data_obtaining_fields:
            obtaining_fields.append(decode_category_data_field(field))
    item_data = data.get('item')
    deal_item = decode_my_item(item_data) if isinstance(item_data, dict) and item_data.get('__typename') == 'MyItem' else decode_item(item_data)
    return enrich_response(ItemDeal(id=data.get('id'), status=DealStage.__members__.get(data.get('status')), status_expiration_date=data.get('statusExpirationDate'), status_description=data.get('statusDescription'), direction=DealFlow.__members__.get(data.get('direction')), obtaining=data.get('obtaining'), has_problem=data.get('hasProblem'), report_problem_enabled=data.get('reportProblemEnabled'), completed_user=decode_user_profile(data.get('completedBy')), props=data.get('props'), previous_status=DealStage.__members__.get(data.get('prevStatus')), completed_at=data.get('completedAt'), created_at=data.get('createdAt'), logs=logs, transaction=decode_transaction(data.get('transaction')), user=decode_user_profile(data.get('user')), chat=decode_chat(data.get('chat')), item=deal_item, review=decode_review(data.get('testimonial')), obtaining_fields=obtaining_fields, comment_from_buyer=data.get('commentFromBuyer')), data)

def decode_item_deal_page_info(data: dict) -> 'ItemDealPageInfo':
    from .models import ItemDealPageInfo
    if not data:
        return None
    return ItemDealPageInfo(start_cursor=data.get('startCursor'), end_cursor=data.get('endCursor'), has_previous_page=data.get('hasPreviousPage'), has_next_page=data.get('hasNextPage'))

def decode_item_deal_list(data: dict) -> 'ItemDealList':
    from .models import ItemDealList
    if not data:
        return None
    deals = []
    edges: list[dict] = data.get('edges')
    if edges:
        for edge in edges:
            deals.append(decode_item_deal(edge.get('node')))
    return ItemDealList(deals=deals, page_info=decode_item_deal_page_info(data.get('pageInfo')), total_count=data.get('totalCount'))

def decode_item(data: dict) -> 'Item':
    from .models import Item
    if not data:
        return None
    attachments = []
    data_attachments = data.get('attachments')
    if data_attachments:
        for att in data_attachments:
            attachments.append(decode_file_object(att))
    data_fields = []
    data_data_fields = data.get('dataFields')
    if data_data_fields:
        for field in data_data_fields:
            data_fields.append(decode_category_data_field(field))
    return enrich_response(Item(id=data.get('id'), slug=data.get('slug'), name=data.get('name'), description=data.get('description'), obtaining_type=decode_category_obtaining_type(data.get('obtainingType')), price=data.get('price'), raw_price=data.get('rawPrice'), priority_position=data.get('priorityPosition'), attachments=attachments, attributes=data.get('attributes'), category=decode_game_category(data.get('category')), comment=data.get('comment'), data_fields=data_fields, fee_multiplier=data.get('feeMultiplier'), game=decode_game_profile(data.get('game')), seller_type=data.get('sellerType'), status=ListingStage.__members__.get(data.get('status')), user=decode_user_profile(data.get('user'))), data)

def decode_my_item(data: dict) -> 'MyItem':
    from .models import MyItem
    if not data:
        return None
    attachments = []
    data_attachments = data.get('attachments')
    if data_attachments:
        for att in data_attachments:
            attachments.append(decode_file_object(att))
    data_fields = []
    data_data_fields = data.get('dataFields')
    if data_data_fields:
        for field in data_data_fields:
            data_fields.append(decode_category_data_field(field))
    return enrich_response(MyItem(id=data.get('id'), slug=data.get('slug'), name=data.get('name'), description=data.get('description'), obtaining_type=decode_category_obtaining_type(data.get('obtainingType')), price=data.get('price'), prev_price=data.get('prevPrice'), raw_price=data.get('rawPrice'), priority_position=data.get('priorityPosition'), attachments=attachments, attributes=data.get('attributes'), buyer=decode_user_profile(data.get('buyer')), category=decode_game_category(data.get('category')), comment=data.get('comment'), data_fields=data_fields, fee_multiplier=data.get('feeMultiplier'), prev_fee_multiplier=data.get('prevFeeMultiplier'), seller_notified_about_fee_change=data.get('sellerNotifiedAboutFeeChange'), game=decode_game_profile(data.get('game')), seller_type=data.get('sellerType'), status=ListingStage.__members__.get(data.get('status')), user=decode_user_profile(data.get('user')), priority=BoostLevel.__members__.get(data.get('priority')), priority_price=data.get('priorityPrice'), sequence=data.get('sequence'), status_expiration_date=data.get('statusExpirationDate'), status_description=data.get('statusDescription'), status_payment=decode_transaction(data.get('statusPayment')), views_counter=data.get('viewsCounter'), is_editable=data.get('isEditable'), approval_date=data.get('approvalDate'), deleted_at=data.get('deletedAt'), updated_at=data.get('updatedAt'), created_at=data.get('createdAt')), data)

def decode_item_profile(data: dict) -> 'ItemProfile':
    from .models import ItemProfile
    if not data:
        return None
    return enrich_response(ItemProfile(id=data.get('id'), slug=data.get('slug'), priority=BoostLevel.__members__.get(data.get('priority')), status=ListingStage.__members__.get(data.get('status')), name=data.get('name'), price=data.get('price'), raw_price=data.get('rawPrice'), seller_type=AccountRole.__members__.get(data.get('sellerType')), attachment=decode_file_object(data.get('attachment')), user=decode_user_profile(data.get('user')), approval_date=data.get('approvalDate'), priority_position=data.get('priorityPosition'), views_counter=data.get('viewsCounter'), fee_multiplier=data.get('feeMultiplier'), created_at=data.get('createdAt')), data)

def decode_item_profile_page_info(data: dict) -> 'ItemProfilePageInfo':
    from .models import ItemProfilePageInfo
    if not data:
        return None
    return ItemProfilePageInfo(start_cursor=data.get('startCursor'), end_cursor=data.get('endCursor'), has_previous_page=data.get('hasPreviousPage'), has_next_page=data.get('hasNextPage'))

def decode_item_profile_list(data: dict) -> 'ItemProfileList':
    from .models import ItemProfileList
    if not data:
        return None
    items = []
    edges: list[dict] = data.get('edges')
    if edges:
        for edge in edges:
            items.append(decode_item_profile(edge.get('node')))
    return ItemProfileList(items=items, page_info=decode_item_profile_page_info(data.get('pageInfo')), total_count=data.get('totalCount'))

def decode_item_priority_status(data: dict) -> 'ItemPriorityStatus':
    from .models import ItemPriorityStatus
    if not data:
        return None
    return ItemPriorityStatus(id=data.get('id'), price=data.get('price'), name=data.get('name'), type=BoostLevel.__members__.get(data.get('type')), period=data.get('period'), price_range=decode_item_priority_status_price_range(data.get('priceRange')))

def decode_item_priority_status_price_range(data: dict) -> 'ItemPriorityStatusPriceRange':
    from .models import ItemPriorityStatusPriceRange
    if not data:
        return None
    return ItemPriorityStatusPriceRange(min=data.get('min'), max=data.get('max'))

def decode_item_log(data: dict) -> 'ItemLog':
    from .models import ItemLog
    if not data:
        return None
    return ItemLog(id=data.get('id'), event=ItemLogEvents.__members__.get(data.get('event')), created_at=data.get('createdAt'), user=decode_user_profile(data.get('user')))

def decode_chat_message(data: dict) -> 'ChatMessage':
    from .models import ChatMessage
    if not data:
        return None
    btns = []
    data_btns = data.get('buttons')
    if data_btns:
        for btn in data_btns:
            btns.append(decode_chat_message_button(btn))
    imgs: list = []
    for row in image_rows(data):
        if row:
            fo = decode_file_object(row)
            if fo:
                imgs.append(fo)
    return enrich_response(ChatMessage(id=data.get('id'), text=data.get('text'), created_at=data.get('createdAt'), deleted_at=data.get('deletedAt'), is_read=data.get('isRead'), is_suspicious=data.get('isSuspicious'), is_bulk_messaging=data.get('isBulkMessaging'), file=decode_file_object(data.get('file')), game=decode_game(data.get('game')), images=imgs, user=decode_user_profile(data.get('user')), deal=decode_item_deal(data.get('deal')), item=decode_item(data.get('item')), transaction=decode_transaction(data.get('transaction')), moderator=decode_moderator(data.get('moderator')), event=decode_stream_event(data.get('event')), event_by_user=decode_user_profile(data.get('eventByUser')), event_to_user=decode_user_profile(data.get('eventToUser')), is_auto_response=data.get('isAutoResponse'), buttons=btns), data)

def decode_chat_message_button(data: dict) -> 'ChatMessageButton':
    from .models import ChatMessageButton
    if not data:
        return None
    return ChatMessageButton(type=ChatMessageButtonTypes.__members__.get(data.get('type')), url=data.get('url'), text=data.get('text'))

def decode_chat_message_page_info(data: dict) -> 'ChatMessagePageInfo':
    from .models import ChatMessagePageInfo
    if not data:
        return None
    return ChatMessagePageInfo(start_cursor=data.get('startCursor'), end_cursor=data.get('endCursor'), has_previous_page=data.get('hasPreviousPage'), has_next_page=data.get('hasNextPage'))

def decode_chat_message_list(data: dict) -> 'ChatMessageList':
    from .models import ChatMessageList
    if not data:
        return None
    messages = []
    edges: list[dict] = data.get('edges')
    if edges:
        for edge in edges:
            messages.append(decode_chat_message(edge.get('node')))
    return ChatMessageList(messages=messages, page_info=decode_chat_message_page_info(data.get('pageInfo')), total_count=data.get('totalCount'))

def decode_chat(data: dict) -> 'Chat':
    from .models import Chat
    if not data:
        return None
    users = []
    data_users = data.get('participants')
    if data_users:
        for user in data_users:
            users.append(decode_user_profile(user))
    deals = []
    data_deals = data.get('deals')
    if data_deals:
        for deal in data_deals:
            deals.append(decode_item_deal(deal))
    return Chat(id=data.get('id'), type=RoomKind.__members__.get(data.get('type')), status=RoomState.__members__.get(data.get('status')), unread_messages_counter=data.get('unreadMessagesCounter'), bookmarked=data.get('bookmarked'), is_texting_allowed=data.get('isTextingAllowed'), owner=decode_user_profile(data.get('owner')), deals=deals, started_at=data.get('startedAt'), finished_at=data.get('finishedAt'), last_message=decode_chat_message(data.get('lastMessage')), users=users)

def decode_chat_page_info(data: dict) -> 'ChatPageInfo':
    from .models import ChatPageInfo
    if not data:
        return None
    return ChatPageInfo(start_cursor=data.get('startCursor'), end_cursor=data.get('endCursor'), has_previous_page=data.get('hasPreviousPage'), has_next_page=data.get('hasNextPage'))

def decode_chat_list(data: dict) -> 'ChatList':
    from .models import ChatList
    if not data:
        return None
    chats = []
    edges: list[dict] = data.get('edges')
    if edges:
        for edge in edges:
            chats.append(decode_chat(edge.get('node')))
    return ChatList(chats=chats, page_info=decode_chat_page_info(data.get('pageInfo')), total_count=data.get('totalCount'))

def decode_review(data: dict) -> 'Review':
    from .models import Review
    if not data:
        return None
    return Review(id=data.get('id'), status=ReviewState.__members__.get(data.get('status')), text=data.get('text'), rating=data.get('rating'), created_at=data.get('createdAt'), updated_at=data.get('updatedAt'), deal=decode_item_deal(data.get('deal')), creator=decode_user_profile(data.get('creator')), moderator=decode_moderator(data.get('moderator')), user=decode_user_profile(data.get('user')))

def decode_review_page_info(data: dict) -> 'ReviewPageInfo':
    from .models import ReviewPageInfo
    if not data:
        return None
    return ReviewPageInfo(start_cursor=data.get('startCursor'), end_cursor=data.get('endCursor'), has_previous_page=data.get('hasPreviousPage'), has_next_page=data.get('hasNextPage'))

def decode_review_list(data: dict) -> 'ReviewList':
    from .models import ReviewList
    if not data:
        return None
    reviews = []
    edges: list[dict] = data.get('edges')
    if edges:
        for edge in edges:
            reviews.append(decode_review(edge.get('node')))
    return ReviewList(reviews=reviews, page_info=decode_review_page_info(data.get('pageInfo')), total_count=data.get('totalCount'))

def decode_game(data: dict) -> 'Game':
    from .models import Game
    if not data:
        return None
    cats = []
    data_cats = data.get('categories')
    if data_cats:
        for cat in data_cats:
            cats.append(decode_game_category(cat))
    return Game(id=data.get('id'), slug=data.get('slug'), name=data.get('name'), type=GameTypes.__members__.get(data.get('type')), logo=decode_file_object(data.get('logo')), banner=decode_file_object(data.get('banner')), categories=cats, created_at=data.get('createdAt'))

def decode_game_profile(data: dict) -> 'GameProfile':
    from .models import GameProfile
    if not data:
        return None
    return GameProfile(id=data.get('id'), slug=data.get('slug'), name=data.get('name'), type=GameTypes.__members__.get(data.get('type')), logo=decode_file_object(data.get('logo')))

def decode_game_category(data: dict) -> 'GameCategory':
    from .models import GameCategory
    if not data:
        return None
    options = []
    data_options = data.get('options')
    if data_options:
        for option in data_options:
            options.append(decode_category_option(option))
    agrs = []
    data_agrs = data.get('agreements')
    if data_agrs:
        for agr in data_agrs:
            agrs.append(decode_category_agreement(agr))
    return GameCategory(id=data.get('id'), slug=data.get('slug'), name=data.get('name'), category_id=data.get('categoryId'), game_id=data.get('gameId'), obtaining=data.get('obtaining'), options=options, props=decode_category_props(data.get('props')), no_comment_from_buyer=data.get('noCommentFromBuyer'), instruction_for_buyer=data.get('instructionForBuyer'), instruction_for_seller=data.get('instructionForSeller'), use_custom_obtaining=data.get('useCustomObtaining'), auto_confirm_period=GameCategoryAutoConfirmPeriods.__members__.get(data.get('autoConfirmPeriod')), auto_moderation_mode=data.get('autoModerationMode'), agreements=agrs, fee_multiplier=data.get('feeMultiplier'))

def decode_game_page_info(data: dict) -> 'GamePageInfo':
    from .models import GamePageInfo
    if not data:
        return None
    return GamePageInfo(start_cursor=data.get('startCursor'), end_cursor=data.get('endCursor'), has_previous_page=data.get('hasPreviousPage'), has_next_page=data.get('hasNextPage'))

def decode_game_list(data: dict) -> 'GameList':
    from .models import GameList
    if not data:
        return None
    games = []
    edges: list[dict] = data.get('edges')
    if edges:
        for edge in edges:
            games.append(decode_game(edge.get('node')))
    return GameList(games=games, page_info=decode_game_page_info(data.get('pageInfo')), total_count=data.get('totalCount'))

def decode_category_data_field(data: dict) -> 'GameCategoryDataField':
    from .models import GameCategoryDataField
    if not data:
        return None
    return GameCategoryDataField(id=data.get('id'), label=data.get('label'), type=FieldScope.__members__.get(data.get('type')), input_type=GameCategoryDataFieldInputTypes.__members__.get(data.get('inputType')), copyable=data.get('copyable'), hidden=data.get('hidden'), required=data.get('required'), value=data.get('value'))

def decode_category_data_field_page_info(data: dict) -> 'GameCategoryDataFieldPageInfo':
    from .models import GameCategoryDataFieldPageInfo
    if not data:
        return None
    return GameCategoryDataFieldPageInfo(start_cursor=data.get('startCursor'), end_cursor=data.get('endCursor'), has_previous_page=data.get('hasPreviousPage'), has_next_page=data.get('hasNextPage'))

def decode_category_data_field_list(data: dict) -> 'GameCategoryDataFieldList':
    from .models import GameCategoryDataFieldList
    if not data:
        return None
    data_fields = []
    edges: list[dict] = data.get('edges')
    if edges:
        for edge in edges:
            data_fields.append(decode_category_data_field(edge.get('node')))
    return GameCategoryDataFieldList(data_fields=data_fields, page_info=decode_category_data_field_page_info(data.get('pageInfo')), total_count=data.get('totalCount'))

def decode_category_props(data: dict) -> 'GameCategoryProps':
    from .models import GameCategoryProps
    if not data:
        return None
    return GameCategoryProps(min_reviews=data.get('minTestimonials'), min_reviews_for_seller=data.get('minTestimonialsForSeller'))

def decode_category_option(data: dict) -> 'GameCategoryOption':
    from .models import GameCategoryOption
    if not data:
        return None
    return enrich_response(GameCategoryOption(id=data.get('id'), group=data.get('group'), label=data.get('label'), type=OptionStyle.__members__.get(data.get('type')), field=data.get('field'), value=data.get('value'), value_range_limit=data.get('valueRangeLimit')), data)

def decode_category_agreement(data: dict) -> 'GameCategoryAgreement':
    from .models import GameCategoryAgreement
    if not data:
        return None
    return GameCategoryAgreement(id=data.get('id'), description=data.get('description'), icontype=GameCategoryAgreementIconTypes.__members__.get(data.get('iconType')), sequence=data.get('sequence'))

def decode_category_agreement_page_info(data: dict) -> 'GameCategoryAgreementPageInfo':
    from .models import GameCategoryAgreementPageInfo
    if not data:
        return None
    return GameCategoryAgreementPageInfo(start_cursor=data.get('startCursor'), end_cursor=data.get('endCursor'), has_previous_page=data.get('hasPreviousPage'), has_next_page=data.get('hasNextPage'))

def decode_category_agreement_list(data: dict) -> 'GameCategoryAgreementList':
    from .models import GameCategoryAgreementList
    if not data:
        return None
    agreements = []
    edges: list[dict] = data.get('edges')
    if edges:
        for edge in edges:
            agreements.append(decode_category_agreement(edge.get('node')))
    return GameCategoryAgreementList(agreements=agreements, page_info=decode_category_agreement_page_info(data.get('pageInfo')), total_count=data.get('totalCount'))

def decode_category_obtaining_type(data: dict) -> 'GameCategoryObtainingType':
    from .models import GameCategoryObtainingType
    if not data:
        return None
    agrs = []
    data_agrs = data.get('agreements')
    if data_agrs:
        for agr in data_agrs:
            agrs.append(decode_category_agreement(agr))
    return enrich_response(GameCategoryObtainingType(id=data.get('id'), name=data.get('name'), description=data.get('description'), game_category_id=data.get('gameCategoryId'), no_comment_from_buyer=data.get('noCommentFromBuyer'), instruction_for_buyer=data.get('instructionForBuyer'), instruction_for_seller=data.get('instructionForSeller'), sequence=data.get('sequence'), fee_multiplier=data.get('feeMultiplier'), agreements=agrs, props=decode_category_props(data.get('props'))), data)

def decode_category_obtaining_type_page_info(data: dict) -> 'GameCategoryObtainingTypePageInfo':
    from .models import GameCategoryObtainingTypePageInfo
    if not data:
        return None
    return GameCategoryObtainingTypePageInfo(start_cursor=data.get('startCursor'), end_cursor=data.get('endCursor'), has_previous_page=data.get('hasPreviousPage'), has_next_page=data.get('hasNextPage'))

def decode_category_obtaining_type_list(data: dict) -> 'GameCategoryObtainingTypeList':
    from .models import GameCategoryObtainingTypeList
    if not data:
        return None
    types = []
    edges: list[dict] = data.get('edges')
    if edges:
        for edge in edges:
            types.append(decode_category_obtaining_type(edge.get('node')))
    return GameCategoryObtainingTypeList(obtaining_types=types, page_info=decode_category_obtaining_type_page_info(data.get('pageInfo')), total_count=data.get('totalCount'))

def decode_category_instruction(data: dict) -> 'GameCategoryInstruction':
    from .models import GameCategoryInstruction
    if not data:
        return None
    return GameCategoryInstruction(id=data.get('id'), text=data.get('text'))

def decode_category_instruction_page_info(data: dict) -> 'GameCategoryInstructionPageInfo':
    from .models import GameCategoryInstructionPageInfo
    if not data:
        return None
    return GameCategoryInstructionPageInfo(start_cursor=data.get('startCursor'), end_cursor=data.get('endCursor'), has_previous_page=data.get('hasPreviousPage'), has_next_page=data.get('hasNextPage'))

def decode_category_instruction_list(data: dict) -> 'GameCategoryInstructionList':
    from .models import GameCategoryInstructionList
    if not data:
        return None
    instructions = []
    edges: list[dict] = data.get('edges')
    if edges:
        for edge in edges:
            instructions.append(decode_category_instruction(edge.get('node')))
    return GameCategoryInstructionList(instructions=instructions, page_info=decode_category_instruction_page_info(data.get('pageInfo')), total_count=data.get('totalCount'))

def decode_transaction(data: dict) -> 'Transaction':
    from .models import Transaction
    if not data:
        return None
    return Transaction(id=data.get('id'), operation=TxKind.__members__.get(data.get('operation')), direction=TransactionDirections.__members__.get(data.get('direction')), provider_id=PayGateway.__members__.get(data.get('providerId')), provider=decode_transaction_provider(data.get('provider')), user=decode_user_profile(data.get('user')), creator=decode_user_profile(data.get('creator')), status=TxStage.__members__.get(data.get('status')), status_description=data.get('statusDescription'), status_expiration_date=data.get('statusExpirationDate'), value=data.get('value'), fee=data.get('fee'), created_at=data.get('createdAt'), verified_at=data.get('verifiedAt'), verified_by=decode_user_profile(data.get('verifiedBy')), completed_at=data.get('completedAt'), completed_by=decode_user_profile(data.get('completedBy')), payment_method_id=PayMethod.__members__.get(data.get('paymentMethodId')), is_suspicious=data.get('isSuspicious'), sbp_bank_name=data.get('spbBankName'), props=data.get('props'), auto_claimed_at=data.get('autoClaimedAt'))

def decode_transaction_page_info(data: dict) -> 'TransactionPageInfo':
    from .models import TransactionPageInfo
    if not data:
        return None
    return TransactionPageInfo(start_cursor=data.get('startCursor'), end_cursor=data.get('endCursor'), has_previous_page=data.get('hasPreviousPage'), has_next_page=data.get('hasNextPage'))

def decode_transaction_list(data: dict) -> 'TransactionList':
    from .models import TransactionList
    if not data:
        return None
    return TransactionList(transactions=[decode_transaction(edge.get('node')) for edge in data.get('edges')], page_info=decode_transaction_page_info(data.get('pageInfo')), total_count=data.get('totalCount'))

def decode_transaction_payment_method(data: dict) -> 'TransactionPaymentMethod':
    from .models import TransactionPaymentMethod
    if not data:
        return None
    return TransactionPaymentMethod(id=PayMethod.__members__.get(data.get('id')), name=data.get('name'), fee=data.get('fee'), provider_id=PayGateway.__members__.get(data.get('providerId') or data.get('provider_id')), account=decode_transaction_provider_account(data.get('account')), props=decode_transaction_provider_props(data.get('props')), limits=decode_transaction_provider_limits(data.get('limits')))

def decode_transaction_provider(data: dict) -> 'TransactionProvider':
    from .models import TransactionProvider
    if not data:
        return None
    return TransactionProvider(id=PayGateway.__members__.get(data.get('id')), name=data.get('name'), fee=data.get('fee'), min_fee_amount=data.get('minFeeAmount'), description=data.get('description'), account=decode_transaction_provider_account(data.get('account')), props=decode_transaction_provider_props(data.get('props')), limits=decode_transaction_provider_limits(data.get('limits')), payment_methods=[decode_transaction_payment_method(method) for method in data.get('paymentMethods') or []])

def decode_transaction_provider_account(data: dict) -> 'TransactionProviderAccount':
    from .models import TransactionProviderAccount
    if not data:
        return None
    return TransactionProviderAccount(
        id=data.get('id'),
        value=data.get('value'),
        user_id=data.get('userId'),
        provider_id=PayGateway.__members__.get(data.get('providerId')),
        payment_method_id=PayMethod.__members__.get(data.get('paymentMethodId')),
    )

def decode_transaction_provider_props(data: dict) -> 'TransactionProviderProps':
    from .models import TransactionProviderProps
    if not data:
        return None
    return TransactionProviderProps(required_user_data=decode_transaction_provider_required_user_data(data.get('requiredUserData')), tooltip=data.get('tooltip'))

def decode_transaction_provider_limits(data: dict) -> 'TransactionProviderLimits':
    from .models import TransactionProviderLimits
    if not data:
        return None
    return TransactionProviderLimits(incoming=decode_transaction_provider_limit_range(data.get('incoming')), outgoing=decode_transaction_provider_limit_range(data.get('outgoing')))

def decode_transaction_provider_limit_range(data: dict) -> 'TransactionProviderLimitRange':
    from .models import TransactionProviderLimitRange
    if not data:
        return None
    return TransactionProviderLimitRange(min=data.get('min'), max=data.get('max'))

def decode_transaction_provider_required_user_data(data: dict) -> 'TransactionProviderRequiredUserData':
    from .models import TransactionProviderRequiredUserData
    if not data:
        return None
    return TransactionProviderRequiredUserData(email=data.get('email'), phone_number=data.get('phoneNumber'), erip_account_number=data.get('eripAccountNumber'))

def decode_user_profile(data: dict) -> 'UserProfile':
    from .models import UserProfile
    if not data:
        return None
    u = UserProfile(id=data.get('id'), username=data.get('username', 'Поддержка'), role=AccountRole.__members__.get(data.get('role')), avatar_url=data.get('avatarURL'), is_online=data.get('isOnline'), is_blocked=data.get('isBlocked'), rating=data.get('rating'), reviews_count=data.get('testimonialCounter'), created_at=data.get('createdAt'), support_chat_id=data.get('supportChatId'), system_chat_id=data.get('systemChatId'))
    return u

def decode_bank_card(data: dict) -> 'UserBankCard':
    from .models import UserBankCard
    if not data:
        return None
    return UserBankCard(id=data.get('id'), card_first_six=data.get('cardFirstSix'), card_last_four=data.get('cardLastFour'), card_type=BankCardTypes.__members__.get(data.get('cardType')), is_chosen=data.get('isChosen'))

def decode_bank_card_page_info(data: dict) -> 'UserBankCardPageInfo':
    from .models import UserBankCardPageInfo
    if not data:
        return None
    return UserBankCardPageInfo(start_cursor=data.get('startCursor'), end_cursor=data.get('endCursor'), has_previous_page=data.get('hasPreviousPage'), has_next_page=data.get('hasNextPage'))

def decode_bank_card_list(data: dict) -> 'UserBankCardList':
    from .models import UserBankCardList
    if not data:
        return None
    return UserBankCardList(bank_cards=[decode_bank_card(edge.get('node')) for edge in data.get('edges')], page_info=decode_bank_card_page_info(data.get('pageInfo')), total_count=data.get('totalCount'))

def decode_sbp_bank_member(data: dict) -> 'SBPBankMember':
    from .models import SBPBankMember
    if not data:
        return None
    return SBPBankMember(id=data.get('id'), name=data.get('name'), icon=data.get('icon'))

def decode_moderator(data: dict) -> 'Moderator':
    ...

def decode_stream_event(data: dict):
    return message_event(data)

def decode_file_object(data: dict) -> 'FileObject':
    from .models import FileObject
    if not data:
        return None
    return FileObject(id=data.get('id'), url=data.get('url'), filename=data.get('filename'), mime=data.get('mime'))

def decode_temporary_attachment_upload_output(data: dict) -> 'TemporaryAttachmentUploadOutput':
    from .models import TemporaryAttachmentUploadOutput
    if not data:
        return None
    return TemporaryAttachmentUploadOutput(
        id=data.get('id'),
        url=data.get('url'),
        chat_id=data.get('chatId'),
        client_attachment_id=data.get('clientAttachmentId'),
        expires_at=data.get('expiresAt'),
    )
temporary_attachment_upload_output = decode_temporary_attachment_upload_output
file = decode_file_object
sbp_bank_member = decode_sbp_bank_member
transaction_payment_method = decode_transaction_payment_method
transaction_provider_limit_range = decode_transaction_provider_limit_range
transaction_provider_limits = decode_transaction_provider_limits
transaction_provider_required_user_data = decode_transaction_provider_required_user_data
transaction_provider_props = decode_transaction_provider_props
transaction_provider = decode_transaction_provider
transaction = decode_transaction
transaction_page_info = decode_transaction_page_info
transaction_list = decode_transaction_list
user_bank_card = decode_bank_card
user_bank_card_page_info = decode_bank_card_page_info
user_bank_card_list = decode_bank_card_list
game_category_data_field = decode_category_data_field
game_category_data_field_page_info = decode_category_data_field_page_info
game_category_data_field_list = decode_category_data_field_list
game_category_props = decode_category_props
game_category_option = decode_category_option
game_category_agreement = decode_category_agreement
game_category_agreement_page_info = decode_category_agreement_page_info
game_category_agreement_list = decode_category_agreement_list
game_category_obtaining_type = decode_category_obtaining_type
game_category_obtaining_type_page_info = decode_category_obtaining_type_page_info
game_category_obtaining_type_list = decode_category_obtaining_type_list
game_category_instruction = decode_category_instruction
game_category_instruction_page_info = decode_category_instruction_page_info
game_category_instruction_list = decode_category_instruction_list
game_category = decode_game_category
game = decode_game
game_profile = decode_game_profile
game_page_info = decode_game_page_info
game_list = decode_game_list
user_profile = decode_user_profile
account_items_stats = decode_account_items_stats
account_incoming_deals_stats = decode_account_incoming_deals_stats
account_outgoing_deals_stats = decode_account_outgoing_deals_stats
account_deals_stats = decode_account_deals_stats
account_stats = decode_account_stats
account_balance = decode_account_balance
account_profile = decode_account_profile
item_priority_status_price_range = decode_item_priority_status_price_range
item_priority_status = decode_item_priority_status
item_log = decode_item_log
item = decode_item
my_item = decode_my_item
item_profile = decode_item_profile
item_profile_page_info = decode_item_profile_page_info
item_profile_list = decode_item_profile_list
moderator = decode_moderator
event = decode_stream_event
chat = decode_chat
chat_page_info = decode_chat_page_info
chat_list = decode_chat_list
review = decode_review
review_page_info = decode_review_page_info
review_list = decode_review_list
item_deal = decode_item_deal
item_deal_page_info = decode_item_deal_page_info
item_deal_list = decode_item_deal_list
chat_message_button = decode_chat_message_button
chat_message = decode_chat_message
chat_message_page_info = decode_chat_message_page_info
chat_message_list = decode_chat_message_list
