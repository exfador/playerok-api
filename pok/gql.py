PERSISTED_QUERIES = {'user': '1149bd67f3773e9d37beb4a22a1fb4dd5bd248986b810a25bae0b717f19a449d', 'deals': 'c3b623b5fe0758cf91b2335ebf36ff65f8650a6672a792a3ca7a36d270d396fb', 'deal': '5652037a966d8da6d41180b0be8226051fe0ed1357d460c6ae348c3138a0fba3', 'testimonials': '773d40b7efec82a4b86021ba8bcaa462f68eb236e255926f2168c5cd4685e881', 'games': '5de9b3240c148579c82e2310a30b4aad5462884fd1abf93dd3c43d1f5ef14d85', 'GamePage': '4775f8630a3e234c50537e68649043ac32a40b0370b0f1fb2dc314500ef6202d', 'GamePageCategory': '7759f743651176ddad6afefb5f2e889ec9984cae08a015281879cd61e94bdb60', 'gameCategoryAgreements': '3ea4b047196ed9f84aa5eb652299c4bd73f2e99e9fdf4587877658d9ea6330f6', 'gameCategoryObtainingTypes': '15b0991414821528251930b4c8161c299eb39882fd635dd5adb1a81fb0570aea', 'gameCategoryInstructions': '15b0991414821528251930b4c8161c299eb39882fd635dd5adb1a81fb0570aea', 'gameCategoryDataFields': '6fdadfb9b05880ce2d307a1412bc4f2e383683061c281e2b65a93f7266ea4a49', 'userChats': '999f86b7c94a4cb525ed5549d8f24d0d24036214f02a213e8fd7cefc742bbd58', 'chat': 'bb024dc0652fc7c1302a64a117d56d99fb0d726eb4b896ca803dca55f611d933', 'chatMessages': '587e8a28b6a2487232d82abed32093367609d57a05601246d09926f4c83deb67', 'items': '63eefcfd813442882ad846360d925279bc376e8bc85a577ebefbee0f9c78b557', 'item': '37d2d9f947e950c09322e2f5e3056451ee5f12dc38565eb811423e915c094c22', 'itemPriorityStatuses': 'b922220c6f979537e1b99de6af8f5c13727daeff66727f679f07f986ce1c025a', 'transactionProviders': '31960e5dd929834c1f85bc685db80657ff576373076f016b2578c0a34e6e9f42', 'transactions': 'e3c9d07ba6b2dd15cc82c5006449db50f8d9b88b0c4cb02d50d308ebee1276f6', 'SbpBankMembers': 'ef7902598e855fa15fb5e3112156ac226180f0b009a36606fc80a18f00b80c63', 'verifiedCards': 'eb338d8432981307a2b3d322b3310b2447cab3a6acf21aba4b8773b97e72d1aa'}
QUERIES = {'viewer': 'query viewer {\n  viewer {\n    ...Viewer\n    __typename\n  }\n}\n\nfragment Viewer on User {\n  id\n  username\n  email\n  role\n  hasFrozenBalance\n  supportChatId\n  systemChatId\n  unreadChatsCounter\n  isBlocked\n  isBlockedFor\n  isFundsProtectionActive\n  createdAt\n  lastItemCreatedAt\n  hasConfirmedPhoneNumber\n  canPublishItems\n  chosenVerifiedCard {\n    ...MinimalUserBankCard\n    __typename\n  }\n  balance {\n    value\n    __typename\n  }\n  profile {\n    id\n    avatarURL\n    testimonialCounter\n    __typename\n  }\n  __typename\n}\n\nfragment MinimalUserBankCard on UserBankCard {\n  id\n  cardFirstSix\n  cardLastFour\n  cardType\n  isChosen\n  __typename\n}', 'updateDeal': 'mutation updateDeal($input: UpdateItemDealInput!) {\n  updateDeal(input: $input) {\n    ...RegularItemDeal\n    __typename\n  }\n}\n\nfragment RegularItemDeal on ItemDeal {\n  id\n  status\n  direction\n  statusExpirationDate\n  statusDescription\n  obtaining\n  hasProblem\n  reportProblemEnabled\n  completedBy {\n    ...MinimalUserFragment\n    __typename\n  }\n  props {\n    ...ItemDealProps\n    __typename\n  }\n  prevStatus\n  completedAt\n  createdAt\n  logs {\n    ...ItemLog\n    __typename\n  }\n  transaction {\n    ...ItemDealTransaction\n    __typename\n  }\n  user {\n    ...UserEdgeNode\n    __typename\n  }\n  chat {\n    ...RegularChatId\n    __typename\n  }\n  item {\n    ...PartialDealItem\n    __typename\n  }\n  testimonial {\n    ...RegularItemDealTestimonial\n    __typename\n  }\n  obtainingFields {\n    ...GameCategoryDataFieldWithValue\n    __typename\n  }\n  commentFromBuyer\n  __typename\n}\n\nfragment MinimalUserFragment on UserFragment {\n  id\n  username\n  role\n  __typename\n}\n\nfragment ItemDealProps on ItemDealProps {\n  autoConfirmPeriod\n  __typename\n}\n\nfragment ItemLog on ItemLog {\n  id\n  event\n  createdAt\n  user {\n    ...UserEdgeNode\n    __typename\n  }\n  __typename\n}\n\nfragment UserEdgeNode on UserFragment {\n  ...RegularUserFragment\n  __typename\n}\n\nfragment RegularUserFragment on UserFragment {\n  id\n  username\n  role\n  avatarURL\n  isOnline\n  isBlocked\n  rating\n  testimonialCounter\n  createdAt\n  supportChatId\n  systemChatId\n  __typename\n}\n\nfragment ItemDealTransaction on Transaction {\n  id\n  operation\n  direction\n  providerId\n  status\n  value\n  createdAt\n  paymentMethodId\n  statusExpirationDate\n  __typename\n}\n\nfragment RegularChatId on Chat {\n  id\n  __typename\n}\n\nfragment PartialDealItem on Item {\n  ...PartialDealMyItem\n  ...PartialDealForeignItem\n  __typename\n}\n\nfragment PartialDealMyItem on MyItem {\n  id\n  slug\n  priority\n  status\n  name\n  price\n  priorityPrice\n  rawPrice\n  statusExpirationDate\n  sellerType\n  approvalDate\n  createdAt\n  priorityPosition\n  viewsCounter\n  feeMultiplier\n  comment\n  attachments {\n    ...RegularFile\n    __typename\n  }\n  user {\n    ...UserEdgeNode\n    __typename\n  }\n  game {\n    ...RegularGameProfile\n    __typename\n  }\n  category {\n    ...MinimalGameCategory\n    __typename\n  }\n  dataFields {\n    ...GameCategoryDataFieldWithValue\n    __typename\n  }\n  obtainingType {\n    ...MinimalGameCategoryObtainingType\n    __typename\n  }\n  __typename\n}\n\nfragment RegularFile on File {\n  id\n  url\n  filename\n  mime\n  __typename\n}\n\nfragment RegularGameProfile on GameProfile {\n  id\n  name\n  type\n  slug\n  logo {\n    ...PartialFile\n    __typename\n  }\n  __typename\n}\n\nfragment PartialFile on File {\n  id\n  url\n  __typename\n}\n\nfragment MinimalGameCategory on GameCategory {\n  id\n  slug\n  name\n  __typename\n}\n\nfragment GameCategoryDataFieldWithValue on GameCategoryDataFieldWithValue {\n  id\n  label\n  type\n  inputType\n  copyable\n  hidden\n  required\n  value\n  __typename\n}\n\nfragment MinimalGameCategoryObtainingType on GameCategoryObtainingType {\n  id\n  name\n  description\n  gameCategoryId\n  noCommentFromBuyer\n  instructionForBuyer\n  instructionForSeller\n  sequence\n  feeMultiplier\n  props {\n    minTestimonialsForSeller\n    __typename\n  }\n  __typename\n}\n\nfragment PartialDealForeignItem on ForeignItem {\n  id\n  slug\n  priority\n  status\n  name\n  price\n  rawPrice\n  sellerType\n  approvalDate\n  priorityPosition\n  createdAt\n  viewsCounter\n  feeMultiplier\n  comment\n  attachments {\n    ...RegularFile\n    __typename\n  }\n  user {\n    ...UserEdgeNode\n    __typename\n  }\n  game {\n    ...RegularGameProfile\n    __typename\n  }\n  category {\n    ...MinimalGameCategory\n    __typename\n  }\n  dataFields {\n    ...GameCategoryDataFieldWithValue\n    __typename\n  }\n  obtainingType {\n    ...MinimalGameCategoryObtainingType\n    __typename\n  }\n  __typename\n}\n\nfragment RegularItemDealTestimonial on Testimonial {\n  id\n  status\n  text\n  rating\n  createdAt\n  updatedAt\n  creator {\n    ...RegularUserFragment\n    __typename\n  }\n  moderator {\n    ...RegularUserFragment\n    __typename\n  }\n  user {\n    ...RegularUserFragment\n    __typename\n  }\n  __typename\n}', 'markChatAsRead': 'mutation markChatAsRead($input: MarkChatAsReadInput!) {\n\tmarkChatAsRead(input: $input) {\n\t\t...RegularChat\n\t\t__typename\n\t}\n}\n\nfragment RegularChat on Chat {\n\tid\n\ttype\n\tunreadMessagesCounter\n\tbookmarked\n\tisTextingAllowed\n\towner {\n\t\t...ChatParticipant\n\t\t__typename\n\t}\n\tagent {\n\t\t...ChatParticipant\n\t\t__typename\n\t}\n\tparticipants {\n\t\t...ChatParticipant\n\t\t__typename\n\t}\n\tdeals {\n\t\t...ChatActiveItemDeal\n\t\t__typename\n\t}\n\tstatus\n\tstartedAt\n\tfinishedAt\n\t__typename\n}\n\nfragment ChatParticipant on UserFragment {\n\t...RegularUserFragment\n\t__typename\n}\n\nfragment RegularUserFragment on UserFragment {\n\tid\n\tusername\n\trole\n\tavatarURL\n\tisOnline\n\tisBlocked\n\trating\n\ttestimonialCounter\n\tcreatedAt\n\tsupportChatId\n\tsystemChatId\n\t__typename\n}\n\nfragment ChatActiveItemDeal on ItemDealProfile {\n\tid\n\tdirection\n\tstatus\n\thasProblem\n\ttestimonial {\n\t\tid\n\t\trating\n\t\t__typename\n\t}\n\titem {\n\t\t...ChatDealItemEdgeNode\n\t\t__typename\n\t}\n\tuser {\n\t\t...RegularUserFragment\n\t\t__typename\n\t}\n\t__typename\n}\n\nfragment ChatDealItemEdgeNode on ItemProfile {\n\t...ChatDealMyItemEdgeNode\n\t...ChatDealForeignItemEdgeNode\n\t__typename\n}\n\nfragment ChatDealMyItemEdgeNode on MyItemProfile {\n\tid\n\tslug\n\tpriority\n\tstatus\n\tname\n\tprice\n\trawPrice\n\tstatusExpirationDate\n\tsellerType\n\tattachment {\n\t\t...PartialFile\n\t\t__typename\n\t}\n\tuser {\n\t\t...UserItemEdgeNode\n\t\t__typename\n\t}\n\tapprovalDate\n\tcreatedAt\n\tpriorityPosition\n\tfeeMultiplier\n\t__typename\n}\n\nfragment PartialFile on File {\n\tid\n\turl\n\t__typename\n}\n\nfragment UserItemEdgeNode on UserFragment {\n\t...UserEdgeNode\n\t__typename\n}\n\nfragment UserEdgeNode on UserFragment {\n\t...RegularUserFragment\n\t__typename\n}\n\nfragment ChatDealForeignItemEdgeNode on ForeignItemProfile {\n\tid\n\tslug\n\tpriority\n\tstatus\n\tname\n\tprice\n\trawPrice\n\tsellerType\n\tattachment {\n\t\t...PartialFile\n\t\t__typename\n\t}\n\tuser {\n\t\t...UserItemEdgeNode\n\t\t__typename\n\t}\n\tapprovalDate\n\tpriorityPosition\n\tcreatedAt\n\tfeeMultiplier\n\t__typename\n}', 'createChatMessageWithFile': 'mutation createChatMessage($input: CreateChatMessageInput!, $file: Upload, $showForbiddenImage: Boolean) {\n  createChatMessage(input: $input, file: $file) {\n    ...RegularChatMessage\n    __typename\n  }\n}\n\nfragment RegularChatMessage on ChatMessage {\n  id\n  text\n  createdAt\n  deletedAt\n  isRead\n  isSuspicious\n  isBulkMessaging\n  game {\n    ...RegularGameProfile\n    __typename\n  }\n  file {\n    ...PartialFile\n    __typename\n  }\n  user {\n    ...ChatMessageUserFields\n    __typename\n  }\n  deal {\n    ...ChatMessageItemDeal\n    __typename\n  }\n  item {\n    ...ItemEdgeNode\n    __typename\n  }\n  transaction {\n    ...RegularTransaction\n    __typename\n  }\n  moderator {\n    ...UserEdgeNode\n    __typename\n  }\n  eventByUser {\n    ...ChatMessageUserFields\n    __typename\n  }\n  eventToUser {\n    ...ChatMessageUserFields\n    __typename\n  }\n  isAutoResponse\n  event\n  buttons {\n    ...ChatMessageButton\n    __typename\n  }\n  images {\n    ...RegularFile\n    __typename\n  }\n  __typename\n}\n\nfragment RegularGameProfile on GameProfile {\n  id\n  name\n  type\n  slug\n  logo {\n    ...PartialFile\n    __typename\n  }\n  __typename\n}\n\nfragment PartialFile on File {\n  id\n  url\n  __typename\n}\n\nfragment ChatMessageUserFields on UserFragment {\n  ...UserEdgeNode\n  __typename\n}\n\nfragment UserEdgeNode on UserFragment {\n  ...RegularUserFragment\n  __typename\n}\n\nfragment RegularUserFragment on UserFragment {\n  id\n  username\n  role\n  avatarURL\n  isOnline\n  isBlocked\n  rating\n  testimonialCounter\n  createdAt\n  supportChatId\n  systemChatId\n  __typename\n}\n\nfragment ChatMessageItemDeal on ItemDeal {\n  id\n  direction\n  status\n  statusDescription\n  hasProblem\n  user {\n    ...ChatParticipant\n    __typename\n  }\n  testimonial {\n    ...ChatMessageDealTestimonial\n    __typename\n  }\n  item {\n    id\n    name\n    price\n    slug\n    rawPrice\n    sellerType\n    user {\n      ...ChatParticipant\n      __typename\n    }\n    category {\n      id\n      __typename\n    }\n    attachments(showForbiddenImage: $showForbiddenImage) {\n      ...PartialFile\n      __typename\n    }\n    isAttachmentsForbidden\n    comment\n    dataFields {\n      ...GameCategoryDataFieldWithValue\n      __typename\n    }\n    obtainingType {\n      ...GameCategoryObtainingType\n      __typename\n    }\n    __typename\n  }\n  obtainingFields {\n    ...GameCategoryDataFieldWithValue\n    __typename\n  }\n  chat {\n    id\n    type\n    __typename\n  }\n  transaction {\n    id\n    statusExpirationDate\n    __typename\n  }\n  statusExpirationDate\n  commentFromBuyer\n  __typename\n}\n\nfragment ChatParticipant on UserFragment {\n  ...RegularUserFragment\n  __typename\n}\n\nfragment ChatMessageDealTestimonial on Testimonial {\n  id\n  status\n  text\n  rating\n  createdAt\n  updatedAt\n  creator {\n    ...RegularUserFragment\n    __typename\n  }\n  moderator {\n    ...RegularUserFragment\n    __typename\n  }\n  user {\n    ...RegularUserFragment\n    __typename\n  }\n  __typename\n}\n\nfragment GameCategoryDataFieldWithValue on GameCategoryDataFieldWithValue {\n  id\n  label\n  type\n  inputType\n  copyable\n  hidden\n  required\n  value\n  __typename\n}\n\nfragment GameCategoryObtainingType on GameCategoryObtainingType {\n  id\n  name\n  description\n  gameCategoryId\n  noCommentFromBuyer\n  instructionForBuyer\n  instructionForSeller\n  sequence\n  feeMultiplier\n  agreements {\n    ...MinimalGameCategoryAgreement\n    __typename\n  }\n  props {\n    minTestimonialsForSeller\n    __typename\n  }\n  __typename\n}\n\nfragment MinimalGameCategoryAgreement on GameCategoryAgreement {\n  description\n  iconType\n  id\n  sequence\n  __typename\n}\n\nfragment ItemEdgeNode on ItemProfile {\n  ...MyItemEdgeNode\n  ...ForeignItemEdgeNode\n  __typename\n}\n\nfragment MyItemEdgeNode on MyItemProfile {\n  id\n  slug\n  priority\n  status\n  name\n  price\n  rawPrice\n  statusExpirationDate\n  sellerType\n  attachment(showForbiddenImage: $showForbiddenImage) {\n    ...PartialFile\n    __typename\n  }\n  isAttachmentsForbidden\n  user {\n    ...UserItemEdgeNode\n    __typename\n  }\n  approvalDate\n  createdAt\n  priorityPosition\n  viewsCounter\n  feeMultiplier\n  __typename\n}\n\nfragment UserItemEdgeNode on UserFragment {\n  ...UserEdgeNode\n  __typename\n}\n\nfragment ForeignItemEdgeNode on ForeignItemProfile {\n  id\n  slug\n  priority\n  status\n  name\n  price\n  rawPrice\n  sellerType\n  attachment(showForbiddenImage: $showForbiddenImage) {\n    ...PartialFile\n    __typename\n  }\n  isAttachmentsForbidden\n  user {\n    ...UserItemEdgeNode\n    __typename\n  }\n  approvalDate\n  priorityPosition\n  createdAt\n  viewsCounter\n  feeMultiplier\n  __typename\n}\n\nfragment RegularTransaction on Transaction {\n  id\n  operation\n  direction\n  providerId\n  provider {\n    ...RegularTransactionProvider\n    __typename\n  }\n  user {\n    ...RegularUserFragment\n    __typename\n  }\n  creator {\n    ...RegularUserFragment\n    __typename\n  }\n  status\n  statusDescription\n  statusExpirationDate\n  value\n  fee\n  createdAt\n  props {\n    ...RegularTransactionProps\n    __typename\n  }\n  verifiedAt\n  verifiedBy {\n    ...UserEdgeNode\n    __typename\n  }\n  completedBy {\n    ...UserEdgeNode\n    __typename\n  }\n  paymentMethodId\n  completedAt\n  isSuspicious\n  spbBankName\n  __typename\n}\n\nfragment RegularTransactionProvider on TransactionProvider {\n  id\n  name\n  fee\n  minFeeAmount\n  description\n  account {\n    ...RegularTransactionProviderAccount\n    __typename\n  }\n  props {\n    ...TransactionProviderPropsFragment\n    __typename\n  }\n  limits {\n    ...ProviderLimits\n    __typename\n  }\n  paymentMethods {\n    ...TransactionPaymentMethod\n    __typename\n  }\n  __typename\n}\n\nfragment RegularTransactionProviderAccount on TransactionProviderAccount {\n  id\n  value\n  userId\n  __typename\n}\n\nfragment TransactionProviderPropsFragment on TransactionProviderPropsFragment {\n  requiredUserData {\n    ...TransactionProviderRequiredUserData\n    __typename\n  }\n  tooltip\n  __typename\n}\n\nfragment TransactionProviderRequiredUserData on TransactionProviderRequiredUserData {\n  email\n  phoneNumber\n  eripAccountNumber\n  __typename\n}\n\nfragment ProviderLimits on ProviderLimits {\n  incoming {\n    ...ProviderLimitRange\n    __typename\n  }\n  outgoing {\n    ...ProviderLimitRange\n    __typename\n  }\n  __typename\n}\n\nfragment ProviderLimitRange on ProviderLimitRange {\n  min\n  max\n  __typename\n}\n\nfragment TransactionPaymentMethod on TransactionPaymentMethod {\n  id\n  name\n  fee\n  providerId\n  account {\n    ...RegularTransactionProviderAccount\n    __typename\n  }\n  props {\n    ...TransactionProviderPropsFragment\n    __typename\n  }\n  limits {\n    ...ProviderLimits\n    __typename\n  }\n  __typename\n}\n\nfragment RegularTransactionProps on TransactionPropsFragment {\n  creatorId\n  dealId\n  paidFromPendingIncome\n  paymentURL\n  successURL\n  fee\n  paymentAccount {\n    id\n    value\n    __typename\n  }\n  paymentGateway\n  alreadySpent\n  exchangeRate\n  amountAfterConversionRub\n  amountAfterConversionUsdt\n  userData {\n    account\n    email\n    ipAddress\n    phoneNumber\n    __typename\n  }\n  __typename\n}\n\nfragment ChatMessageButton on ChatMessageButton {\n  type\n  url\n  text\n  __typename\n}\n\nfragment RegularFile on File {\n  id\n  url\n  filename\n  mime\n  __typename\n}', 'createChatMessage': 'mutation createChatMessage($input: CreateChatMessageInput!, $file: Upload) {\n  createChatMessage(input: $input, file: $file) {\n    ...RegularChatMessage\n    __typename\n  }\n}\n\nfragment RegularChatMessage on ChatMessage {\n  id\n  text\n  createdAt\n  deletedAt\n  isRead\n  isSuspicious\n  isBulkMessaging\n  game {\n    ...RegularGameProfile\n    __typename\n  }\n  file {\n    ...PartialFile\n    __typename\n  }\n  user {\n    ...ChatMessageUserFields\n    __typename\n  }\n  deal {\n    ...ChatMessageItemDeal\n    __typename\n  }\n  item {\n    ...ItemEdgeNode\n    __typename\n  }\n  transaction {\n    ...RegularTransaction\n    __typename\n  }\n  moderator {\n    ...UserEdgeNode\n    __typename\n  }\n  eventByUser {\n    ...ChatMessageUserFields\n    __typename\n  }\n  eventToUser {\n    ...ChatMessageUserFields\n    __typename\n  }\n  isAutoResponse\n  event\n  buttons {\n    ...ChatMessageButton\n    __typename\n  }\n  __typename\n}\n\nfragment RegularGameProfile on GameProfile {\n  id\n  name\n  type\n  slug\n  logo {\n    ...PartialFile\n    __typename\n  }\n  __typename\n}\n\nfragment PartialFile on File {\n  id\n  url\n  __typename\n}\n\nfragment ChatMessageUserFields on UserFragment {\n  ...UserEdgeNode\n  __typename\n}\n\nfragment UserEdgeNode on UserFragment {\n  ...RegularUserFragment\n  __typename\n}\n\nfragment RegularUserFragment on UserFragment {\n  id\n  username\n  role\n  avatarURL\n  isOnline\n  isBlocked\n  rating\n  testimonialCounter\n  createdAt\n  supportChatId\n  systemChatId\n  __typename\n}\n\nfragment ChatMessageItemDeal on ItemDeal {\n  id\n  direction\n  status\n  statusDescription\n  hasProblem\n  user {\n    ...ChatParticipant\n    __typename\n  }\n  testimonial {\n    ...ChatMessageDealTestimonial\n    __typename\n  }\n  item {\n    id\n    name\n    price\n    slug\n    rawPrice\n    sellerType\n    user {\n      ...ChatParticipant\n      __typename\n    }\n    category {\n      id\n      __typename\n    }\n    attachments {\n      ...PartialFile\n      __typename\n    }\n    comment\n    dataFields {\n      ...GameCategoryDataFieldWithValue\n      __typename\n    }\n    obtainingType {\n      ...GameCategoryObtainingType\n      __typename\n    }\n    __typename\n  }\n  obtainingFields {\n    ...GameCategoryDataFieldWithValue\n    __typename\n  }\n  chat {\n    id\n    type\n    __typename\n  }\n  transaction {\n    id\n    statusExpirationDate\n    __typename\n  }\n  statusExpirationDate\n  commentFromBuyer\n  __typename\n}\n\nfragment ChatParticipant on UserFragment {\n  ...RegularUserFragment\n  __typename\n}\n\nfragment ChatMessageDealTestimonial on Testimonial {\n  id\n  status\n  text\n  rating\n  createdAt\n  updatedAt\n  creator {\n    ...RegularUserFragment\n    __typename\n  }\n  moderator {\n    ...RegularUserFragment\n    __typename\n  }\n  user {\n    ...RegularUserFragment\n    __typename\n  }\n  __typename\n}\n\nfragment GameCategoryDataFieldWithValue on GameCategoryDataFieldWithValue {\n  id\n  label\n  type\n  inputType\n  copyable\n  hidden\n  required\n  value\n  __typename\n}\n\nfragment GameCategoryObtainingType on GameCategoryObtainingType {\n  id\n  name\n  description\n  gameCategoryId\n  noCommentFromBuyer\n  instructionForBuyer\n  instructionForSeller\n  sequence\n  feeMultiplier\n  agreements {\n    ...MinimalGameCategoryAgreement\n    __typename\n  }\n  props {\n    minTestimonialsForSeller\n    __typename\n  }\n  __typename\n}\n\nfragment MinimalGameCategoryAgreement on GameCategoryAgreement {\n  description\n  iconType\n  id\n  sequence\n  __typename\n}\n\nfragment ItemEdgeNode on ItemProfile {\n  ...MyItemEdgeNode\n  ...ForeignItemEdgeNode\n  __typename\n}\n\nfragment MyItemEdgeNode on MyItemProfile {\n  id\n  slug\n  priority\n  status\n  name\n  price\n  rawPrice\n  statusExpirationDate\n  sellerType\n  attachment {\n    ...PartialFile\n    __typename\n  }\n  user {\n    ...UserItemEdgeNode\n    __typename\n  }\n  approvalDate\n  createdAt\n  priorityPosition\n  viewsCounter\n  feeMultiplier\n  __typename\n}\n\nfragment UserItemEdgeNode on UserFragment {\n  ...UserEdgeNode\n  __typename\n}\n\nfragment ForeignItemEdgeNode on ForeignItemProfile {\n  id\n  slug\n  priority\n  status\n  name\n  price\n  rawPrice\n  sellerType\n  attachment {\n    ...PartialFile\n    __typename\n  }\n  user {\n    ...UserItemEdgeNode\n    __typename\n  }\n  approvalDate\n  priorityPosition\n  createdAt\n  viewsCounter\n  feeMultiplier\n  __typename\n}\n\nfragment RegularTransaction on Transaction {\n  id\n  operation\n  direction\n  providerId\n  provider {\n    ...RegularTransactionProvider\n    __typename\n  }\n  user {\n    ...RegularUserFragment\n    __typename\n  }\n  creator {\n    ...RegularUserFragment\n    __typename\n  }\n  status\n  statusDescription\n  statusExpirationDate\n  value\n  fee\n  createdAt\n  props {\n    ...RegularTransactionProps\n    __typename\n  }\n  verifiedAt\n  verifiedBy {\n    ...UserEdgeNode\n    __typename\n  }\n  completedBy {\n    ...UserEdgeNode\n    __typename\n  }\n  paymentMethodId\n  completedAt\n  isSuspicious\n  __typename\n}\n\nfragment RegularTransactionProvider on TransactionProvider {\n  id\n  name\n  fee\n  minFeeAmount\n  description\n  account {\n    ...RegularTransactionProviderAccount\n    __typename\n  }\n  props {\n    ...TransactionProviderPropsFragment\n    __typename\n  }\n  limits {\n    ...ProviderLimits\n    __typename\n  }\n  paymentMethods {\n    ...TransactionPaymentMethod\n    __typename\n  }\n  __typename\n}\n\nfragment RegularTransactionProviderAccount on TransactionProviderAccount {\n  id\n  value\n  userId\n  __typename\n}\n\nfragment TransactionProviderPropsFragment on TransactionProviderPropsFragment {\n  requiredUserData {\n    ...TransactionProviderRequiredUserData\n    __typename\n  }\n  tooltip\n  __typename\n}\n\nfragment TransactionProviderRequiredUserData on TransactionProviderRequiredUserData {\n  email\n  phoneNumber\n  __typename\n}\n\nfragment ProviderLimits on ProviderLimits {\n  incoming {\n    ...ProviderLimitRange\n    __typename\n  }\n  outgoing {\n    ...ProviderLimitRange\n    __typename\n  }\n  __typename\n}\n\nfragment ProviderLimitRange on ProviderLimitRange {\n  min\n  max\n  __typename\n}\n\nfragment TransactionPaymentMethod on TransactionPaymentMethod {\n  id\n  name\n  fee\n  providerId\n  account {\n    ...RegularTransactionProviderAccount\n    __typename\n  }\n  props {\n    ...TransactionProviderPropsFragment\n    __typename\n  }\n  limits {\n    ...ProviderLimits\n    __typename\n  }\n  __typename\n}\n\nfragment RegularTransactionProps on TransactionPropsFragment {\n  creatorId\n  dealId\n  paidFromPendingIncome\n  paymentURL\n  successURL\n  fee\n  paymentAccount {\n    id\n    value\n    __typename\n  }\n  paymentGateway\n  alreadySpent\n  exchangeRate\n  amountAfterConversionRub\n  amountAfterConversionUsdt\n  __typename\n}\n\nfragment ChatMessageButton on ChatMessageButton {\n  type\n  url\n  text\n  __typename\n}', 'createItem': 'mutation createItem($input: CreateItemInput!, $attachments: [Upload!]!, $showForbiddenImage: Boolean) {\n  createItem(input: $input, attachments: $attachments) {\n    ...RegularItem\n    __typename\n  }\n}\n\nfragment RegularItem on Item {\n  ...RegularMyItem\n  ...RegularForeignItem\n  __typename\n}\n\nfragment RegularMyItem on MyItem {\n  ...ItemFields\n  prevPrice\n  priority\n  sequence\n  priorityPrice\n  statusExpirationDate\n  comment\n  viewsCounter\n  dealsCounter\n  statusDescription\n  editable\n  statusPayment {\n    ...StatusPaymentTransaction\n    __typename\n  }\n  moderator {\n    id\n    username\n    __typename\n  }\n  approvalDate\n  deletedAt\n  createdAt\n  updatedAt\n  mayBePublished\n  prevFeeMultiplier\n  sellerNotifiedAboutFeeChange\n  __typename\n}\n\nfragment ItemFields on Item {\n  id\n  slug\n  name\n  description\n  rawPrice\n  price\n  attributes\n  status\n  priorityPosition\n  sellerType\n  feeMultiplier\n  user {\n    ...ItemUser\n    __typename\n  }\n  buyer {\n    ...ItemUser\n    __typename\n  }\n  attachments(showForbiddenImage: $showForbiddenImage) {\n    ...PartialFile\n    __typename\n  }\n  isAttachmentsForbidden\n  category {\n    ...RegularGameCategory\n    __typename\n  }\n  game {\n    ...RegularGameProfile\n    __typename\n  }\n  comment\n  dataFields {\n    ...GameCategoryDataFieldWithValue\n    __typename\n  }\n  obtainingType {\n    ...GameCategoryObtainingType\n    __typename\n  }\n  __typename\n}\n\nfragment ItemUser on UserFragment {\n  ...UserEdgeNode\n  __typename\n}\n\nfragment UserEdgeNode on UserFragment {\n  ...RegularUserFragment\n  __typename\n}\n\nfragment RegularUserFragment on UserFragment {\n  id\n  username\n  role\n  avatarURL\n  isOnline\n  isBlocked\n  rating\n  testimonialCounter\n  createdAt\n  supportChatId\n  systemChatId\n  __typename\n}\n\nfragment PartialFile on File {\n  id\n  url\n  __typename\n}\n\nfragment RegularGameCategory on GameCategory {\n  id\n  slug\n  name\n  categoryId\n  gameId\n  obtaining\n  options {\n    ...RegularGameCategoryOption\n    __typename\n  }\n  props {\n    ...GameCategoryProps\n    __typename\n  }\n  noCommentFromBuyer\n  instructionForBuyer\n  instructionForSeller\n  useCustomObtaining\n  autoConfirmPeriod\n  autoModerationMode\n  agreements {\n    ...RegularGameCategoryAgreement\n    __typename\n  }\n  feeMultiplier\n  __typename\n}\n\nfragment RegularGameCategoryOption on GameCategoryOption {\n  id\n  group\n  label\n  type\n  field\n  value\n  valueRangeLimit {\n    min\n    max\n    __typename\n  }\n  __typename\n}\n\nfragment GameCategoryProps on GameCategoryPropsObjectType {\n  minTestimonials\n  minTestimonialsForSeller\n  __typename\n}\n\nfragment RegularGameCategoryAgreement on GameCategoryAgreement {\n  description\n  gameCategoryId\n  gameCategoryObtainingTypeId\n  iconType\n  id\n  sequence\n  __typename\n}\n\nfragment RegularGameProfile on GameProfile {\n  id\n  name\n  type\n  slug\n  logo {\n    ...PartialFile\n    __typename\n  }\n  __typename\n}\n\nfragment GameCategoryDataFieldWithValue on GameCategoryDataFieldWithValue {\n  id\n  label\n  type\n  inputType\n  copyable\n  hidden\n  required\n  value\n  __typename\n}\n\nfragment GameCategoryObtainingType on GameCategoryObtainingType {\n  id\n  name\n  description\n  gameCategoryId\n  noCommentFromBuyer\n  instructionForBuyer\n  instructionForSeller\n  sequence\n  feeMultiplier\n  agreements {\n    ...MinimalGameCategoryAgreement\n    __typename\n  }\n  props {\n    minTestimonialsForSeller\n    __typename\n  }\n  __typename\n}\n\nfragment MinimalGameCategoryAgreement on GameCategoryAgreement {\n  description\n  iconType\n  id\n  sequence\n  __typename\n}\n\nfragment StatusPaymentTransaction on Transaction {\n  id\n  operation\n  direction\n  providerId\n  status\n  statusDescription\n  statusExpirationDate\n  value\n  props {\n    paymentURL\n    __typename\n  }\n  __typename\n}\n\nfragment RegularForeignItem on ForeignItem {\n  ...ItemFields\n  __typename\n}', 'updateItem': 'mutation updateItem($input: UpdateItemInput!, $addedAttachments: [Upload!]) {\n  updateItem(input: $input, addedAttachments: $addedAttachments) {\n    ...RegularItem\n    __typename\n  }\n}\n\nfragment RegularItem on Item {\n  ...RegularMyItem\n  ...RegularForeignItem\n  __typename\n}\n\nfragment RegularMyItem on MyItem {\n  ...ItemFields\n  prevPrice\n  priority\n  sequence\n  priorityPrice\n  statusExpirationDate\n  comment\n  viewsCounter\n  statusDescription\n  editable\n  statusPayment {\n    ...StatusPaymentTransaction\n    __typename\n  }\n  moderator {\n    id\n    username\n    __typename\n  }\n  approvalDate\n  deletedAt\n  createdAt\n  updatedAt\n  mayBePublished\n  prevFeeMultiplier\n  sellerNotifiedAboutFeeChange\n  __typename\n}\n\nfragment ItemFields on Item {\n  id\n  slug\n  name\n  description\n  rawPrice\n  price\n  attributes\n  status\n  priorityPosition\n  sellerType\n  feeMultiplier\n  user {\n    ...ItemUser\n    __typename\n  }\n  buyer {\n    ...ItemUser\n    __typename\n  }\n  attachments {\n    ...PartialFile\n    __typename\n  }\n  category {\n    ...RegularGameCategory\n    __typename\n  }\n  game {\n    ...RegularGameProfile\n    __typename\n  }\n  comment\n  dataFields {\n    ...GameCategoryDataFieldWithValue\n    __typename\n  }\n  obtainingType {\n    ...GameCategoryObtainingType\n    __typename\n  }\n  __typename\n}\n\nfragment ItemUser on UserFragment {\n  ...UserEdgeNode\n  __typename\n}\n\nfragment UserEdgeNode on UserFragment {\n  ...RegularUserFragment\n  __typename\n}\n\nfragment RegularUserFragment on UserFragment {\n  id\n  username\n  role\n  avatarURL\n  isOnline\n  isBlocked\n  rating\n  testimonialCounter\n  createdAt\n  supportChatId\n  systemChatId\n  __typename\n}\n\nfragment PartialFile on File {\n  id\n  url\n  __typename\n}\n\nfragment RegularGameCategory on GameCategory {\n  id\n  slug\n  name\n  categoryId\n  gameId\n  obtaining\n  options {\n    ...RegularGameCategoryOption\n    __typename\n  }\n  props {\n    ...GameCategoryProps\n    __typename\n  }\n  noCommentFromBuyer\n  instructionForBuyer\n  instructionForSeller\n  useCustomObtaining\n  autoConfirmPeriod\n  autoModerationMode\n  agreements {\n    ...RegularGameCategoryAgreement\n    __typename\n  }\n  feeMultiplier\n  __typename\n}\n\nfragment RegularGameCategoryOption on GameCategoryOption {\n  id\n  group\n  label\n  type\n  field\n  value\n  valueRangeLimit {\n    min\n    max\n    __typename\n  }\n  __typename\n}\n\nfragment GameCategoryProps on GameCategoryPropsObjectType {\n  minTestimonials\n  minTestimonialsForSeller\n  __typename\n}\n\nfragment RegularGameCategoryAgreement on GameCategoryAgreement {\n  description\n  gameCategoryId\n  gameCategoryObtainingTypeId\n  iconType\n  id\n  sequence\n  __typename\n}\n\nfragment RegularGameProfile on GameProfile {\n  id\n  name\n  type\n  slug\n  logo {\n    ...PartialFile\n    __typename\n  }\n  __typename\n}\n\nfragment GameCategoryDataFieldWithValue on GameCategoryDataFieldWithValue {\n  id\n  label\n  type\n  inputType\n  copyable\n  hidden\n  required\n  value\n  __typename\n}\n\nfragment GameCategoryObtainingType on GameCategoryObtainingType {\n  id\n  name\n  description\n  gameCategoryId\n  noCommentFromBuyer\n  instructionForBuyer\n  instructionForSeller\n  sequence\n  feeMultiplier\n  agreements {\n    ...MinimalGameCategoryAgreement\n    __typename\n  }\n  props {\n    minTestimonialsForSeller\n    __typename\n  }\n  __typename\n}\n\nfragment MinimalGameCategoryAgreement on GameCategoryAgreement {\n  description\n  iconType\n  id\n  sequence\n  __typename\n}\n\nfragment StatusPaymentTransaction on Transaction {\n  id\n  operation\n  direction\n  providerId\n  status\n  statusDescription\n  statusExpirationDate\n  value\n  props {\n    paymentURL\n    __typename\n  }\n  __typename\n}\n\nfragment RegularForeignItem on ForeignItem {\n  ...ItemFields\n  __typename\n}', 'removeItem': 'mutation removeItem($id: UUID!) {\n  removeItem(id: $id) {\n    ...RegularItem\n    __typename\n  }\n}\n\nfragment RegularItem on Item {\n  ...RegularMyItem\n  ...RegularForeignItem\n  __typename\n}\n\nfragment RegularMyItem on MyItem {\n  ...ItemFields\n  prevPrice\n  priority\n  sequence\n  priorityPrice\n  statusExpirationDate\n  comment\n  viewsCounter\n  statusDescription\n  editable\n  statusPayment {\n    ...StatusPaymentTransaction\n    __typename\n  }\n  moderator {\n    id\n    username\n    __typename\n  }\n  approvalDate\n  deletedAt\n  createdAt\n  updatedAt\n  mayBePublished\n  prevFeeMultiplier\n  sellerNotifiedAboutFeeChange\n  __typename\n}\n\nfragment ItemFields on Item {\n  id\n  slug\n  name\n  description\n  rawPrice\n  price\n  attributes\n  status\n  priorityPosition\n  sellerType\n  feeMultiplier\n  user {\n    ...ItemUser\n    __typename\n  }\n  buyer {\n    ...ItemUser\n    __typename\n  }\n  attachments {\n    ...PartialFile\n    __typename\n  }\n  category {\n    ...RegularGameCategory\n    __typename\n  }\n  game {\n    ...RegularGameProfile\n    __typename\n  }\n  comment\n  dataFields {\n    ...GameCategoryDataFieldWithValue\n    __typename\n  }\n  obtainingType {\n    ...GameCategoryObtainingType\n    __typename\n  }\n  __typename\n}\n\nfragment ItemUser on UserFragment {\n  ...UserEdgeNode\n  __typename\n}\n\nfragment UserEdgeNode on UserFragment {\n  ...RegularUserFragment\n  __typename\n}\n\nfragment RegularUserFragment on UserFragment {\n  id\n  username\n  role\n  avatarURL\n  isOnline\n  isBlocked\n  rating\n  testimonialCounter\n  createdAt\n  supportChatId\n  systemChatId\n  __typename\n}\n\nfragment PartialFile on File {\n  id\n  url\n  __typename\n}\n\nfragment RegularGameCategory on GameCategory {\n  id\n  slug\n  name\n  categoryId\n  gameId\n  obtaining\n  options {\n    ...RegularGameCategoryOption\n    __typename\n  }\n  props {\n    ...GameCategoryProps\n    __typename\n  }\n  noCommentFromBuyer\n  instructionForBuyer\n  instructionForSeller\n  useCustomObtaining\n  autoConfirmPeriod\n  autoModerationMode\n  agreements {\n    ...RegularGameCategoryAgreement\n    __typename\n  }\n  feeMultiplier\n  __typename\n}\n\nfragment RegularGameCategoryOption on GameCategoryOption {\n  id\n  group\n  label\n  type\n  field\n  value\n  valueRangeLimit {\n    min\n    max\n    __typename\n  }\n  __typename\n}\n\nfragment GameCategoryProps on GameCategoryPropsObjectType {\n  minTestimonials\n  minTestimonialsForSeller\n  __typename\n}\n\nfragment RegularGameCategoryAgreement on GameCategoryAgreement {\n  description\n  gameCategoryId\n  gameCategoryObtainingTypeId\n  iconType\n  id\n  sequence\n  __typename\n}\n\nfragment RegularGameProfile on GameProfile {\n  id\n  name\n  type\n  slug\n  logo {\n    ...PartialFile\n    __typename\n  }\n  __typename\n}\n\nfragment GameCategoryDataFieldWithValue on GameCategoryDataFieldWithValue {\n  id\n  label\n  type\n  inputType\n  copyable\n  hidden\n  required\n  value\n  __typename\n}\n\nfragment GameCategoryObtainingType on GameCategoryObtainingType {\n  id\n  name\n  description\n  gameCategoryId\n  noCommentFromBuyer\n  instructionForBuyer\n  instructionForSeller\n  sequence\n  feeMultiplier\n  agreements {\n    ...MinimalGameCategoryAgreement\n    __typename\n  }\n  props {\n    minTestimonialsForSeller\n    __typename\n  }\n  __typename\n}\n\nfragment MinimalGameCategoryAgreement on GameCategoryAgreement {\n  description\n  iconType\n  id\n  sequence\n  __typename\n}\n\nfragment StatusPaymentTransaction on Transaction {\n  id\n  operation\n  direction\n  providerId\n  status\n  statusDescription\n  statusExpirationDate\n  value\n  props {\n    paymentURL\n    __typename\n  }\n  __typename\n}\n\nfragment RegularForeignItem on ForeignItem {\n  ...ItemFields\n  __typename\n}', 'publishItem': 'mutation publishItem($input: PublishItemInput!) {\n  publishItem(input: $input) {\n    ...RegularItem\n    __typename\n  }\n}\n\nfragment RegularItem on Item {\n  ...RegularMyItem\n  ...RegularForeignItem\n  __typename\n}\n\nfragment RegularMyItem on MyItem {\n  ...ItemFields\n  prevPrice\n  priority\n  sequence\n  priorityPrice\n  statusExpirationDate\n  comment\n  viewsCounter\n  statusDescription\n  editable\n  statusPayment {\n    ...StatusPaymentTransaction\n    __typename\n  }\n  moderator {\n    id\n    username\n    __typename\n  }\n  approvalDate\n  deletedAt\n  createdAt\n  updatedAt\n  mayBePublished\n  prevFeeMultiplier\n  sellerNotifiedAboutFeeChange\n  __typename\n}\n\nfragment ItemFields on Item {\n  id\n  slug\n  name\n  description\n  rawPrice\n  price\n  attributes\n  status\n  priorityPosition\n  sellerType\n  feeMultiplier\n  user {\n    ...ItemUser\n    __typename\n  }\n  buyer {\n    ...ItemUser\n    __typename\n  }\n  attachments {\n    ...PartialFile\n    __typename\n  }\n  category {\n    ...RegularGameCategory\n    __typename\n  }\n  game {\n    ...RegularGameProfile\n    __typename\n  }\n  comment\n  dataFields {\n    ...GameCategoryDataFieldWithValue\n    __typename\n  }\n  obtainingType {\n    ...GameCategoryObtainingType\n    __typename\n  }\n  __typename\n}\n\nfragment ItemUser on UserFragment {\n  ...UserEdgeNode\n  __typename\n}\n\nfragment UserEdgeNode on UserFragment {\n  ...RegularUserFragment\n  __typename\n}\n\nfragment RegularUserFragment on UserFragment {\n  id\n  username\n  role\n  avatarURL\n  isOnline\n  isBlocked\n  rating\n  testimonialCounter\n  createdAt\n  supportChatId\n  systemChatId\n  __typename\n}\n\nfragment PartialFile on File {\n  id\n  url\n  __typename\n}\n\nfragment RegularGameCategory on GameCategory {\n  id\n  slug\n  name\n  categoryId\n  gameId\n  obtaining\n  options {\n    ...RegularGameCategoryOption\n    __typename\n  }\n  props {\n    ...GameCategoryProps\n    __typename\n  }\n  noCommentFromBuyer\n  instructionForBuyer\n  instructionForSeller\n  useCustomObtaining\n  autoConfirmPeriod\n  autoModerationMode\n  agreements {\n    ...RegularGameCategoryAgreement\n    __typename\n  }\n  feeMultiplier\n  __typename\n}\n\nfragment RegularGameCategoryOption on GameCategoryOption {\n  id\n  group\n  label\n  type\n  field\n  value\n  valueRangeLimit {\n    min\n    max\n    __typename\n  }\n  __typename\n}\n\nfragment GameCategoryProps on GameCategoryPropsObjectType {\n  minTestimonials\n  minTestimonialsForSeller\n  __typename\n}\n\nfragment RegularGameCategoryAgreement on GameCategoryAgreement {\n  description\n  gameCategoryId\n  gameCategoryObtainingTypeId\n  iconType\n  id\n  sequence\n  __typename\n}\n\nfragment RegularGameProfile on GameProfile {\n  id\n  name\n  type\n  slug\n  logo {\n    ...PartialFile\n    __typename\n  }\n  __typename\n}\n\nfragment GameCategoryDataFieldWithValue on GameCategoryDataFieldWithValue {\n  id\n  label\n  type\n  inputType\n  copyable\n  hidden\n  required\n  value\n  __typename\n}\n\nfragment GameCategoryObtainingType on GameCategoryObtainingType {\n  id\n  name\n  description\n  gameCategoryId\n  noCommentFromBuyer\n  instructionForBuyer\n  instructionForSeller\n  sequence\n  feeMultiplier\n  agreements {\n    ...MinimalGameCategoryAgreement\n    __typename\n  }\n  props {\n    minTestimonialsForSeller\n    __typename\n  }\n  __typename\n}\n\nfragment MinimalGameCategoryAgreement on GameCategoryAgreement {\n  description\n  iconType\n  id\n  sequence\n  __typename\n}\n\nfragment StatusPaymentTransaction on Transaction {\n  id\n  operation\n  direction\n  providerId\n  status\n  statusDescription\n  statusExpirationDate\n  value\n  props {\n    paymentURL\n    __typename\n  }\n  __typename\n}\n\nfragment RegularForeignItem on ForeignItem {\n  ...ItemFields\n  __typename\n}', 'increaseItemPriorityStatus': 'mutation increaseItemPriorityStatus($input: PublishItemInput!) {\n  increaseItemPriorityStatus(input: $input) {\n    ...RegularItem\n    __typename\n  }\n}\n\nfragment RegularItem on Item {\n  ...RegularMyItem\n  ...RegularForeignItem\n  __typename\n}\n\nfragment RegularMyItem on MyItem {\n  ...ItemFields\n  prevPrice\n  priority\n  sequence\n  priorityPrice\n  statusExpirationDate\n  comment\n  viewsCounter\n  statusDescription\n  editable\n  statusPayment {\n    ...StatusPaymentTransaction\n    __typename\n  }\n  moderator {\n    id\n    username\n    __typename\n  }\n  approvalDate\n  deletedAt\n  createdAt\n  updatedAt\n  mayBePublished\n  prevFeeMultiplier\n  sellerNotifiedAboutFeeChange\n  __typename\n}\n\nfragment ItemFields on Item {\n  id\n  slug\n  name\n  description\n  rawPrice\n  price\n  attributes\n  status\n  priorityPosition\n  sellerType\n  feeMultiplier\n  user {\n    ...ItemUser\n    __typename\n  }\n  buyer {\n    ...ItemUser\n    __typename\n  }\n  attachments {\n    ...PartialFile\n    __typename\n  }\n  category {\n    ...RegularGameCategory\n    __typename\n  }\n  game {\n    ...RegularGameProfile\n    __typename\n  }\n  comment\n  dataFields {\n    ...GameCategoryDataFieldWithValue\n    __typename\n  }\n  obtainingType {\n    ...GameCategoryObtainingType\n    __typename\n  }\n  __typename\n}\n\nfragment ItemUser on UserFragment {\n  ...UserEdgeNode\n  __typename\n}\n\nfragment UserEdgeNode on UserFragment {\n  ...RegularUserFragment\n  __typename\n}\n\nfragment RegularUserFragment on UserFragment {\n  id\n  username\n  role\n  avatarURL\n  isOnline\n  isBlocked\n  rating\n  testimonialCounter\n  createdAt\n  supportChatId\n  systemChatId\n  __typename\n}\n\nfragment PartialFile on File {\n  id\n  url\n  __typename\n}\n\nfragment RegularGameCategory on GameCategory {\n  id\n  slug\n  name\n  categoryId\n  gameId\n  obtaining\n  options {\n    ...RegularGameCategoryOption\n    __typename\n  }\n  props {\n    ...GameCategoryProps\n    __typename\n  }\n  noCommentFromBuyer\n  instructionForBuyer\n  instructionForSeller\n  useCustomObtaining\n  autoConfirmPeriod\n  autoModerationMode\n  agreements {\n    ...RegularGameCategoryAgreement\n    __typename\n  }\n  feeMultiplier\n  __typename\n}\n\nfragment RegularGameCategoryOption on GameCategoryOption {\n  id\n  group\n  label\n  type\n  field\n  value\n  valueRangeLimit {\n    min\n    max\n    __typename\n  }\n  __typename\n}\n\nfragment GameCategoryProps on GameCategoryPropsObjectType {\n  minTestimonials\n  minTestimonialsForSeller\n  __typename\n}\n\nfragment RegularGameCategoryAgreement on GameCategoryAgreement {\n  description\n  gameCategoryId\n  gameCategoryObtainingTypeId\n  iconType\n  id\n  sequence\n  __typename\n}\n\nfragment RegularGameProfile on GameProfile {\n  id\n  name\n  type\n  slug\n  logo {\n    ...PartialFile\n    __typename\n  }\n  __typename\n}\n\nfragment GameCategoryDataFieldWithValue on GameCategoryDataFieldWithValue {\n  id\n  label\n  type\n  inputType\n  copyable\n  hidden\n  required\n  value\n  __typename\n}\n\nfragment GameCategoryObtainingType on GameCategoryObtainingType {\n  id\n  name\n  description\n  gameCategoryId\n  noCommentFromBuyer\n  instructionForBuyer\n  instructionForSeller\n  sequence\n  feeMultiplier\n  agreements {\n    ...MinimalGameCategoryAgreement\n    __typename\n  }\n  props {\n    minTestimonialsForSeller\n    __typename\n  }\n  __typename\n}\n\nfragment MinimalGameCategoryAgreement on GameCategoryAgreement {\n  description\n  iconType\n  id\n  sequence\n  __typename\n}\n\nfragment StatusPaymentTransaction on Transaction {\n  id\n  operation\n  direction\n  providerId\n  status\n  statusDescription\n  statusExpirationDate\n  value\n  props {\n    paymentURL\n    __typename\n  }\n  __typename\n}\n\nfragment RegularForeignItem on ForeignItem {\n  ...ItemFields\n  __typename\n}', 'deleteCard': 'mutation deleteCard($input: DeleteCardInput!) {\n  deleteCard(input: $input)\n}', 'requestWithdrawal': 'mutation requestWithdrawal($input: CreateWithdrawalTransactionInput!) {\n  requestWithdrawal(input: $input) {\n    ...RegularTransaction\n    __typename\n  }\n}\n\nfragment RegularTransaction on Transaction {\n  id\n  operation\n  direction\n  providerId\n  provider {\n    ...RegularTransactionProvider\n    __typename\n  }\n  user {\n    ...RegularUserFragment\n    __typename\n  }\n  creator {\n    ...RegularUserFragment\n    __typename\n  }\n  status\n  statusDescription\n  statusExpirationDate\n  value\n  fee\n  createdAt\n  props {\n    ...RegularTransactionProps\n    __typename\n  }\n  verifiedAt\n  verifiedBy {\n    ...UserEdgeNode\n    __typename\n  }\n  completedBy {\n    ...UserEdgeNode\n    __typename\n  }\n  paymentMethodId\n  completedAt\n  isSuspicious\n  spbBankName\n  __typename\n}\n\nfragment RegularTransactionProvider on TransactionProvider {\n  id\n  name\n  fee\n  minFeeAmount\n  description\n  account {\n    ...RegularTransactionProviderAccount\n    __typename\n  }\n  props {\n    ...TransactionProviderPropsFragment\n    __typename\n  }\n  limits {\n    ...ProviderLimits\n    __typename\n  }\n  paymentMethods {\n    ...TransactionPaymentMethod\n    __typename\n  }\n  __typename\n}\n\nfragment RegularTransactionProviderAccount on TransactionProviderAccount {\n  id\n  value\n  userId\n  providerId\n  paymentMethodId\n  __typename\n}\n\nfragment TransactionProviderPropsFragment on TransactionProviderPropsFragment {\n  requiredUserData {\n    ...TransactionProviderRequiredUserData\n    __typename\n  }\n  tooltip\n  __typename\n}\n\nfragment TransactionProviderRequiredUserData on TransactionProviderRequiredUserData {\n  email\n  phoneNumber\n  eripAccountNumber\n  __typename\n}\n\nfragment ProviderLimits on ProviderLimits {\n  incoming {\n    ...ProviderLimitRange\n    __typename\n  }\n  outgoing {\n    ...ProviderLimitRange\n    __typename\n  }\n  __typename\n}\n\nfragment ProviderLimitRange on ProviderLimitRange {\n  min\n  max\n  __typename\n}\n\nfragment TransactionPaymentMethod on TransactionPaymentMethod {\n  id\n  name\n  fee\n  providerId\n  account {\n    ...RegularTransactionProviderAccount\n    __typename\n  }\n  props {\n    ...TransactionProviderPropsFragment\n    __typename\n  }\n  limits {\n    ...ProviderLimits\n    __typename\n  }\n  __typename\n}\n\nfragment RegularUserFragment on UserFragment {\n  id\n  username\n  role\n  avatarURL\n  isOnline\n  isBlocked\n  rating\n  testimonialCounter\n  createdAt\n  supportChatId\n  systemChatId\n  __typename\n}\n\nfragment RegularTransactionProps on TransactionPropsFragment {\n  creatorId\n  dealId\n  paidFromPendingIncome\n  paymentURL\n  successURL\n  fee\n  paymentAccount {\n    id\n    value\n    __typename\n  }\n  paymentGateway\n  alreadySpent\n  exchangeRate\n  amountAfterConversionRub\n  amountAfterConversionUsdt\n  userData {\n    account\n    email\n    ipAddress\n    phoneNumber\n    __typename\n  }\n  __typename\n}\n\nfragment UserEdgeNode on UserFragment {\n  ...RegularUserFragment\n  __typename\n}', 'removeTransaction': 'mutation removeTransaction($id: UUID!) {\n  removeTransaction(id: $id) {\n    ...RegularTransaction\n    __typename\n  }\n}\n\nfragment RegularTransaction on Transaction {\n  id\n  operation\n  direction\n  providerId\n  provider {\n    ...RegularTransactionProvider\n    __typename\n  }\n  user {\n    ...RegularUserFragment\n    __typename\n  }\n  creator {\n    ...RegularUserFragment\n    __typename\n  }\n  status\n  statusDescription\n  statusExpirationDate\n  value\n  fee\n  createdAt\n  props {\n    ...RegularTransactionProps\n    __typename\n  }\n  verifiedAt\n  verifiedBy {\n    ...UserEdgeNode\n    __typename\n  }\n  completedBy {\n    ...UserEdgeNode\n    __typename\n  }\n  paymentMethodId\n  completedAt\n  isSuspicious\n  spbBankName\n  __typename\n}\n\nfragment RegularTransactionProvider on TransactionProvider {\n  id\n  name\n  fee\n  minFeeAmount\n  description\n  account {\n    ...RegularTransactionProviderAccount\n    __typename\n  }\n  props {\n    ...TransactionProviderPropsFragment\n    __typename\n  }\n  limits {\n    ...ProviderLimits\n    __typename\n  }\n  paymentMethods {\n    ...TransactionPaymentMethod\n    __typename\n  }\n  __typename\n}\n\nfragment RegularTransactionProviderAccount on TransactionProviderAccount {\n  id\n  value\n  userId\n  providerId\n  paymentMethodId\n  __typename\n}\n\nfragment TransactionProviderPropsFragment on TransactionProviderPropsFragment {\n  requiredUserData {\n    ...TransactionProviderRequiredUserData\n    __typename\n  }\n  tooltip\n  __typename\n}\n\nfragment TransactionProviderRequiredUserData on TransactionProviderRequiredUserData {\n  email\n  phoneNumber\n  eripAccountNumber\n  __typename\n}\n\nfragment ProviderLimits on ProviderLimits {\n  incoming {\n    ...ProviderLimitRange\n    __typename\n  }\n  outgoing {\n    ...ProviderLimitRange\n    __typename\n  }\n  __typename\n}\n\nfragment ProviderLimitRange on ProviderLimitRange {\n  min\n  max\n  __typename\n}\n\nfragment TransactionPaymentMethod on TransactionPaymentMethod {\n  id\n  name\n  fee\n  providerId\n  account {\n    ...RegularTransactionProviderAccount\n    __typename\n  }\n  props {\n    ...TransactionProviderPropsFragment\n    __typename\n  }\n  limits {\n    ...ProviderLimits\n    __typename\n  }\n  __typename\n}\n\nfragment RegularUserFragment on UserFragment {\n  id\n  username\n  role\n  avatarURL\n  isOnline\n  isBlocked\n  rating\n  testimonialCounter\n  createdAt\n  supportChatId\n  systemChatId\n  __typename\n}\n\nfragment RegularTransactionProps on TransactionPropsFragment {\n  creatorId\n  dealId\n  paidFromPendingIncome\n  paymentURL\n  successURL\n  fee\n  paymentAccount {\n    id\n    value\n    __typename\n  }\n  paymentGateway\n  alreadySpent\n  exchangeRate\n  amountAfterConversionRub\n  amountAfterConversionUsdt\n  userData {\n    account\n    email\n    ipAddress\n    phoneNumber\n    __typename\n  }\n  __typename\n}\n\nfragment UserEdgeNode on UserFragment {\n  ...RegularUserFragment\n  __typename\n}', 'chatUpdated': 'subscription chatUpdated($filter: ChatFilter, $showForbiddenImage: Boolean) {\n  chatUpdated(filter: $filter) {\n    ...ChatUpdatedFields\n    __typename\n  }\n}\n\nfragment ChatUpdatedFields on Chat {\n  id\n  unreadMessagesCounter\n  isTextingAllowed\n  lastMessage {\n    ...LastChatMessageFields\n    __typename\n  }\n  status\n  startedAt\n  finishedAt\n  __typename\n}\n\nfragment LastChatMessageFields on ChatMessage {\n  id\n  text\n  createdAt\n  isRead\n  isBulkMessaging\n  event\n  file {\n    ...RegularFile\n    __typename\n  }\n  images {\n    ...RegularFile\n    __typename\n  }\n  user {\n    ...ChatMessageUserFields\n    __typename\n  }\n  eventByUser {\n    ...ChatMessageUserFields\n    __typename\n  }\n  eventToUser {\n    ...ChatMessageUserFields\n    __typename\n  }\n  deal {\n    ...ChatMessageItemDeal\n    __typename\n  }\n  __typename\n}\n\nfragment RegularFile on File {\n  id\n  url\n  filename\n  mime\n  __typename\n}\n\nfragment ChatMessageUserFields on UserFragment {\n  ...UserEdgeNode\n  __typename\n}\n\nfragment UserEdgeNode on UserFragment {\n  ...RegularUserFragment\n  __typename\n}\n\nfragment RegularUserFragment on UserFragment {\n  id\n  username\n  role\n  avatarURL\n  isOnline\n  isBlocked\n  rating\n  testimonialCounter\n  createdAt\n  supportChatId\n  systemChatId\n  __typename\n}\n\nfragment ChatMessageItemDeal on ItemDeal {\n  id\n  direction\n  status\n  statusDescription\n  hasProblem\n  user {\n    ...ChatParticipant\n    __typename\n  }\n  testimonial {\n    ...ChatMessageDealTestimonial\n    __typename\n  }\n  item {\n    id\n    name\n    price\n    slug\n    rawPrice\n    sellerType\n    user {\n      ...ChatParticipant\n      __typename\n    }\n    category {\n      id\n      __typename\n    }\n    attachments(showForbiddenImage: $showForbiddenImage) {\n      ...PartialFile\n      __typename\n    }\n    isAttachmentsForbidden\n    comment\n    dataFields {\n      ...GameCategoryDataFieldWithValue\n      __typename\n    }\n    obtainingType {\n      ...GameCategoryObtainingType\n      __typename\n    }\n    __typename\n  }\n  obtainingFields {\n    ...GameCategoryDataFieldWithValue\n    __typename\n  }\n  chat {\n    id\n    type\n    __typename\n  }\n  transaction {\n    id\n    statusExpirationDate\n    __typename\n  }\n  statusExpirationDate\n  commentFromBuyer\n  gameCategoryWarnings {\n    ...ItemDealWarningFragment\n    __typename\n  }\n  obtainingTypeWarnings {\n    ...ItemDealWarningFragment\n    __typename\n  }\n  __typename\n}\n\nfragment ChatParticipant on UserFragment {\n  ...RegularUserFragment\n  __typename\n}\n\nfragment ChatMessageDealTestimonial on Testimonial {\n  id\n  status\n  text\n  rating\n  createdAt\n  updatedAt\n  creator {\n    ...RegularUserFragment\n    __typename\n  }\n  moderator {\n    ...RegularUserFragment\n    __typename\n  }\n  user {\n    ...RegularUserFragment\n    __typename\n  }\n  __typename\n}\n\nfragment PartialFile on File {\n  id\n  url\n  __typename\n}\n\nfragment GameCategoryDataFieldWithValue on GameCategoryDataFieldWithValue {\n  id\n  label\n  type\n  inputType\n  copyable\n  hidden\n  required\n  value\n  __typename\n}\n\nfragment GameCategoryObtainingType on GameCategoryObtainingType {\n  id\n  name\n  description\n  gameCategoryId\n  noCommentFromBuyer\n  instructionForBuyer\n  instructionForSeller\n  sequence\n  feeMultiplier\n  agreements {\n    ...MinimalGameCategoryAgreement\n    __typename\n  }\n  props {\n    minTestimonialsForSeller\n    __typename\n  }\n  __typename\n}\n\nfragment MinimalGameCategoryAgreement on GameCategoryAgreement {\n  description\n  iconType\n  id\n  sequence\n  __typename\n}\n\nfragment ItemDealWarningFragment on ItemDealWarning {\n  id\n  status\n  title\n  text\n  __typename\n}', 'chatMarkedAsRead': 'subscription chatMarkedAsRead($filter: ChatFilter, $showForbiddenImage: Boolean) {\n  chatMarkedAsRead(filter: $filter) {\n    ...ChatUpdatedFields\n    __typename\n  }\n}\n\nfragment ChatUpdatedFields on Chat {\n  id\n  unreadMessagesCounter\n  isTextingAllowed\n  lastMessage {\n    ...LastChatMessageFields\n    __typename\n  }\n  status\n  startedAt\n  finishedAt\n  __typename\n}\n\nfragment LastChatMessageFields on ChatMessage {\n  id\n  text\n  createdAt\n  isRead\n  isBulkMessaging\n  event\n  file {\n    ...RegularFile\n    __typename\n  }\n  images {\n    ...RegularFile\n    __typename\n  }\n  user {\n    ...ChatMessageUserFields\n    __typename\n  }\n  eventByUser {\n    ...ChatMessageUserFields\n    __typename\n  }\n  eventToUser {\n    ...ChatMessageUserFields\n    __typename\n  }\n  deal {\n    ...ChatMessageItemDeal\n    __typename\n  }\n  __typename\n}\n\nfragment RegularFile on File {\n  id\n  url\n  filename\n  mime\n  __typename\n}\n\nfragment ChatMessageUserFields on UserFragment {\n  ...UserEdgeNode\n  __typename\n}\n\nfragment UserEdgeNode on UserFragment {\n  ...RegularUserFragment\n  __typename\n}\n\nfragment RegularUserFragment on UserFragment {\n  id\n  username\n  role\n  avatarURL\n  isOnline\n  isBlocked\n  rating\n  testimonialCounter\n  createdAt\n  supportChatId\n  systemChatId\n  __typename\n}\n\nfragment ChatMessageItemDeal on ItemDeal {\n  id\n  direction\n  status\n  statusDescription\n  hasProblem\n  user {\n    ...ChatParticipant\n    __typename\n  }\n  testimonial {\n    ...ChatMessageDealTestimonial\n    __typename\n  }\n  item {\n    id\n    name\n    price\n    slug\n    rawPrice\n    sellerType\n    user {\n      ...ChatParticipant\n      __typename\n    }\n    category {\n      id\n      __typename\n    }\n    attachments(showForbiddenImage: $showForbiddenImage) {\n      ...PartialFile\n      __typename\n    }\n    isAttachmentsForbidden\n    comment\n    dataFields {\n      ...GameCategoryDataFieldWithValue\n      __typename\n    }\n    obtainingType {\n      ...GameCategoryObtainingType\n      __typename\n    }\n    __typename\n  }\n  obtainingFields {\n    ...GameCategoryDataFieldWithValue\n    __typename\n  }\n  chat {\n    id\n    type\n    __typename\n  }\n  transaction {\n    id\n    statusExpirationDate\n    __typename\n  }\n  statusExpirationDate\n  commentFromBuyer\n  gameCategoryWarnings {\n    ...ItemDealWarningFragment\n    __typename\n  }\n  obtainingTypeWarnings {\n    ...ItemDealWarningFragment\n    __typename\n  }\n  __typename\n}\n\nfragment ChatParticipant on UserFragment {\n  ...RegularUserFragment\n  __typename\n}\n\nfragment ChatMessageDealTestimonial on Testimonial {\n  id\n  status\n  text\n  rating\n  createdAt\n  updatedAt\n  creator {\n    ...RegularUserFragment\n    __typename\n  }\n  moderator {\n    ...RegularUserFragment\n    __typename\n  }\n  user {\n    ...RegularUserFragment\n    __typename\n  }\n  __typename\n}\n\nfragment PartialFile on File {\n  id\n  url\n  __typename\n}\n\nfragment GameCategoryDataFieldWithValue on GameCategoryDataFieldWithValue {\n  id\n  label\n  type\n  inputType\n  copyable\n  hidden\n  required\n  value\n  __typename\n}\n\nfragment GameCategoryObtainingType on GameCategoryObtainingType {\n  id\n  name\n  description\n  gameCategoryId\n  noCommentFromBuyer\n  instructionForBuyer\n  instructionForSeller\n  sequence\n  feeMultiplier\n  agreements {\n    ...MinimalGameCategoryAgreement\n    __typename\n  }\n  props {\n    minTestimonialsForSeller\n    __typename\n  }\n  __typename\n}\n\nfragment MinimalGameCategoryAgreement on GameCategoryAgreement {\n  description\n  iconType\n  id\n  sequence\n  __typename\n}\n\nfragment ItemDealWarningFragment on ItemDealWarning {\n  id\n  status\n  title\n  text\n  __typename\n}', 'userUpdated': 'subscription userUpdated($userId: UUID) {\n  userUpdated(userId: $userId) {\n    ...PartialUserProfile\n    __typename\n  }\n}\n\nfragment PartialUserProfile on UserProfile {\n  __typename\n  ...PartialUser\n  ...PartialUserFragment\n}\n\nfragment PartialUser on User {\n  id\n  unreadChatsCounter\n  __typename\n}\n\nfragment PartialUserFragment on UserFragment {\n  id\n  __typename\n}', 'chatMessageCreated': 'subscription chatMessageCreated($filter: ChatMessageWSFilter!, $showForbiddenImage: Boolean) {\n  chatMessageCreated(filter: $filter) {\n    ...RegularChatMessage\n    __typename\n  }\n}\n\nfragment RegularChatMessage on ChatMessage {\n  id\n  text\n  createdAt\n  deletedAt\n  isRead\n  isSuspicious\n  isBulkMessaging\n  game {\n    ...RegularGameProfile\n    __typename\n  }\n  file {\n    ...PartialFile\n    __typename\n  }\n  user {\n    ...ChatMessageUserFields\n    __typename\n  }\n  deal {\n    ...ChatMessageItemDeal\n    __typename\n  }\n  item {\n    ...ItemEdgeNode\n    __typename\n  }\n  transaction {\n    ...RegularTransaction\n    __typename\n  }\n  moderator {\n    ...UserEdgeNode\n    __typename\n  }\n  eventByUser {\n    ...ChatMessageUserFields\n    __typename\n  }\n  eventToUser {\n    ...ChatMessageUserFields\n    __typename\n  }\n  isAutoResponse\n  event\n  buttons {\n    ...ChatMessageButton\n    __typename\n  }\n  images {\n    ...RegularFile\n    __typename\n  }\n  __typename\n}\n\nfragment RegularGameProfile on GameProfile {\n  id\n  name\n  type\n  slug\n  logo {\n    ...PartialFile\n    __typename\n  }\n  __typename\n}\n\nfragment PartialFile on File {\n  id\n  url\n  __typename\n}\n\nfragment ChatMessageUserFields on UserFragment {\n  ...UserEdgeNode\n  __typename\n}\n\nfragment UserEdgeNode on UserFragment {\n  ...RegularUserFragment\n  __typename\n}\n\nfragment RegularUserFragment on UserFragment {\n  id\n  username\n  role\n  avatarURL\n  isOnline\n  isBlocked\n  rating\n  testimonialCounter\n  createdAt\n  supportChatId\n  systemChatId\n  __typename\n}\n\nfragment ChatMessageItemDeal on ItemDeal {\n  id\n  direction\n  status\n  statusDescription\n  hasProblem\n  user {\n    ...ChatParticipant\n    __typename\n  }\n  testimonial {\n    ...ChatMessageDealTestimonial\n    __typename\n  }\n  item {\n    id\n    name\n    price\n    slug\n    rawPrice\n    sellerType\n    user {\n      ...ChatParticipant\n      __typename\n    }\n    category {\n      id\n      __typename\n    }\n    attachments(showForbiddenImage: $showForbiddenImage) {\n      ...PartialFile\n      __typename\n    }\n    isAttachmentsForbidden\n    comment\n    dataFields {\n      ...GameCategoryDataFieldWithValue\n      __typename\n    }\n    obtainingType {\n      ...GameCategoryObtainingType\n      __typename\n    }\n    __typename\n  }\n  obtainingFields {\n    ...GameCategoryDataFieldWithValue\n    __typename\n  }\n  chat {\n    id\n    type\n    __typename\n  }\n  transaction {\n    id\n    statusExpirationDate\n    __typename\n  }\n  statusExpirationDate\n  commentFromBuyer\n  gameCategoryWarnings {\n    ...ItemDealWarningFragment\n    __typename\n  }\n  obtainingTypeWarnings {\n    ...ItemDealWarningFragment\n    __typename\n  }\n  __typename\n}\n\nfragment ChatParticipant on UserFragment {\n  ...RegularUserFragment\n  __typename\n}\n\nfragment ChatMessageDealTestimonial on Testimonial {\n  id\n  status\n  text\n  rating\n  createdAt\n  updatedAt\n  creator {\n    ...RegularUserFragment\n    __typename\n  }\n  moderator {\n    ...RegularUserFragment\n    __typename\n  }\n  user {\n    ...RegularUserFragment\n    __typename\n  }\n  __typename\n}\n\nfragment GameCategoryDataFieldWithValue on GameCategoryDataFieldWithValue {\n  id\n  label\n  type\n  inputType\n  copyable\n  hidden\n  required\n  value\n  __typename\n}\n\nfragment GameCategoryObtainingType on GameCategoryObtainingType {\n  id\n  name\n  description\n  gameCategoryId\n  noCommentFromBuyer\n  instructionForBuyer\n  instructionForSeller\n  sequence\n  feeMultiplier\n  agreements {\n    ...MinimalGameCategoryAgreement\n    __typename\n  }\n  props {\n    minTestimonialsForSeller\n    __typename\n  }\n  __typename\n}\n\nfragment MinimalGameCategoryAgreement on GameCategoryAgreement {\n  description\n  iconType\n  id\n  sequence\n  __typename\n}\n\nfragment ItemDealWarningFragment on ItemDealWarning {\n  id\n  status\n  title\n  text\n  __typename\n}\n\nfragment ItemEdgeNode on ItemProfile {\n  ...MyItemEdgeNode\n  ...ForeignItemEdgeNode\n  __typename\n}\n\nfragment MyItemEdgeNode on MyItemProfile {\n  id\n  slug\n  priority\n  status\n  name\n  price\n  rawPrice\n  statusExpirationDate\n  sellerType\n  attachment(showForbiddenImage: $showForbiddenImage) {\n    ...PartialFile\n    __typename\n  }\n  isAttachmentsForbidden\n  user {\n    ...UserItemEdgeNode\n    __typename\n  }\n  game {\n    name\n    __typename\n  }\n  category {\n    name\n    __typename\n  }\n  approvalDate\n  createdAt\n  priorityPosition\n  viewsCounter\n  dealsCounter\n  feeMultiplier\n  __typename\n}\n\nfragment UserItemEdgeNode on UserFragment {\n  ...UserEdgeNode\n  __typename\n}\n\nfragment ForeignItemEdgeNode on ForeignItemProfile {\n  id\n  slug\n  priority\n  status\n  name\n  price\n  rawPrice\n  sellerType\n  attachment(showForbiddenImage: $showForbiddenImage) {\n    ...PartialFile\n    __typename\n  }\n  isAttachmentsForbidden\n  user {\n    ...UserItemEdgeNode\n    __typename\n  }\n  game {\n    name\n    __typename\n  }\n  category {\n    name\n    __typename\n  }\n  approvalDate\n  priorityPosition\n  createdAt\n  viewsCounter\n  dealsCounter\n  feeMultiplier\n  __typename\n}\n\nfragment RegularTransaction on Transaction {\n  id\n  operation\n  direction\n  providerId\n  provider {\n    ...RegularTransactionProvider\n    __typename\n  }\n  user {\n    ...RegularUserFragment\n    __typename\n  }\n  creator {\n    ...RegularUserFragment\n    __typename\n  }\n  status\n  statusDescription\n  statusExpirationDate\n  value\n  fee\n  createdAt\n  props {\n    ...RegularTransactionProps\n    __typename\n  }\n  verifiedAt\n  verifiedBy {\n    ...UserEdgeNode\n    __typename\n  }\n  completedBy {\n    ...UserEdgeNode\n    __typename\n  }\n  paymentMethodId\n  completedAt\n  isSuspicious\n  spbBankName\n  autoClaimedAt\n  __typename\n}\n\nfragment RegularTransactionProvider on TransactionProvider {\n  id\n  name\n  fee\n  minFeeAmount\n  description\n  account {\n    ...RegularTransactionProviderAccount\n    __typename\n  }\n  props {\n    ...TransactionProviderPropsFragment\n    __typename\n  }\n  limits {\n    ...ProviderLimits\n    __typename\n  }\n  paymentMethods {\n    ...TransactionPaymentMethod\n    __typename\n  }\n  __typename\n}\n\nfragment RegularTransactionProviderAccount on TransactionProviderAccount {\n  id\n  value\n  userId\n  providerId\n  paymentMethodId\n  __typename\n}\n\nfragment TransactionProviderPropsFragment on TransactionProviderPropsFragment {\n  requiredUserData {\n    ...TransactionProviderRequiredUserData\n    __typename\n  }\n  tooltip\n  __typename\n}\n\nfragment TransactionProviderRequiredUserData on TransactionProviderRequiredUserData {\n  email\n  phoneNumber\n  eripAccountNumber\n  __typename\n}\n\nfragment ProviderLimits on ProviderLimits {\n  incoming {\n    ...ProviderLimitRange\n    __typename\n  }\n  outgoing {\n    ...ProviderLimitRange\n    __typename\n  }\n  __typename\n}\n\nfragment ProviderLimitRange on ProviderLimitRange {\n  min\n  max\n  __typename\n}\n\nfragment TransactionPaymentMethod on TransactionPaymentMethod {\n  id\n  name\n  fee\n  providerId\n  account {\n    ...RegularTransactionProviderAccount\n    __typename\n  }\n  props {\n    ...TransactionProviderPropsFragment\n    __typename\n  }\n  limits {\n    ...ProviderLimits\n    __typename\n  }\n  __typename\n}\n\nfragment RegularTransactionProps on TransactionPropsFragment {\n  creatorId\n  dealId\n  paidFromPendingIncome\n  paymentURL\n  successURL\n  fee\n  paymentAccount {\n    id\n    value\n    __typename\n  }\n  paymentGateway\n  alreadySpent\n  exchangeRate\n  amountAfterConversionRub\n  amountAfterConversionUsdt\n  userData {\n    account\n    email\n    ipAddress\n    phoneNumber\n    __typename\n  }\n  __typename\n}\n\nfragment ChatMessageButton on ChatMessageButton {\n  type\n  url\n  text\n  __typename\n}\n\nfragment RegularFile on File {\n  id\n  url\n  filename\n  mime\n  __typename\n}'}
from typing import TYPE_CHECKING
from .defs import *
if TYPE_CHECKING:
    from .models import *

