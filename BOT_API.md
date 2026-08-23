# Telegram Bot API features (2026) vs Obra

Sources: core.telegram.org/bots/api-changelog (through **Bot API 10.2**, July 14, 2026).

## Bot API 9.4 (Feb 2026)
| Feature | In Obra? |
|---------|----------|
| Button `style`: primary / success / danger | ✅ Welcome + confirm/cancel |
| `icon_custom_emoji_id` on buttons | ⚪ optional later (needs premium/fragment) |

## Bot API 10.0 (May 2026)
| Feature | In Obra? |
|---------|----------|
| Guest mode / answerGuestQuery | ⚪ not wired (needs guest flow product design) |
| deleteMessageReaction / deleteAllMessageReactions | ✅ helper available |
| Media polls / members_only polls | ⚪ basic sendPoll only |
| Live photos sendLivePhoto | ⚪ not needed for AI text agent |
| sendMessageDraft empty text | ⚪ we use Rich drafts instead |
| Bot-to-bot messaging | ⚪ optional |

## Bot API 10.1 (June 2026)
| Feature | In Obra? |
|---------|----------|
| **sendRichMessage** (32k, headings, tables, details, math) | ✅ |
| **sendRichMessageDraft** + `<tg-thinking>` | ✅ |
| editMessageText + rich_message | ⚪ partial (send path primary) |
| InputRichMessage markdown/html/blocks | ✅ markdown + html |
| Join request queries / guard bot | ⚪ not wired |
| Poll option links | ⚪ basic polls |

## Bot API 10.2 (July 2026)
| Feature | In Obra? |
|---------|----------|
| Rich blocks + media field | ✅ via html/markdown path |
| **Ephemeral messages** (group whisper to one user) | ✅ `receiver_user_id` helper |
| edit/delete ephemeral | ⚪ helper stub |
| Communities types | ⚪ listen-only later |
| Subscription updates | ⚪ not a paid bot yet |
| Mini App origin lock | ⚪ host config |

## Always-on (older API, used heavily)
- Inline keyboards, callbacks, commands menu
- sendPoll, documents, photos, voice
- setMessageReaction
- Webhook + polling
- Mini App web_app_data path

Legend: ✅ in code · ⚪ not productized yet
