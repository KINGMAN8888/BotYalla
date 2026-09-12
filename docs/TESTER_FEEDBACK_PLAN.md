# BotYalla — Tester Feedback: Problems, Root Causes & Implementation Plan

> **Status:** ✅ implemented (2026-09-12) — see [§10 Implementation status](#10-implementation-status) at the end.
> **Date:** 2026-09-12
> **Source:** a first-time, non-technical tester built a Telegram bot for a made-to-measure clothing shop ("محل ملابس", template *customer_service*, **free plan**), used the free AI setup, and shared the bot with a customer.
> **Read with:** [AGENTS.md](../AGENTS.md) (invariants every change must respect) · [REVIEW.md](../REVIEW.md) · [business/LAUNCH_READINESS.md](../business/LAUNCH_READINESS.md)

---

## 0) Executive summary

| # | Problem (as reported) | Root cause (verified in code) | Professional solution | Priority | Tier |
|---|---|---|---|---|---|
| 1 | Creating the bot is too technical (BotFather, copy/paste token) | Only manual BotFather flow exists; AGENTS.md §6 forbids automation (true until April 2026) | **Telegram Managed Bots** (Bot API 9.6): one tap / one QR scan → Telegram's own confirm dialog → bot created, token delivered to us automatically | 🔴 P0 | All plans |
| 2 | After creating the bot there is no easy way to open or share it | Bot page shows `@username` as a pill only; no link, QR or share action | "Your bot is live" card: direct link, QR code (screen + printable), copy, share, "Test it myself" | 🔴 P0 (quick win) | All plans |
| 3 | Free AI is "dumb": pasted the raw prompt into the welcome message, fixed thanks text, flow not adapted | The free plan **never calls an LLM** — `ai_setup()` forces `key=None`, so `_fallback()` runs; it copies the first 40 chars of the prompt as the business name. The paid path is one-shot JSON with no understanding, no questions, no preview | **Setup Agent**: multi-turn, extracts a structured Business Brief, asks clarifying questions only when needed, proposes a design, shows a live preview + diff, applies on approval | 🔴 P0 (hotfix) → 🟠 P1 (agent) | Free with quota, more in paid |
| 4 | Bot answers with canned replies; wants AI to be the bot's brain | Bots are rule-based flows; any free text after the flow ends gets "للبدء من جديد أرسل /start" (`flow_engine.handle_message`) | **Response modes**: Flow · Hybrid · **AI Brain** (grounded LLM agent with tools, handoff, cost limits). Paid add-on, labelled *"Available in custom bots"* | 🟠 P1 | Paid add-on |
| 5 | Owner cannot enter a conversation and reply manually | **No conversation storage exists** (only `leads` and `chat_state`); no owner→customer send path | **Live Inbox + Human takeover**: `messages` + `conversations` tables, "Chat" button on every lead row, take-over / return-to-bot | 🟠 P1 | All paid plans (read-only transcript on free) |
| 6 | Cannot upload images/videos from device; links only | Outbound media is URL-only (`welcome_image`, product `image`); inbound customer media storage exists (`media_store`) but not an owner media library | **Media Library**: upload from device or paste link, validated & channel-aware, reused everywhere (welcome, products, flow steps, campaigns), incl. **interactive video** (video + buttons) | 🟡 P2 | Quota per plan |

**Recommended order:** Phase 0 hotfixes (1–2 days) → Managed Bots (item 1) → Setup Agent + `messages` table (items 3, 5 foundations) → Live Inbox (5) → AI Brain (4) → Media Library (6, can run in parallel). Details in §7.

---

## 1) One-tap / QR bot creation — Telegram Managed Bots

### 1.1 Problem
The tester had to: open BotFather, send `/newbot`, invent a name and a username ending in `bot`, copy a long token, come back, paste it. Every step is a drop-off point; most small-business owners do not know what a "token" is.

### 1.2 Root cause
- The only creation path is manual: `app.bot_create` → `tg_helpers.validate_token` (getMe) on a pasted token.
- AGENTS.md §6 says: *"لا تنشئ بوت تليجرام عبر أي API. تيليجرام لا يوفّر ذلك"*. That was correct when written. **It is no longer true** — Telegram shipped an official mechanism in **Bot API 9.6 (April 3, 2026)**.

### 1.3 What Telegram now provides (verified)
**Managed Bots** let a *manager bot* create and operate bots **on behalf of a user**, with the user's explicit confirmation inside Telegram:

- The manager bot enables **Bot Management Mode** in the BotFather mini app → `getMe` returns `can_manage_bots: true`.
- The user opens a link of the form **`https://t.me/newbot/{manager_bot_username}/{suggested_username}`** (or taps a keyboard button of type **`KeyboardButtonRequestManagedBot`** sent by the manager bot). Telegram shows a native, pre-filled "create bot" screen; the user confirms (and may edit the name/username).
- The manager receives a **`managed_bot`** update containing **`ManagedBotUpdated`** (`user` = the creator/owner, `bot` = the new bot), and a **`ManagedBotCreated`** service message.
- The manager calls **`getManagedBotToken(user_id)`** to receive the new bot's token. **`replaceManagedBotToken`** rotates it; **`getManagedBotAccessSettings` / `setManagedBotAccessSettings`** control access.
- **Ownership:** the user who confirmed owns the bot in Telegram; the manager holds operational control via the token. We never see or ask for the user's Telegram login, phone or codes — this stays compliant with AGENTS.md §6's second rule (*never collect Telegram account credentials*).

### 1.4 Solution — the UX (2–3 taps)

**On mobile:**
1. Dashboard → **"أنشئ بوتك على تليجرام بضغطة واحدة"** → the user picks the bot type (store / bookings / customer service …) and types the business name.
2. Tapping the button opens Telegram on **our platform bot** with a one-time link (`t.me/{platform_bot}?start=mb-{token}`).
3. The platform bot replies with a single button **"✨ أنشئ بوتي"** (`KeyboardButtonRequestManagedBot`, pre-filled name and suggested username).
4. The user taps → confirms Telegram's dialog → **done**. The dashboard (polling) jumps to *"بوتك شغّال 🎉"* with the link and QR (§2).

**On desktop:** the same button shows a **QR code** to scan with the phone — this opens step 2 on the phone. The desktop page waits and auto-advances when the bot is created.

**Why start from our platform bot, not a bare `t.me/newbot/...` link?** The `managed_bot` update tells us the **Telegram** user id, not the BotYalla account. Starting the conversation with our platform bot through a one-time `start` token (the same pattern as today's `account_link_telegram`) binds **Telegram user id ↔ BotYalla account** first, so when the bot is created we know exactly which account owns it. The bare link remains a fallback for users already linked.

### 1.5 Solution — backend

| Piece | Design |
|---|---|
| Platform bot | Admin enables Bot Management Mode once in the BotFather mini app (documented in `docs/`). Add `"managed_bot"` to the platform bot's `allowed_updates` and handle it in `platform_bot.py`. |
| Library | Upgrade **python-telegram-bot 21.6 → 22.8** (full Bot API 9.6/10.0 support). If the upgrade is deferred, call `getManagedBotToken` through the existing raw HTTP helper (`tg_helpers._tg_post`) — both paths are viable; the upgrade is preferred but needs a regression pass (PTB 22 has breaking changes). |
| One-time link | New table `managed_bot_requests(token_hash PK, user_id, template, business_name, suggested_username, created_at, expires_at, used_at, tg_user_id, bot_id)`. Token stored **hashed**, single-use, 15-minute TTL — the same pattern as `password_resets`. |
| Creation handler | On `managed_bot` update: find the pending request by `tg_user_id` → `getManagedBotToken(user_id)` → `validate_token` (getMe) → `db.create_bot(...)` with the chosen template and default config (the existing `bot_create` logic moved into a reusable function) → `configure_bot_profile` (name, description, commands) → optionally run the Setup Agent brief (§3) → start the bot → mark the request used → confirm to the user in Telegram with the bot link. |
| Plan limits | The same `max_bots` check as `bot_create` runs **before** issuing the link and again at creation (race-safe). |
| Suggested username | Transliterate the business name to Latin, slugify, append `_bot` (Telegram validates uniqueness in its dialog; the user can edit). |
| Dashboard status | `GET /bot/create/managed/<request_id>/status` → `pending / created(bot_id) / expired`. Frontend polls every 2 s while the QR/link is open. |
| Token security | Tokens are currently stored in plaintext in `bots.token`. Take this opportunity to **encrypt tokens at rest** (Fernet key from `.env`), and use `replaceManagedBotToken` for "Disconnect / rotate". |
| Fallback | Keep the manual BotFather path (improved with a 3-step illustrated guide) for users who prefer it or if Management Mode is unavailable. |

### 1.6 WhatsApp equivalent (for consistency)
Meta's **Embedded Signup** (available to Tech Providers — see LAUNCH_READINESS L-12) is the WhatsApp counterpart: a Meta-hosted popup that creates/links the WhatsApp Business Account and number, and returns the IDs to us. Plan it as the WhatsApp track of this item once Tech Provider status is approved.

### 1.7 Required rule change
Update **AGENTS.md §6**: replace *"never create Telegram bots via any API"* with *"create Telegram bots **only** through official Managed Bots (manager bot + user confirmation); never through account automation, never collecting credentials"*.

### 1.8 Acceptance criteria / tests
- A pending request binds one BotYalla account; a second account cannot claim it; expired/used tokens are refused.
- A `managed_bot` update for an unknown Telegram user creates nothing.
- Plan limit reached ⇒ no link issued; limit reached between link and creation ⇒ bot not started, user told to upgrade.
- Created bot row has the correct owner, template and running state; token stored encrypted.
- Status endpoint only reveals the caller's own requests (ownership in the query).
- `getManagedBotToken` failure ⇒ clear message, retry path, nothing half-created.

**Effort:** 3–4 days (+1–2 days if upgrading PTB in the same step).

---

## 2) "Your bot is live" — direct link, QR, share

### 2.1 Problem
After creation the owner sees `@Raghadpersonalbot` as a small pill. There is no button to open the bot, no link to copy, no QR to print for the shop.

### 2.2 Solution
A prominent card at the top of the bot page (and on the dashboard bot card, and at the end of the creation flow):

- **Open bot** — `https://t.me/{username}?start=src-link` (Telegram) or `https://wa.me/{number}?text=…` (WhatsApp).
- **QR code** — rendered server-side as **SVG** (CSP-safe, crisp at any size) with the bot avatar in the centre; library: `segno` (pure-Python, no system deps) — *new dependency, needs approval*.
- **Copy link**, **Share to WhatsApp/Telegram** (`navigator.share` on mobile), **"Test it myself"**.
- **Printable poster** — A5/A4 SVG/PDF: business name, *"امسح وكلّم بوتنا 24 ساعة"*, large QR, the link. Owners put it at the counter, on packaging and on social posts.
- **Attribution** — different `start` payloads per source (`src-qr`, `src-link`, `src-poster`) logged via `db.log_event` → analytics show where customers come from.

### 2.3 Details
- The bot username is already stored in `cfg.bot_username` at creation; refresh it from `getMe` on sync.
- Endpoints: `GET /bot/<id>/qr.svg?src=qr` and `GET /bot/<id>/poster.svg`, both behind `_owned()`.
- The onboarding checklist step **"جرّبه بنفسك"** links straight to the bot.

### 2.4 Tests
QR endpoint returns valid SVG for the owner and 404 for others; the link encodes the right username/number; source payloads are logged.

**Effort:** 1 day. **Quick win — do first.**

---

## 3) The AI Setup Agent (replacing one-shot generation)

### 3.1 What the tester saw
Prompt: *"بنعمل ملابس تفصيل و انت بوت خدمة عملاء واضبط الاعدادات"*
Result: welcome = **"👋 أهلاً بك في «بنعمل ملابس تفصيل و انت بوت خدمة عملاء و»! سعداء بخدمتك."**, the default thanks text, a generic flow.

### 3.2 Root causes (verified)
1. **The free plan never uses AI.** In `app.py → ai_setup()`:
   `if current_role() not in ("admin","support") and not p.get("ai"): key = None  # Force fallback offline generator`
   The free plan has `"ai": False`, so every free user gets `ai_agent._fallback()`.
2. **The fallback echoes the prompt.** `_fallback()` takes the first 40 characters of the first line as the business name and builds `welcome = f"👋 أهلاً بك في «{name}»! …"`; `thanks` is a constant; the flow is a fixed 4-step template. For `customer_service` it **overwrites the user's existing flow** with that template.
3. **The paid path is one-shot.** One system prompt → one JSON → applied immediately. No understanding of the goal, no clarifying questions, no preview, no undo; it only fills `welcome/thanks/flow/products/booking` and ignores FAQs, tone, working hours, delivery, measurements, etc.
4. **UI copy is misleading** — the badge "المولّد الأساسي (مجاني)" sits under a heading that says "اضبط بوتك بالذكاء الاصطناعي".

### 3.3 Phase-0 hotfix (1 day, independent of the agent)
- The fallback must **never** place raw user text into customer-facing messages. Extract a business name only when confidently detectable; otherwise use the bot's existing `business_name`.
- The fallback must **never overwrite** a non-default flow the user already edited.
- Rename the badge honestly ("قوالب جاهزة — بدون ذكاء اصطناعي") until free users get real AI.

### 3.4 The Setup Agent — design
A short, multi-turn conversation inside the bot page (chat UI), backed by a state machine:

```
INTAKE ──► BRIEF (structured) ──► GAPS? ──yes──► ASK (≤3 questions, chips) ──┐
                                   │no                                        │
                                   ▼                                          │
                               DESIGN ──► PREVIEW + DIFF ──► APPLY / EDIT ◄───┘
```

1. **Intake** — the owner writes anything, in any dialect.
2. **Business Brief** (structured output validated by JSON schema): business type & sub-type, offerings (with prices if given), audience, **primary goal** (sell · book · support · collect leads · answer FAQs), data to collect, tone & dialect, hours, location/delivery, payment methods, FAQs, escalation contact. Every field carries a confidence score.
3. **Gap analysis** — only if goal-critical fields are missing/low-confidence, the agent asks **at most 3 targeted questions per round, max 2 rounds**, each with quick-reply chips. For the tester it would ask e.g.: *"العميل بيطلب تفصيل جديد ولا تعديل؟"*, *"محتاجين مقاسات العميل في المحادثة؟"*, *"بتوصّلوا ولا استلام من المحل؟"*.
4. **Design** — the agent proposes the full bot: recommended template (it may suggest switching — tailoring fits a flow with a *measurements* step and a *photo upload* step better than a plain customer-service form), a branching flow with buttons, welcome/thanks written for that business, FAQ answers, owner-notification text.
5. **Preview & diff** — a live chat simulator renders the proposed bot; a "what will change" list shows before/after per field. Nothing is written until **Apply**.
6. **Apply & undo** — applied configs are versioned (`bot_config_versions`), with one-click restore; fields the owner edited by hand are flagged and never silently overwritten.
7. **Validation loop** — output is linted before preview: WhatsApp button label ≤ 20 chars and ≤ 3 reply buttons (or a list ≤ 10 rows), prompt length limits, required `var` names unique, no empty steps. Failures are sent back to the model to fix (max 2 retries).

### 3.5 Implementation notes
- **Provider abstraction** in `ai_agent.py`: keep Gemini (`gemini-2.5-flash`) and Groq (`llama-3.3-70b-versatile`); use **structured output / JSON schema** on every call; optionally add a Claude model as a premium provider. The key stays platform-level (AGENTS.md §3.4).
- **State:** `ai_setup_sessions(id, bot_id, owner_id, status, brief_json, turns_json, proposal_json, tokens_used, created_at, updated_at)`.
- **Safety:** treat the owner's text as data (prompt-injection-resistant system prompt), cap tokens per session, rate-limit sessions per account/day, redact secrets, log failures to `logs/`.
- **Free tier:** give free users the **real agent** on a low-cost model with a small quota (e.g. 3 setup sessions/month); paid plans get more. The offline generator becomes an outage fallback only.
- **Endpoints:** `POST /bot/<id>/ai/session` (start), `POST /bot/<id>/ai/session/<sid>/reply`, `POST /bot/<id>/ai/session/<sid>/apply`, `POST /bot/<id>/config/restore/<version>` — all CSRF-protected and `_owned()`.

### 3.6 Acceptance criteria / tests (LLM stubbed as today via `ai_agent._call`)
- The tester's exact prompt never appears verbatim in `welcome`/`thanks`.
- An incomplete brief ⇒ the agent returns questions, **not** a config.
- A complete brief ⇒ proposal includes an adapted flow (for tailoring: measurements/photo steps).
- Preview writes nothing; Apply writes and creates a version; Restore returns the previous config.
- Malformed model output ⇒ repair loop, then a clear error — never a half-applied config.
- Quota and rate limits enforced; free vs paid behaviour correct.

**Effort:** hotfix 1 day; agent 5–7 days.

---

## 4) AI Brain mode — the LLM runs the conversation (paid)

### 4.1 Problem
Once a customer finishes the flow, any free question (e.g. *"عندكم إيه؟"* / "what do you offer?") gets only *"للبدء من جديد أرسل: /start"* (`flow_engine.handle_message`, the `bot_user_exists` branch). During the flow, a question typed into a step is stored as that step's answer. Rule-based flows cannot answer free questions.

### 4.2 Solution — per-bot response mode

| Mode | Behaviour | Who |
|---|---|---|
| **Flow** (today) | Deterministic steps, buttons, data capture | All plans |
| **Hybrid** | Flow stays for structured capture (orders, bookings); **free text outside a step is answered by AI** from the knowledge base, then offers to continue the flow | Paid add-on |
| **AI Brain** | The LLM drives the whole conversation, calls tools to act | Paid add-on — labelled **"متاح في البوت المخصص / Available in custom bots"** next to the toggle |

### 4.3 Architecture
- **Routing:** at the top of `flow_engine.handle_message` (the single entry for Telegram and WhatsApp), branch on `cfg.response_mode` and on the conversation mode (§5: human takeover wins over everything).
- **Grounding:** system prompt built from the **Business Brief** (§3) + a **knowledge base** (products & prices, FAQs, hours, delivery, policies) editable by the owner. The model must answer **only** from it; unknown facts ⇒ *"هتأكد وأرجعلك"* + notify the owner (never invent prices, stock or promises).
- **Memory:** last N messages from the `messages` table (§5) per conversation.
- **Tools (function calling):** `create_lead`, `create_order`, `check_booking_slots` / `create_booking`, `send_product_card` (image + buttons), `handoff_to_human`, `end_conversation`. Tools write through existing `database.py` functions — no new SQL outside it.
- **Guardrails:** language/dialect matching, max reply length, per-customer rate limit, profanity/abuse handling, injection-resistant prompt, PII minimisation, automatic handoff on complaints or low confidence.
- **UX:** Telegram `sendChatAction(typing)`; optional streaming via `sendMessageDraft` (Bot API 10.x) for a "live typing" feel.
- **WhatsApp:** AI replies are free-form service messages ⇒ only inside the 24-hour window and **must** pass through `db.try_consume_msg` (AGENTS.md §6).

### 4.4 Pricing & cost control
- LLM calls cost per token ⇒ **paid add-on** (not in Free). Include a monthly AI-reply allowance per plan; overage can draw from the existing wallet in piastres (AGENTS.md §3.19).
- Per-bot kill switch; automatic fallback to Flow if the provider fails or the allowance is exhausted.
- Owner sees AI transcripts in the Inbox (§5) and can rate replies (feedback loop).

### 4.5 Legal & policy updates (required before launch of this mode)
- The Privacy Policy currently states AI providers receive **only the business description, not customers' data**. AI Brain sends **end-customer messages** to the LLM provider ⇒ update `legal_content.py` (privacy §5 sharing, §6 transfers, §7 retention), Terms (AI add-on), and show an opt-in notice to the owner.

### 4.6 Tests
Free text outside a step is answered in Hybrid; unknown price ⇒ no invented number + owner notified; tool calls create real leads/orders; allowance exhausted ⇒ Flow fallback; WhatsApp outside 24 h ⇒ no free-form send; human takeover suppresses AI.

**Effort:** 6–8 days (after §3 brief/KB and §5 `messages` table exist).

---

## 5) Live Inbox & human takeover

### 5.1 Problem
The owner sees each customer as a row in the «العملاء» table (name · phone · message) but cannot open the conversation or talk to that customer.

### 5.2 Root cause
There is **no conversation storage**: the schema has `leads` (final answers) and `chat_state` (flow position) only. There is also no path for the owner to send a message as the bot.

### 5.3 Solution
**Data model (in `database.py`, with `_migrate` guards):**
- `messages(id, bot_id, peer, direction in|out, sender customer|bot|ai|human, kind text|image|video|audio|document, text, media_id, external_id, created_at)` — indexed on `(bot_id, peer, created_at)`.
- `conversations(bot_id, peer, mode bot|human, assigned_user_id, unread, last_message_at, handoff_at, PRIMARY KEY(bot_id, peer))`.
- Every inbound and outbound message (flow, AI, human) is logged through one helper.

**Behaviour:**
- A **"💬 محادثة"** button next to every lead/customer row opens the conversation.
- **Take over:** sets `mode=human`. `handle_message` then logs the inbound message, **does not run the flow/AI**, and notifies the owner (platform bot alert with a deep link to the conversation).
- **Reply:** the owner types in the dashboard → `POST /bot/<id>/inbox/<peer>/send` → `manager.send_to_peer()` submits to the bot's asyncio loop (same pattern as `notify_text`) → message logged as `sender=human`.
- **Return to bot:** one button; optional auto-return after N hours of owner inactivity.
- **Inbox page:** conversation list (unread badges, last message, mode), filters (needs reply · human · AI), search.
- **Updates:** polling every 5 s to start (gunicorn `threads=4` — SSE would pin threads); revisit after the bot-manager is split into its own service.

**Channel rules:**
- **WhatsApp:** free-form human replies only within the 24-hour window; outside it the UI offers an approved template (existing templates feature). Every send passes `try_consume_msg`.
- **Telegram:** no window; respect blocked users (403) gracefully.

**Privacy:** define message retention (e.g. 12 months, configurable), include in export/delete, update the Privacy Policy retention table.

### 5.4 Security
Ownership enforced **inside** every query (`bot_id` + owner), CSRF on send, per-bot send rate limit, all text rendered through React (escaped) and `_js_json`.

### 5.5 Tests
Takeover suppresses the flow; owner reply reaches the channel stub and is logged; another owner gets 404; WhatsApp outside 24 h is blocked with a template suggestion; return-to-bot resumes the flow correctly; unread counters update.

**Effort:** 4–5 days.

---

## 6) Media Library — upload from device or link (incl. interactive video)

### 6.1 Problem
The owner can only paste URLs (welcome image, product images). Most owners have photos and videos **on their phone**, not hosted links.

### 6.2 Solution
An account-level **Media Library**:
- **Upload** images, videos, GIFs from the device (drag & drop; mobile camera/gallery picker), or **paste a link**.
- **Validation:** magic-byte sniffing (reuse `media_store._sniff` — never trust the declared type; fail closed, AGENTS.md §6), per-channel size limits, image dimension checks, video container/codec check (MP4/H.264).
- **Link safety:** fetch server-side with SSRF protection (HTTPS only, block private/loopback IPs, size/time caps), then store a copy — a link that disappears must not break the bot.
- **Storage:** outside `static/` (like customer media), per-plan storage quota (extend `media_limit` with MB).
- **Reuse everywhere:** welcome media (image **or video**), product images, a new flow step type **"media message"**, campaign broadcasts.

**Channel delivery (cached, not re-uploaded each time):**

| Channel | Upload limits | Delivery |
|---|---|---|
| Telegram | photos ≤ 10 MB, other files ≤ 50 MB (bot upload) | upload once, **cache `file_id`** per bot and reuse |
| WhatsApp | image ≤ 5 MB (JPEG/PNG), video ≤ 16 MB (MP4); interactive header media < 15 MB | upload to the Cloud API media endpoint, **cache `media_id`**, re-upload on expiry |

**Interactive video / image:**
- Telegram: `sendVideo` / `sendPhoto` with an inline keyboard (buttons under the media).
- WhatsApp: **interactive reply-buttons message with a video or image header** (max 3 buttons, 20 chars each) — the platform validates these limits before saving.

### 6.3 Tests
Non-media file disguised as `.jpg` rejected; oversize per channel rejected with a clear message; quota enforced; SSRF targets (`127.0.0.1`, `169.254.x.x`, private ranges) refused; `file_id`/`media_id` cached and reused; flow media step renders on both channel stubs.

**Effort:** 4–6 days.

---

## 7) Delivery plan

### Phase 0 — hotfixes & quick wins (1–2 days)
- §3.3 fallback must not echo the prompt or overwrite edited flows; honest badge text.
- §2 "Your bot is live" card: link, QR, copy, share, poster.
- Bot page header on mobile: group the actions (Stop · Analytics · Campaign · Flow builder · Delete) into a primary action + overflow menu.

### Phase 1 — frictionless creation (3–6 days)
- §1 Managed Bots (+ PTB 22.8 upgrade, token encryption, AGENTS.md §6 update).

### Phase 2 — understanding the business (6–8 days)
- §3 Setup Agent (brief, questions, preview/diff, versions).
- `messages` table + logging helper (foundation for §4 and §5).

### Phase 3 — humans in the loop (4–5 days)
- §5 Live Inbox & takeover.

### Phase 4 — the AI brain (6–8 days)
- §4 Hybrid & AI Brain modes, allowance & wallet, legal updates.

### Parallel track — media (4–6 days)
- §6 Media Library.

**Dependencies:** §4 needs §3 (brief/KB) and §5 (`messages`). §1 and §2 are independent. §6 is independent but §4's `send_product_card` benefits from it.

---

## 8) Cross-cutting requirements (from AGENTS.md)
- All SQL in `database.py`, parameterised; migrations in `_migrate` with column guards.
- `_owned()` / ownership inside queries for every bot-scoped route; CSRF on every POST; no state change over GET.
- Anything injected into `<script>` goes through `_js_json()`; every `<script>`/`<style>` carries the CSP nonce.
- WhatsApp sends always through `try_consume_msg`; broadcasts respect the 24-hour window.
- Money in integer piastres; any AI overage through `_wallet_move`.
- Email/links built from `PUBLIC_URL`.
- **Tests first-class:** each item ships with tests that fail before and pass after (Flask test client, channel and LLM stubs as documented in AGENTS.md §5), run with `./run_tests.sh`, plus a browser check on mobile and desktop.
- Update `i18n.py` (Arabic + English), `PROJECT_MEMORY.md`, `LAUNCH_READINESS.md`, and the legal texts where behaviour changes.

---

## 9) Open decisions for the owner
1. **Free-tier AI quota** for the Setup Agent (suggested: 3 sessions/month on a low-cost model).
2. **AI Brain pricing:** add-on price and monthly allowance per plan; overage via wallet or hard stop.
3. **Message retention** period for the Inbox (suggested 12 months).
4. **New dependency approval:** `segno` (QR) and the python-telegram-bot 22.8 upgrade.
5. **Premium LLM provider** for AI Brain (keep Gemini/Groq only, or add a higher-quality model for paid tiers).

---

## Sources
- [Telegram Bot API](https://core.telegram.org/bots/api) · [Bot API changelog](https://core.telegram.org/bots/api-changelog) (9.6 — Managed Bots, April 3 2026; 10.x — streaming drafts)
- [Telegram Managed Bots (Bot API 9.6) — technical flow](https://happyin.space/llm-agents/telegram-managed-bots/)
- [Telegram Bot API 9.6 Adds Managed Bots Feature — aiHola](https://aihola.com/article/telegram-managed-bots-api)
- [python-telegram-bot changelog (v22.8: API 9.6 & 10.0)](https://docs.python-telegram-bot.org/en/stable/changelog.html)
- [WhatsApp Cloud API — Interactive reply buttons messages (media headers)](https://developers.facebook.com/docs/whatsapp/cloud-api/messages/interactive-reply-buttons-messages/)
- [WhatsApp Cloud API — Media (supported types & sizes)](https://developers.facebook.com/documentation/business-messaging/whatsapp/business-phone-numbers/media)

---

## 10) Implementation status

| # | Item | Where | Tests |
|---|---|---|---|
| 1 | One-tap / QR creation (Managed Bots): one-time hashed link → platform bot → native `request_managed_bot` button + `t.me/newbot` fallback → `managed_bot` update → `getManagedBotToken` → bot row, profile sync, auto-start, owner linked. Plan limit re-checked at creation; claim-once lock; token-rotation updates; unknown Telegram users create nothing. Works on PTB 21.6 (`api_kwargs` + `do_api_request`) and 22.8 (typed objects). | `managed_bots.py`, `platform_bot.py`, `bot_manager.py`, `app.py` (`/bot/create/managed`), Dashboard one-tap card | `tests/test_managed_media.py` |
| 2 | "Your bot is live" card: open · copy · share · QR (server SVG, `segno`) · printable A4 poster · QR download; per-source `start` payloads counted in Analytics; creation lands on the bot page; onboarding "try it" opens the bot. | `app.py` (`_bot_links`, `/qr.svg`, `/poster`), `templates_web/poster.html`, BotDetail, Analytics | `tests/test_managed_media.py::LinksTests` |
| 3 | Setup Agent: multi-turn, ≤3 questions × 2 rounds, JSON-validated design, repair pass, no-echo guard, live chat preview + before/after diff, apply on approval, config versions + restore. Offline designer (no key / provider down) recognises 7 business types and designs per answers. Free plan gets the real agent with a 3-session quota. | `ai_agent.py`, `app.py` (`/ai/session*`, `/config/restore`), BotDetail | `tests/test_setup_agent.py` |
| 4 | Response modes Flow · Hybrid · AI Brain (paid, labelled «يمكن تطبيقه في البوت المخصص»): grounded in a per-bot knowledge base, validated tools (lead · server-priced order · handoff · notify · product photo), monthly allowance then wallet (atomic), automatic fallback to the flow, explicit owner consent, privacy/terms updated. | `flow_engine.py`, `ai_agent.brain_reply`, `database.ai_reply_allow`, `app.py` (`/brain`), BotDetail | `tests/test_inbox_brain.py::BrainTests` |
| 5 | Inbox + human takeover: `messages`/`conversations` tables, every in/out message logged, «محادثة» button on every customer row, take over / hand back, 12 h auto-return, one alert per unread burst, WhatsApp 24 h window enforced, free plan read-only, 12-month retention purge. | `database.py`, `flow_engine.py`, `bot_manager.py`, `app.py` (`/inbox*`), Inbox view | `tests/test_inbox_brain.py` |
| 6 | Media Library: upload from device (drag & drop) or link (SSRF-pinned fetch), magic-byte sniffing, WhatsApp-safe limits, per-plan storage quota; used in welcome, products, new "show media" flow step (with buttons = interactive video), campaigns and inbox replies; Telegram `file_id` / WhatsApp `media_id` cached per bot. | `asset_store.py`, `channels/*.send_media`, `app.py` (`/media`, `/api/assets*`), media.jsx | `tests/test_managed_media.py::AssetsTests` |
| — | Bot tokens encrypted at rest (Fernet) with a deterministic HMAC blind index (`token_idx`) for WhatsApp lookups and duplicate detection; key from `FERNET_KEY` or an auto-generated `.token.key` (git-ignored, backed up); legacy hard-coded key read-only and rotated away; Telegram tokens no longer sent to the browser. | `database.py`, `app.py` (`_public_bot`), `deploy/backup.sh` | `tests/test_token_crypto.py` |

**Not done / deliberately deferred**
- WhatsApp Embedded Signup (§1.6) — needs Meta Tech Provider approval (LAUNCH_READINESS L-12).
- Telegram streaming replies (`sendMessageDraft`) — the typing indicator is used instead; add when replies get long.
- Outbound logging for the PTB-native store/booking/FAQ templates on Telegram: their inbound messages and takeover are handled (group −1 guard); the canned replies they send are not yet mirrored in the inbox.