def decode_account_profile(data: dict) -> 'AccountProfile':
    from .models import AccountProfile
    if not data:
        return None
    profile: dict = data.get('profile', {})
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
    return ItemDeal(id=data.get('id'), status=DealStage.__members__.get(data.get('status')), status_expiration_date=data.get('statusExpirationDate'), status_description=data.get('statusDescription'), direction=DealFlow.__members__.get(data.get('direction')), obtaining=data.get('obtaining'), has_problem=data.get('hasProblem'), report_problem_enabled=data.get('reportProblemEnabled'), completed_user=decode_user_profile(data.get('completedBy')), props=data.get('props'), previous_status=data.get('prevStatus'), completed_at=data.get('completedAt'), created_at=data.get('createdAt'), logs=logs, transaction=decode_transaction(data.get('transaction')), user=decode_user_profile(data.get('user')), chat=decode_chat(data.get('chat')), item=decode_item(data.get('item')), review=decode_review(data.get('testimonial')), obtaining_fields=obtaining_fields, comment_from_buyer=data.get('commentFromBuyer'))

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
    edges: dict[dict] = data.get('edges')
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
    return Item(id=data.get('id'), slug=data.get('slug'), name=data.get('name'), description=data.get('description'), obtaining_type=decode_category_obtaining_type(data.get('obtainingType')), price=data.get('price'), raw_price=data.get('rawPrice'), priority_position=data.get('priorityPosition'), attachments=attachments, attributes=data.get('attributes'), category=decode_game_category(data.get('category')), comment=data.get('comment'), data_fields=data_fields, fee_multiplier=data.get('feeMultiplier'), game=decode_game_profile(data.get('game')), seller_type=data.get('sellerType'), status=ListingStage.__members__.get(data.get('status')), user=decode_user_profile(data.get('user')))

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
    return MyItem(id=data.get('id'), slug=data.get('slug'), name=data.get('name'), description=data.get('description'), obtaining_type=decode_category_obtaining_type(data.get('obtainingType')), price=data.get('price'), prev_price=data.get('prevPrice'), raw_price=data.get('rawPrice'), priority_position=data.get('priorityPosition'), attachments=attachments, attributes=data.get('attributes'), buyer=decode_user_profile(data.get('buyer')), category=decode_game_category(data.get('category')), comment=data.get('comment'), data_fields=data_fields, fee_multiplier=data.get('feeMultiplier'), prev_fee_multiplier=data.get('prevFeeMultiplier'), seller_notified_about_fee_change=data.get('sellerNotifiedAboutFeeChange'), game=decode_game_profile(data.get('game')), seller_type=data.get('sellerType'), status=ListingStage.__members__.get(data.get('status')), user=decode_user_profile(data.get('user')), priority=BoostLevel.__members__.get(data.get('priority')), priority_price=data.get('priorityPrice'), sequence=data.get('sequence'), status_expiration_date=data.get('statusExpirationDate'), status_description=data.get('statusDescription'), status_payment=decode_transaction(data.get('statusPayment')), views_counter=data.get('viewsCounter'), is_editable=data.get('isEditable'), approval_date=data.get('approvalDate'), deleted_at=data.get('deletedAt'), updated_at=data.get('updatedAt'), created_at=data.get('createdAt'))

