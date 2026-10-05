from types import MappingProxyType

OPTIONAL_RESPONSE_FIELDS = MappingProxyType({
    "is_vip": "isVip",
    "is_automated": "isAutomated",
    "keep_in_sale": "keepInSale",
    "keep_in_sale_available": "keepInSaleAvailable",
    "pause_available": "pauseAvailable",
    "republish_available": "republishAvailable",
    "may_be_published": "mayBePublished",
    "post_moderation_checked_at": "postModerationCheckedAt",
    "is_attachments_forbidden": "isAttachmentsForbidden",
    "characteristics": "characteristics",
    "deals_counter": "dealsCounter",
    "stock_type": "stockType",
    "multiple": "multiple",
    "image_links": "imageLinks",
    "pl_token_amount": "plTokenAmount",
    "uncensor_info": "uncensorInfo",
})