def decode_item_profile(data: dict) -> 'ItemProfile':
    from .models import ItemProfile
    if not data:
        return None
    return ItemProfile(id=data.get('id'), slug=data.get('slug'), priority=BoostLevel.__members__.get(data.get('priority')), status=ListingStage.__members__.get(data.get('status')), name=data.get('name'), price=data.get('price'), raw_price=data.get('rawPrice'), seller_type=AccountRole.__members__.get(data.get('sellerType')), attachment=decode_file_object(data.get('attachment')), user=decode_user_profile(data.get('user')), approval_date=data.get('approvalDate'), priority_position=data.get('priorityPosition'), views_counter=data.get('viewsCounter'), fee_multiplier=data.get('feeMultiplier'), created_at=data.get('createdAt'))

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
    edges: dict[dict] = data.get('edges')
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
    for row in data.get('images') or []:
        if row:
            fo = decode_file_object(row)
            if fo:
                imgs.append(fo)
    return ChatMessage(id=data.get('id'), text=data.get('text'), created_at=data.get('createdAt'), deleted_at=data.get('deletedAt'), is_read=data.get('isRead'), is_suspicious=data.get('isSuspicious'), is_bulk_messaging=data.get('isBulkMessaging'), file=decode_file_object(data.get('file')), game=decode_game(data.get('game')), images=imgs, user=decode_user_profile(data.get('user')), deal=decode_item_deal(data.get('deal')), item=decode_item(data.get('item')), transaction=decode_transaction(data.get('transaction')), moderator=decode_moderator(data.get('moderator')), event=decode_stream_event(data.get('event')), event_by_user=decode_user_profile(data.get('eventByUser')), event_to_user=decode_user_profile(data.get('eventToUser')), is_auto_response=data.get('isAutoResponse'), buttons=btns)

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
    edges: dict[dict] = data.get('edges')
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
    edges: dict[dict] = data.get('edges')
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
    edges: dict[dict] = data.get('edges')
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
    edges: dict[dict] = data.get('edges')
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
    edges: dict[dict] = data.get('edges')
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
    return GameCategoryOption(id=data.get('id'), group=data.get('group'), label=data.get('label'), type=OptionStyle.__members__.get(data.get('type')), field=data.get('field'), value=data.get('value'), value_range_limit=data.get('valueRangeLimit'))

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
    edges: dict[dict] = data.get('edges')
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
    return GameCategoryObtainingType(id=data.get('id'), name=data.get('name'), description=data.get('description'), game_category_id=data.get('gameCategoryId'), no_comment_from_buyer=data.get('noCommentFromBuyer'), instruction_for_buyer=data.get('instructionForBuyer'), instruction_for_seller=data.get('instructionForSeller'), sequence=data.get('sequence'), fee_multiplier=data.get('feeMultiplier'), agreements=agrs, props=decode_category_props(data.get('props')))

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
    edges: dict[dict] = data.get('edges')
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
    edges: dict[dict] = data.get('edges')
    if edges:
        for edge in edges:
            instructions.append(decode_category_instruction(edge.get('node')))
    return GameCategoryInstructionList(instructions=instructions, page_info=decode_category_instruction_page_info(data.get('pageInfo')), total_count=data.get('totalCount'))

def decode_transaction(data: dict) -> 'Transaction':
    from .models import Transaction
    if not data:
        return None
    return Transaction(id=data.get('id'), operation=TxKind.__members__.get(data.get('operation')), direction=TransactionDirections.__members__.get(data.get('direction')), provider_id=PayGateway.__members__.get(data.get('providerId')), provider=decode_transaction_provider(data.get('provider')), user=decode_user_profile(data.get('user')), creator=decode_user_profile(data.get('creator')), status=TxStage.__members__.get(data.get('status')), status_description=data.get('statusDescription'), status_expiration_date=data.get('statusExpirationDate'), value=data.get('value'), fee=data.get('fee'), created_at=data.get('createdAt'), verified_at=data.get('verified_at'), verified_by=data.get('verified_by'), completed_at=data.get('completed_at'), completed_by=data.get('completed_by'), payment_method_id=data.get('paymentMethodId'), is_suspicious=data.get('is_suspicious'), sbp_bank_name=data.get('spb_bank_name'))

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
    return TransactionPaymentMethod(id=PayMethod.__members__.get(data.get('id')), name=data.get('name'), fee=data.get('fee'), provider_id=PayGateway.__members__.get(data.get('providerId') or data.get('provider_id')), account=decode_account_profile(data.get('account')), props=decode_transaction_provider_props(data.get('props')), limits=decode_transaction_provider_limits(data.get('limits')))

def decode_transaction_provider(data: dict) -> 'TransactionProvider':
    from .models import TransactionProvider
    if not data:
        return None
    return TransactionProvider(id=PayGateway.__members__.get(data.get('id')), name=data.get('name'), fee=data.get('fee'), min_fee_amount=data.get('minFeeAmount'), description=data.get('description'), account=decode_account_profile(data.get('account')), props=decode_transaction_provider_props(data.get('props')), limits=decode_transaction_provider_limits(data.get('limits')), payment_methods=[decode_transaction_payment_method(method) for method in data.get('paymentMethods')])

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
    ...

def decode_file_object(data: dict) -> 'FileObject':
    from .models import FileObject
    if not data:
        return None
    return FileObject(id=data.get('id'), url=data.get('url'), filename=data.get('filename'), mime=data.get('mime'))
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
