# BotYalla — Launch & Marketing Playbook

**Version:** 1.0 · **Date:** 15 September 2026 · **Scope:** botyalla.com
**Prepared for:** Youssef AlSherief — Founder, BotYalla
**Covers:** Production-readiness audit · Go-to-market strategy · Launch campaign · Per-platform execution guides · Media asset briefs · Budget & measurement

---

## Table of Contents

**Part I — Production Readiness**
1. Audit executive summary
2. What was tested and passed
3. 🔴 Critical gaps — do not advertise until closed
4. 🟠 Important gaps — week one
5. 🟡 Improvements — month one
6. Launch-day checklist (45 minutes)

**Part II — Strategy**
7. Reading the Egyptian market
8. Ideal customer profile and segments
9. Positioning and core message
10. Offer architecture and funnel

**Part III — The Launch Campaign ("The Boom")**
11. Timeline: T-7 → T+30
12. The anchor offer: "Founding 100"
13. Launch day — hour-by-hour war room

**Part IV — Setting Up Social Accounts Professionally**
14. Step-by-step per platform + every free offer worth claiming

**Part V — Per-Platform Execution Guides**
15. Facebook & Instagram · 16. TikTok · 17. Facebook Groups · 18. Telegram · 19. WhatsApp · 20. LinkedIn · 21. YouTube · 22. Google (SEO, Maps, Ads) · 23. Email

**Part VI — Content**
24. Content pillars and tone of voice
25. 30-day calendar — day by day
26. Hook bank and ad copy

**Part VII — Media Assets**
27. Detailed brief for every media file required

**Part VIII — Budget & Measurement**
28. Three budgets (zero · 5,000 · 20,000 EGP)
29. Measurement and KPIs

**Part IX — Sustainable Growth**
30. Partners, affiliates and agencies
31. Risk register and contingencies

---
---

# Part I — Production Readiness Audit

## 1. Audit executive summary

I reviewed the full project folder (`E:\Github\BotYalla`) and tested the live site `https://botyalla.com` in a browser: public pages, legal policies, redirects, security headers, performance, SEO, RTL/LTR, the English version, mobile rendering, the browser console, DNS records, and TLS.

### Overall verdict

> **The product is technically ready to launch.** The security posture is unusually mature for a day-one product: per-request nonce CSP, HSTS, `Secure`+`HttpOnly`+`SameSite` cookies, 301 redirects from HTTP and `www`, zero console errors, complete SEO with structured data, and four legal policies in two languages.
>
> **But do not start the marketing campaign until two gaps are closed.** Neither is in the code — one will make you **burn ad budget completely blind**, and the other may cost you half of everyone who signs up.

| Category | Count | Impact |
|---|---|---|
| 🔴 Critical — before advertising | **3** | Blinds measurement or breaks conversion |
| 🟠 Important — week one | **6** | Reduces conversion or creates risk |
| 🟡 Improvements — month one | **7** | Performance and growth |

### The three headline findings

1. **There is no analytics or tracking on the site at all** — no Google Analytics, no Meta Pixel, no TikTok Pixel, not even Search Console verification. You would be spending on ads with no way to know what works.
2. **The current CSP will silently block any tracking you add** — `script-src 'self' 'nonce-…'` and `connect-src 'self'` block Google, Meta and TikTok. Installing a pixel without widening CSP gives you a silent pixel you *believe* is working.
3. **Zero social media presence** — no Facebook, Instagram, TikTok, LinkedIn, or Telegram channel. The site contains not one social link. You cannot launch a campaign on platforms that do not exist.

---

## 2. What was tested and passed ✅

### Security and infrastructure

| Check | Result |
|---|---|
| HTTP → HTTPS redirect | ✅ `301` |
| `www` → apex redirect | ✅ `301` (single canonical version — excellent for SEO) |
| `Strict-Transport-Security` | ✅ `max-age=31536000; includeSubDomains` |
| `Content-Security-Policy` | ✅ Per-request nonce, no `unsafe-inline` in scripts |
| Session cookie | ✅ `Secure; HttpOnly; SameSite=Lax` — **`COOKIE_SECURE=1` is live in production** (was an open item in `REVIEW.md` — now closed) |
| `X-Frame-Options` / `X-Content-Type-Options` / `Referrer-Policy` / `Permissions-Policy` | ✅ All present |
| `/healthz` | ✅ `{"ok":true}` — ready for uptime monitoring |
| `/.well-known/security.txt` | ✅ Present |

### SEO and discoverability

| Check | Result |
|---|---|
| `robots.txt` | ✅ Allows public, blocks 15 private paths, links sitemap |
| `sitemap.xml` | ✅ 8 URLs with `lastmod` and per-language `hreflang` |
| `canonical` + `hreflang` (ar · en · x-default) | ✅ On every page |
| Open Graph + Twitter Card | ✅ Complete, with separate `og-ar.png` and `og-en.png` at 1200×630 |
| Structured data (JSON-LD) | ✅ `Organization` · `WebSite` · `SoftwareApplication` · `FAQPage` — all valid |
| 404 page | ✅ Fully branded, in Egyptian dialect |
| `site.webmanifest` | ✅ Present |

### Language and direction (RTL/LTR)

| Check | Result |
|---|---|
| Arabic | ✅ `<html lang="ar" dir="rtl">` |
| English via `?lang=en` | ✅ `<html lang="en" dir="ltr">` — a full translation, not partial |
| Four policies in both languages | ✅ Terms · Privacy · Refund · Acceptable Use |
| No mixed direction or clipped text | ✅ Verified visually |

### Front-end and performance

| Check | Result |
|---|---|
| Console errors | ✅ **Zero** |
| Horizontal overflow at 375px | ✅ None |
| All images have `alt` | ✅ 2/2 |
| All buttons have text or `aria-label` | ✅ |
| One `h1` per page | ✅ |
| gzip compression | ✅ Enabled |
| Static asset caching | ✅ `public, immutable, max-age=2592000` |
| Bundle size | ✅ JS ~123KB + CSS 16KB — lean |
| TTFB | ✅ 0.41–0.78s |
| Monthly/annual toggle | ✅ Works, maths correct (299×12−30% = 2,510 ✓) |

### Code and tests

| Check | Result |
|---|---|
| Test suite | ✅ **31 test files · ~295 assertions** — exceptional coverage |
| `REVIEW.md` | ✅ Three documented security reviews, every finding closed with a regression test |
| `.gitignore` | ✅ Excludes `.env`, `.token.key`, `botyalla.db`, WAL files |
| Deployment docs | ✅ 15 files in `docs/` — deploy, backup, monitoring, WhatsApp, email |
| Brevo DKIM | ✅ `brevo1` and `brevo2._domainkey` present and resolving (was open — **now closed**) |
| MX and DMARC | ✅ Hostinger receiving · `v=DMARC1; p=none` |

> **A note of respect:** the quality of `REVIEW.md`, `AGENTS.md` and `run_tests.sh` is well above startup average. The explicit warning inside `run_tests.sh` about deleting the production database in particular is a rare level of engineering discipline.

---

## 3. 🔴 Critical gaps — close before your first ad

### 3.1 No measurement on the site — the single biggest launch risk

**What I found:** I scanned the landing page source for `gtag`, `googletagmanager`, `fbq`, `facebook.net`, `tiktok`, `clarity`, `plausible`, `hotjar`, `posthog`, and `google-site-verification`. **Result: nothing.**

**Why this is critical:**
- You would spend on Facebook and TikTok ads with no way to know which ad produced a signup.
- You cannot build Custom Audiences or run retargeting — your cheapest source of conversions.
- **Meta's and TikTok's algorithms need a conversion signal to learn.** Without a pixel, the ad optimises for *clicks*, not *signups* — you pay several times more for a worse result.
- You will not know where people drop out: homepage? pricing? registration?

**What to install, in this order:**

| # | Tool | Why | Time |
|---|---|---|---|
| 1 | **Google Tag Manager** | One container to manage every future tag without touching code | 20 min |
| 2 | **GA4** | Funnel, sources, behaviour | 15 min |
| 3 | **Meta Pixel + Conversions API** | Optimises Facebook/Instagram ads | 25 min |
| 4 | **TikTok Pixel** | Optimises TikTok ads | 15 min |
| 5 | **Microsoft Clarity** (free) | Session recordings + heatmaps — shows you **why** they leave | 10 min |
| 6 | **Google Search Console** | Indexing + real search queries | 10 min |

**Conversion events to fire (name them exactly like this):**

```
page_view              — automatic
view_pricing           — on /pricing
sign_up_start          — on /register
sign_up                — after successful registration   ★ primary conversion
bot_created            — first bot created                ★★ the real aha moment
subscribe_intent       — clicked subscribe on a paid plan
purchase               — admin approves payment (value + EGP currency) ★★★
whatsapp_click         — clicked the WhatsApp button
```

> **The golden rule:** `bot_created` is your true metric, not `sign_up`. A user who registered but never created a bot has done nothing. Optimise ads on `sign_up` for the first two weeks (enough volume to learn), then move to `purchase` once you exceed ~50/month.

---

### 3.2 The current CSP will silently block all of the above

**What I found — the live header:**

```
content-security-policy: default-src 'self';
  script-src 'self' 'nonce-wtvtwpXbPlCtnrNAGFnfng';
  style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
  font-src 'self' https://fonts.gstatic.com;
  img-src 'self' data: https:;
  connect-src 'self';
  form-action 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'
```

**The problem:** `script-src 'self'` blocks loading GTM from `googletagmanager.com`, and `connect-src 'self'` blocks sending data to `google-analytics.com` and `facebook.com`. **Your pixel will appear installed in the code and fire nothing** — which is worse than not installing it, because you will trust numbers that do not exist.

**The fix — edit `_security_headers` in `app.py`:**

```
script-src  'self' 'nonce-…' https://www.googletagmanager.com https://connect.facebook.net https://analytics.tiktok.com https://www.clarity.ms
connect-src 'self' https://www.google-analytics.com https://analytics.google.com https://www.googletagmanager.com https://connect.facebook.net https://analytics.tiktok.com https://*.clarity.ms
img-src     'self' data: https:                                    ← unchanged (covers image pixels)
frame-src   'self' https://www.googletagmanager.com               ← add for GTM preview
```

**Three implementation notes:**
1. **Never add `'unsafe-inline'` to `script-src`.** That would undo all the hardening documented in `REVIEW.md §3.1` and reopen the injection vector. GTM works perfectly with a nonce — put the same nonce on the GTM tag.
2. **Allowlist only the tracking domains, never open `https:`.** A specific allowlist is the difference between a policy that protects and a policy that decorates.
3. **After the change, open the console and confirm there is no `Refused to load`** — that is the only way to know the pixel is genuinely firing.

> **Acceptance test:** Open the site → Facebook Pixel Helper and Google Tag Assistant both green → register a test account → `sign_up` appears in Events Manager within two minutes. Do not launch until you have seen that event with your own eyes.

---

### 3.3 Zero social media presence

**What I found:** the only external links on the site are `wa.me/201097585951`, `youssefalsherief.tech`, and Google Fonts.

**Missing:** Facebook · Instagram · TikTok · LinkedIn · YouTube · X · Telegram channel.

**Why this is critical three times over:**
1. **You cannot run a campaign on accounts that do not exist** — and brand-new Meta accounts need "warming up" before advertising or the suspension risk is high.
2. **Missing trust signal:** an Egyptian business owner about to pay 899 EGP/month will look you up on Facebook first. An empty or non-existent page means no trust, which means no payment. This is the single largest conversion leak in the Egyptian market specifically.
3. **SEO:** your `Organization` schema has no `sameAs` field — because there are no social profiles to link. This weakens your entity signal with Google.

**The plan:** Part IV of this playbook is a complete setup guide for every account in the right order, with every free offer worth claiming. **Start there today — before anything else.**

**After creating them, add to `Organization` schema:**
```json
"sameAs": [
  "https://www.facebook.com/botyalla",
  "https://www.instagram.com/botyalla",
  "https://www.tiktok.com/@botyalla",
  "https://www.linkedin.com/company/botyalla",
  "https://t.me/botyalla",
  "https://www.youtube.com/@botyalla"
]
```
And add the icons to the site footer.

---

## 4. 🟠 Important gaps — week one

### 4.1 SPF record does not include Brevo

**Live record:** `v=spf1 include:_spf.mail.hostinger.com ~all`

Brevo sends your mail (password resets, receipts, campaigns) — and is **not listed** in SPF. DKIM is present and working (`brevo1`/`brevo2`), so DMARC passes via alignment, but SPF fails — and some filters (notably Outlook and corporate mail servers) count that against you.

**The fix — edit the existing record (never add a second one; two SPF records invalidate both):**
```
v=spf1 include:_spf.mail.hostinger.com include:spf.brevo.com ~all
```

**Then verify:** send yourself a password reset → test it on [mail-tester.com](https://www.mail-tester.com) → target **9/10 or better**. In Gmail: ⋮ → Show original → `SPF: PASS · DKIM: PASS · DMARC: PASS`.

> **Capacity warning:** Brevo's free tier is **300 emails/day for everything**. On a successful launch day you may exhaust it on welcome emails alone, at which point password-reset links stop sending — and a customer who cannot get into their account on launch day is a customer lost for good. **Watch the counter on launch day and have a Brevo upgrade (Starter, ~$25/mo for 20,000 emails) ready as a contingency.**

### 4.2 `GOOGLE_SITE_VERIFICATION` is empty — the site is not in Search Console

Without Search Console you do not know which queries bring you traffic, you cannot see indexing errors, and you cannot request fast indexing on launch day. The variable already exists in `.env` — only the value is missing.

**Steps:** Search Console → Add property (URL prefix) → `https://botyalla.com` → HTML tag → copy the value → `GOOGLE_SITE_VERIFICATION=` in `.env` → `sudo systemctl restart botyalla` → Verify → then **Sitemaps → submit `sitemap.xml`** → then **URL Inspection → Request Indexing** for the homepage and pricing page.

### 4.3 Rotate `ADMIN_PASS` — open since the first review

`REVIEW.md §2.1` documents that the admin password was in `test_full.py`, which is tracked in git, and that it was **character-for-character identical** to the `.env` value. The code was fixed, but **the old value remains in repository history**, and the second review confirmed the local `.env` still carries it.

**Do this today:** change `ADMIN_PASS` on the server and in your local `.env` to a randomly generated 32-character password, stored in a password manager. The admin account approves payments and promotes roles — compromising it compromises the whole platform. **Do not run a campaign that draws attention to a platform with a leaked admin password.**

### 4.4 No uptime monitoring

`/healthz` is ready and returns `{"ok":true}` — but nobody is watching it. If the server dies at 2am during a campaign, you will not know until morning.

**The fix (10 minutes, free):** [UptimeRobot](https://uptimerobot.com) → HTTP(s) monitor → `https://botyalla.com/healthz` → every 5 minutes → alerts via email **and Telegram**. Add a second monitor on the homepage itself, and a third on SSL certificate expiry.

### 4.5 Backup restore has never actually been tested

`docs/BACKUP_RESTORE.md`, `deploy/backup.sh` and `restore.sh` exist and are well documented, and `PROJECT_MEMORY.md` lists L-15 (restore test) as **not yet done**.

> A backup you have never restored is not a backup — it is a wish.

**Do this before launch:** take a backup → restore it locally or on a staging box → confirm accounts, bots and payments are intact → and **specifically confirm `FERNET_KEY` (or `.token.key`) is backed up with it**, because losing it means every stored bot token becomes unreadable and every bot must be re-linked — a silent catastrophe.

### 4.6 The registration rate limit may choke a successful campaign

`REVIEW.md §3.3` documents **5 registration attempts per 10 minutes per IP**. The review itself flagged the risk: Egyptian mobile networks use CGNAT — **hundreds of users behind one IP**.

**The dangerous scenario:** a TikTok ad works, 30 people on Vodafone open registration in the same minute → the first 5 register, the rest see "too many attempts" and leave forever. **And you paid for all their clicks.**

**Recommendation:**
- Raise the limit to **20 per 10 minutes per IP** before launch (abuse risk is minimal — registration costs you nothing).
- **Monitor 429 logs on launch day as your first priority.** Any spike means raise it immediately.
- Better long term: rate-limit on device fingerprint, or show a CAPTCHA past the limit instead of a hard block.

---
## 5. 🟡 Improvements — month one

| # | Item | Impact | Action |
|---|---|---|---|
| 5.1 | **No social proof on the page** — zero testimonials, logos, or real numbers | Highest on conversion | Start collecting 5 testimonials immediately (a 20-second video beats text). Place a section right after "how it works". In the Egyptian market social proof outperforms any feature |
| 5.2 | **No explainer video on the homepage** | High | A 45-second "zero to working bot" above the fold. Typically lifts SaaS conversion 20–30% |
| 5.3 | **Duplicate headers** — `x-content-type-options` and `referrer-policy` are sent twice (nginx and app) | Low | Remove from `nginx.conf`, keep in the app — one source of truth |
| 5.4 | **No About page, no founder face** | Medium | Egyptians buy from people, not companies. An `/about` page with your photo, story and a real contact number lifts trust substantially |
| 5.5 | **No blog** — your strongest long-term organic engine | Medium (compounds) | `/blog` with 8 long-form Arabic articles targeting search intent (list in §21) |
| 5.6 | **102KB server-rendered HTML on the homepage** | Low | Perfectly acceptable with gzip. Watch mobile LCP on [PageSpeed Insights](https://pagespeed.web.dev/) |
| 5.7 | **No segment-specific landing pages** | Medium | `/restaurants` · `/clinics` · `/shops` — same product, each sector's own language. Doubles targeted ad performance |

---

## 6. Launch-day checklist (45 minutes)

Run it yourself on a **real phone** on mobile data (not Wi-Fi) — that is how your customer arrives.

**Infrastructure (10 min)**
- [ ] `https://botyalla.com` opens in under 3 seconds on 4G
- [ ] `http://botyalla.com` and `https://www.botyalla.com` both redirect to canonical
- [ ] UptimeRobot green on `/healthz` and alerts actually arrive (test by pausing)
- [ ] `ADMIN_PASS` rotated and stored in a password manager

**Measurement (10 min) — do not launch without this**
- [ ] Google Tag Assistant green
- [ ] Facebook Pixel Helper green
- [ ] TikTok Pixel Helper green
- [ ] Console free of `Refused to load` (means CSP is correct)
- [ ] Registered a test account → `sign_up` appeared in GA4 and Meta Events Manager
- [ ] Search Console verified and `sitemap.xml` submitted

**The product, as a customer (15 min)**
- [ ] New account registration → succeeded
- [ ] One-tap bot creation → the bot actually replies on Telegram
- [ ] AI setup agent → produced sensible replies
- [ ] Requested a "Merchant" subscription → Telegram alert reached admin → approved → **receipt arrived in Inbox, not Spam**
- [ ] Password reset → link arrived and worked
- [ ] QR poster printed and scanned with a phone → opened the bot

**Presentation and sharing (10 min)**
- [ ] `/?lang=en` fully English in LTR
- [ ] All four policies open in both languages
- [ ] A non-existent URL → branded 404
- [ ] Paste `https://botyalla.com` into a WhatsApp chat → **preview with image appears**
- [ ] [Facebook Sharing Debugger](https://developers.facebook.com/tools/debug/) → Scrape Again → correct image, title, description
- [ ] [Rich Results Test](https://search.google.com/test/rich-results) → `FAQPage` and `SoftwareApplication` with no errors

---
---

# Part II — Strategy

## 7. Reading the Egyptian market

### The facts every decision rests on

| Fact | What it means for BotYalla |
|---|---|
| **WhatsApp is the internet in Egypt** — the dominant messaging app, and nearly every business takes orders on it | WhatsApp is what they **want**; Telegram is what they **can start using free today**. That gap is the entire funnel mechanic |
| **Facebook is still the #1 platform for small business** — shops live in Facebook Pages and Groups | Facebook = primary acquisition engine; Groups = a free, high-intent channel |
| **TikTok is exploding and reaches the younger owner cohort (22–38)** | The cheapest organic reach in Egypt today. Short video is your strongest awareness tool |
| **Credit cards are rare; Vodafone Cash and InstaPay are the reality** | **A major competitive moat** — most global competitors do not accept local payment. Lead with it in every ad |
| **Distrust of online payment is high** | Testimonials, a real face, and a real WhatsApp number are not "nice to have" — they are the precondition for a sale |
| **Price sensitivity is very high** | 299 EGP is well priced, but the effective comparison is not a competitor — it is **the salary of someone who answers messages (4,000–6,000 EGP)** |
| **Official WhatsApp requires a commercial registration and tax card** | This self-segments your market: unregistered → free Telegram; registered → 899 EGP. Free segmentation |

### Competition and where you sit

| Type | Examples | Why you win in Egypt |
|---|---|---|
| Global platforms (ManyChat, Chatfuel…) | English UI, USD card payment, support in another timezone | **Arabic-first (Egyptian dialect) · local payment in EGP · support in your timezone · priced in their currency** |
| Local agencies building custom bots | 15,000–50,000 EGP one-off + months of waiting | **One tap, free, today** |
| "Hire someone to answer messages" | 4,000–6,000 EGP/month, sleeps, makes mistakes, quits | **299 EGP, 24/7, never forgets, never quits** |
| Nothing (the status quo) | The owner replies personally on their phone | **This is genuinely your biggest competitor — and the message against it is: "and you're not holding your phone"** |

> **Strategic decision:** do not market against ManyChat. Market against **"you're replying yourself at midnight"** and **"the message you didn't answer became an order someone else got."** That is what your customer feels every single day.

---

## 8. Ideal customer profile and segments

### Primary segment — start here and only here

> **An Egyptian small-business owner (25–45) receiving 20–200 messages a day on WhatsApp or Messenger, answering personally or via one employee, and losing orders because they cannot reply fast enough or outside working hours.**

**The five best launch sectors (ordered by ease of persuasion):**

| # | Sector | The acute pain | Marketing hook |
|---|---|---|---|
| 1 | **Restaurants, cafés, cloud kitchens** | Delivery orders get lost in WhatsApp noise; the menu is re-sent as an image every time | "Menu, cart, and order — all inside the chat, and the order reaches you organised" |
| 2 | **Clinics and dental/medical centres** | Appointments by phone, a busy receptionist, patients calling after hours | "Your appointments get booked while you're with a patient" |
| 3 | **Online shops and fashion/tailoring brands** | "How much?" × 200 messages a day, the same question every time | "Answer 200 'how much?' messages without touching your phone" |
| 4 | **Salons, gyms, beauty centres** | Chaotic slot booking, manual reminders | "Your slots fill up and reminders send themselves" |
| 5 | **Tutoring centres and private tutors** | Student registration, groups, schedules | "Registration, groups and schedules — one bot" |

### Secondary segment — the multiplier

> **The freelancer / small social media agency** managing 5–30 clients.

These are **not customers — they are a distribution channel**. The Agency plan (2,999 EGP) + white-label + the affiliate programme you have already built means every agency brings 10 businesses. **One agency is worth ten direct customers at one acquisition cost.**
Target them on LinkedIn and in "Social Media Egypt" and "Freelancers Egypt" groups.

### Who is *not* your customer right now

Large enterprises, banks, government, and anyone needing a long procurement cycle or enterprise integration. **Say no clearly for the first six months** — every hour there is stolen from twenty small customers.

### Detailed persona (use it when writing every ad)

```
Name: Mahmoud · 34 · owns a restaurant in Nasr City
His day: opens 11am, closes 2am. Answers WhatsApp himself between orders.
The pain: he misses messages in the rush. The customer doesn't wait,
          he buys elsewhere. And Mahmoud has no idea how many orders he lost.
Tried before: hired someone to answer messages — quit after two months.
              Asked a developer for a bot — quoted 20,000 EGP.
Fears: "it'll be complicated" · "I won't be able to set it up"
       · "it'll answer my customers wrong" · "I'll pay and find it useless"
The language he thinks in: "a message you don't answer is an order you lost"
What convinces him: seeing a working bot in 60 seconds, for free, while sitting down.
```

---

## 9. Positioning and core message

### Positioning statement (internal — never published)

> **For Egyptian small-business owners** who lose orders because they cannot answer every message,
> **BotYalla** is a no-code conversational bot platform
> **that** turns Telegram and WhatsApp into a 24/7 sales assistant created in a single tap,
> **unlike** complex, expensive global tools or a developer quoting 20,000 EGP,
> **because** BotYalla is Arabic-first, free forever to start, and paid with Vodafone Cash.

### The core message (published everywhere)

**Primary promise (in Egyptian dialect):**
> **"A bot for your business in one tap — it replies, sells and books while you're not holding your phone."**

**Supporting line:**
> "Start free on Telegram today, and add official WhatsApp when your business is ready. No code, no credit card, and pay with Vodafone Cash or InstaPay."

### Three supporting messages (each is an ad angle)

| # | Message | Proof |
|---|---|---|
| 1 | **"Free forever — start in a minute"** | A genuine free tier: unlimited messages, no card, no commercial registration |
| 2 | **"An employee for 299 EGP instead of 5,000"** | Replies 24/7, never forgets, never quits, logs every order |
| 3 | **"Built for Egypt — pay with Vodafone Cash"** | Local payment · Egyptian dialect · support in your timezone · a printable QR poster for your shop |

### Tone of voice

| Do ✅ | Don't ❌ |
|---|---|
| Natural Egyptian dialect | Stiff advertising Modern Standard Arabic |
| Short sentences, clear verbs | Technical jargon (API, webhook, LLM) |
| Specific numbers ("35 minutes", "165 EGP") | Superlatives ("revolutionary", "world's best") |
| Honesty about limits (WhatsApp needs a commercial registration) | Hiding conditions until the payment page |
| Real product screens | Idealised, unrealistic mockups |

> **The honesty rule:** the site clearly stating "requires a commercial registration and tax card" on the WhatsApp plan is a **trust asset, not a flaw**. In a market full of inflated promises, honesty sells. Feature it rather than hide it.

---

## 10. Offer architecture and funnel

### The full funnel

```
   Awareness       ← TikTok / Reels / Group posts (free) + Meta ads
     ↓  target: 3–5% click
   Interest        ← Homepage (the live demo above the fold)
     ↓  target: 25% reach pricing or registration
   Activation ★    ← Register (no card) ← ★★ create the bot in one tap
     ↓  target: 55%+ of registrants create a bot
   Value           ← Setup agent builds replies ← first real customer message
     ↓  target: 30% reach a real conversation
   Revenue         ← Hit a plan limit or need WhatsApp ← subscribe
     ↓  target: 5–8% free→paid within 60 days
   Expansion       ← Upgrade · message credit · annual plan (−30%)
   Referral        ← Affiliate + the QR poster in the shop (free physical marketing)
```

### The aha moment — protect it with your life

> **The moment is:** a business owner seeing **their own bot** reply to **their own message** on Telegram for the first time.

Every marketing decision should be measured against one question: **does this move them closer to that moment, or further away?**
- An ad listing features → further.
- An ad showing **a real bot replying** → closer.
- A landing page with six registration fields → further.
- Name and password, then a "Create my bot" button → closer.

**Measure this as your North Star:** `bots created ÷ signups`. **If it is below 50%, stop ad spend and fix onboarding first** — advertising into a broken funnel only multiplies the loss.

### Offer architecture — how a customer ascends

| Stage | What they get | What they pay | What pushes them up |
|---|---|---|---|
| **Free** | A full Telegram bot, unlimited messages | 0 | Wants a second bot · wants the footer removed · wants more AI replies |
| **Merchant — 299** | 3 bots, campaigns, analytics, 500 AI replies, inbox | 299/mo | Wants WhatsApp (his customers are there) |
| **WhatsApp — 899** | Official WhatsApp + your team connects it for them + 2,000 service messages | 899/mo | Starts managing bots for other clients |
| **Agency — 2,999** | Unlimited + white-label + client panel | 2,999/mo | — |

**Two clever things in your pricing — market them explicitly:**
1. **"Our team connects WhatsApp for you"** on the 899 plan — this is not a feature, it is **the removal of the single biggest obstacle in the entire product**. Make it the plan's headline, not a bullet. Connecting the WhatsApp Cloud API is what kills 90% of competitor attempts.
2. **Carrying over paid days when changing plans** — "your money isn't lost". This kills the biggest upgrade fear. Put it on the pricing page **and in every upgrade message**.

### Unit economics — the numbers that govern your spend

Conservatively:
```
Cost per click (Meta, Egypt)            ≈ 1.5 – 4 EGP
Cost per signup (8% conversion)          ≈ 25 – 50 EGP
Free → paid conversion (60 days)         ≈ 5 – 8%
Customer acquisition cost (CAC)          ≈ 350 – 900 EGP
Average revenue per user (ARPU)          ≈ 400 EGP (mix of 299/899/2,999)
Expected retention                       ≈ 8 – 14 months
Lifetime value (LTV)                     ≈ 3,200 – 5,600 EGP
```
**LTV : CAC ≈ 5:1 to 9:1** — excellent economics. **But it collapses entirely if `bot_created / sign_up` is below 50%.**

**Spending rules:**
- **Do not spend a pound on ads before measurement is installed** (§3.1 and §3.2).
- First 14 days: small spend (200–300 EGP/day) to gather data, not to make sales.
- If paid CAC exceeds **1,200 EGP**, pause and fix targeting or creative.
- Priority always: **organic first, paid to amplify what already worked organically.** Do not pay to discover what works — discover it free, then pay.

---
---

# Part III — The Launch Campaign ("The Boom")

## 11. Timeline: T-7 → T+30

> **The philosophy:** a launch is not a day — it is a **curve**. The most common mistake is posting "we're live!" once to an audience that does not know you, and watching it pass without echo. A real boom is built from **7 days of anticipation**, then **72 hours of concentrated pressure behind an expiring offer**, then **27 days of amplification and optimisation**.

> **An honest note:** you said you want to launch today. I strongly recommend seven days of preparation — new Meta accounts need warming before advertising, and measurement cannot be installed in an hour. **If today is non-negotiable, run the compressed path in §11.4.**

### Phase 0: Foundation — T-7 to T-5

| Day | Task | Output |
|---|---|---|
| **T-7** | Create all social accounts (§14) · reserve `@botyalla` everywhere · profile and cover images | 6 live accounts with one identity |
| **T-7** | Fix 🔴 measurement: GTM + GA4 + Meta Pixel + TikTok Pixel + Clarity + CSP | `sign_up` visible in Events Manager |
| **T-6** | Fix 🟠: SPF + Search Console + `ADMIN_PASS` + UptimeRobot | 9/10 on mail-tester · verified site |
| **T-6** | Shoot every media asset (§27) — one focused production day | 12 videos · 20 images |
| **T-5** | Post 3 "warm-up" videos on every platform (no link, no selling) | Accounts look alive, not born today |
| **T-5** | Write and schedule the first 14 days of content | Full calendar |

> **Why warming is mandatory:** Facebook and TikTok treat an hour-old account that posts a link and starts spending as suspicious. Three days of normal activity (posting, commenting, following) substantially reduces suspension risk. **A suspended ad account on launch day is a disaster that is hard to fix quickly.**

### Phase 1: Building anticipation — T-4 to T-1

**Goal:** 300–800 people know something is coming, and 100+ on a waitlist.

| Day | Action |
|---|---|
| **T-4** | **Teaser:** a 20-second video across all platforms — "In 4 days, any business in Egypt will be able to make a bot in one tap. Free." No link |
| **T-3** | **The story post:** a long post on Facebook and LinkedIn — *why* you built BotYalla. A real, personal story. This is the highest-engagement post of the whole campaign |
| **T-3** | **Telegram channel opens:** `t.me/botyalla` — invite everyone you know. Position it as "where the first offer drops" |
| **T-2** | **Product reveal:** a 60-second video showing the real screen, zero to working bot. **Still no link** — "link tomorrow" |
| **T-2** | **Personal outreach:** message 50 business owners you know personally on WhatsApp. **Individually written, not copy-paste** |
| **T-1** | **Countdown:** story "tomorrow at 12pm" · pin the "Founding 100" post |
| **T-1** | **Seed the groups:** post the value post (not the sell post) in 10 Facebook groups — share the lesson, mention you launch tomorrow |
| **T-1 evening** | **Final test:** full §6 checklist · prepare canned replies · sleep early |

### Phase 2: The boom — T0 to T+3 (72 hours)

**Goal:** 300–600 signups · 150+ bots created · first 10 paying subscribers.

**The mechanism:** the **"Founding 100"** offer — expires after 72 hours or 100 subscribers, whichever comes first. Genuine scarcity is what converts interest into action.

| Day | Action |
|---|---|
| **T0 — 12:00 noon** | **Simultaneous launch across every platform in the same minute.** Link everywhere. "X of 100 left" counter |
| **T0** | Meta and TikTok ads go live (200–400 EGP/day) |
| **T0** | 15 Facebook groups · WhatsApp to all your lists · email to your whole base |
| **T0** | **30-minute live stream at 8pm:** "I'll build a bot for your business right now, live" — the single strongest one-day conversion tool |
| **T+1** | Publish the first 3 bots real users created (with permission) — stronger than any ad |
| **T+1** | Reply to **every** comment and message within an hour |
| **T+2** | **Momentum update:** "120 businesses built bots in two days" + "30 spots left" |
| **T+2** | First report: which ad is working? Kill the loser, double the winner |
| **T+3** | **Final 12 hours:** hourly countdown on stories. The biggest sales spike of the campaign happens here |
| **T+3 midnight** | **Actually close the offer.** If you extend it, nobody will believe your next offer |

### Phase 3: Amplification — T+4 to T+30

| Week | Focus |
|---|---|
| **Week 1 (T+4→T+10)** | Publish results transparently ("420 businesses, how many activated, what I learned") · start retargeting · launch the affiliate programme |
| **Week 2 (T+11→T+17)** | First 3 success stories with real numbers · sector landing pages (`/restaurants`, `/clinics`) · win-back campaign for "registered but no bot" |
| **Week 3 (T+18→T+24)** | Agency campaign on LinkedIn · first two SEO articles · webinar/live "a bot for your restaurant in 20 minutes" |
| **Week 4 (T+25→T+30)** | Full numbers review · double down on winners · kill losers · annual plan campaign (−30%) |

### 11.4 The compressed path — if launching today is mandatory

Run this order **exactly**, and do not publish a link before the first block is done:

```
Hour 0–2   🔴 CSP + GTM + GA4 + Meta Pixel + Clarity          ← do not skip
Hour 2–3   🟠 SPF + Search Console + ADMIN_PASS + UptimeRobot
Hour 3–5   Create 5 social accounts with one identity (§14)
Hour 5–6   Post 2–3 "warm-up" posts on each account (no links)
Hour 6–8   Shoot 3 core videos on your phone (M-01 · M-02 · M-04)
Hour 8–9   Full §6 checklist on a real phone
Hour 9     🚀 Organic-only launch: posts + groups + WhatsApp + Telegram
Day 2–3    Post daily + reply to every comment. ❌ Still no paid ads
Day 4      Start ads after 3 days of account warming
```

> **Do not skip the first block, whatever the pressure.** Launching without measurement means that in a month you will not know what worked — and you will repeat the same mistakes with a bigger budget.

---

## 12. The anchor offer: "Founding 100"

### The offer

> ### 🔥 The Founding 100
> **The first 100 businesses to subscribe within 72 hours get:**
> - **50% off the first 3 months** on any paid plan
> - **or 40% off annual** (instead of 30%) — locked for the life of the subscription
> - **Free bot setup by our team** (genuine 500 EGP value)
> - **A "Founding Member" badge** on the account, permanently
> - **Access to a private WhatsApp group** with the founder directly
> - **A vote on upcoming features** — their input shapes the roadmap
>
> **Ends after 72 hours or at 100 members — whichever comes first.**

### Why this offer specifically

| Element | Psychological function |
|---|---|
| **Limited count (100)** | **Verifiable** scarcity — a visible counter makes it real |
| **Limited time (72 hours)** | Blocks procrastination, the #1 conversion killer in Egypt |
| **Discount on 3 months, not forever** | Protects long-term revenue and gives enough time to build habit |
| **Free setup** | Removes the "I won't be able to configure it" fear — **the genuinely strongest element** |
| **Badge + private group** | Status and belonging — creates advocates, not just subscribers |
| **Feature voting** | Turns customers into partners — your best source of testimonials and case studies |

> **Execution wisdom:** "free setup" outperforms the discount by a wide margin in this market. A discount lowers the price; free setup **removes the risk**. Since you already have an AI setup agent and a team that connects WhatsApp, its cost to you is low and its perceived value is very high. **If you must choose one, keep the free setup and drop the discount.**

### Mechanics

- **One promo code:** `FOUNDER100` — your discount-code engine is already built.
- **The counter:** a site-wide banner reading "**73** spots left of 100". Update it manually three times a day — a visibly manual update builds more credibility than a suspicious automatic counter.
- **Transparency:** post the real number on stories every day. If it is slow, say so. **Honesty sells in Egypt better than manufactured hype.**
- **Actually close it:** disable the code at the exact deadline. Post "offer closed — thank you to the 87 businesses who joined". **The credibility of your next offer is built right here.**

### The permanent offer after launch

Once the offer ends, the standing message becomes:
> **"Start free forever — no card, no commercial registration, no commitment."**

The free tier is always your strongest offer. Do not devalue it with rolling discounts — repeated discounting trains the market to wait for one.

---

## 13. Launch day — hour-by-hour war room

### Before bed (T-1)

- [ ] Every post scheduled and written (write nothing on launch day)
- [ ] Every video uploaded as a draft
- [ ] Canned replies to the 10 expected questions written in a file
- [ ] §6 checklist fully executed ✅
- [ ] Telegram alerts for new orders enabled on your phone
- [ ] Admin panel open on a second device — **payment approval is manual and no customer should wait an hour**
- [ ] Full battery · backup internet · someone briefed to help you reply

### The day

| Time | Action | Signal |
|---|---|---|
| **08:00** | Final check: site loads · tracking fires · email delivers | All green |
| **10:00** | "2 hours to go" story on every platform | — |
| **11:45** | Open: GA4 realtime · Meta Events Manager · admin panel · all social apps | — |
| **🚀 12:00** | **Simultaneous publish across all platforms + Telegram channel + WhatsApp messages** | First visit within 5 minutes |
| **12:15** | Turn on ads (if accounts are warmed) | — |
| **12:30–14:00** | **The golden window:** reply to every comment within 2 minutes. First-hour engagement determines the post's entire reach | 20+ interactions |
| **14:00** | Post in 15 Facebook groups (spread over two hours, not one batch) | — |
| **15:00** | **First checkpoint:** how many signups? how many bots? what's `bot_created/sign_up`? | ≥50% |
| **16:00** | "First X businesses built their bots" story with a real screenshot | — |
| **18:00** | **Technical check:** 429 logs · 500 errors · Brevo counter · server load | Zero errors |
| **20:00** | **30-minute live stream:** build a bot live for a business the viewers suggest | 30+ viewers |
| **21:00** | Cut clips from the stream into Reels/TikToks | — |
| **22:00** | End-of-day story with real numbers + thanks | — |
| **23:00** | **Review:** best post? best ad? most repeated question? Write one answer for tomorrow | — |

### Warning signals and immediate response

| Signal | Meaning | Do immediately |
|---|---|---|
| Many signups, few bots (<40%) | Onboarding is broken | Open Clarity and watch recordings · **pause ads** until fixed |
| Much traffic, few signups (<4%) | The message or the page is not convincing | Change the ad headline · try another angle |
| Rising 429 errors | The rate limit is choking customers (§4.6) | **Raise the limit on the server immediately** |
| Email not arriving | Brevo passed 300/day, or SPF | Upgrade Brevo now · verify SPF |
| Ad account suspended | New account + link + spend | Do not create a new account — **file an appeal** and continue organically |
| Public negative comment | Normal and expected | Reply publicly, politely, with a solution, then move to DM. **Delete only abuse** |

---
---

# Part IV — Setting Up Social Accounts Professionally

## 14. The golden rule before any account

> **One identity, perfectly consistent across every platform.** Same name, same image, same description, same link. Someone who sees you on TikTok and then searches Facebook must recognise you in a fraction of a second.

### Identity kit — prepare this before opening any account

| Element | Value |
|---|---|
| **Display name** | `BotYalla \| بوت يلا` |
| **Handle** | `@botyalla` — reserve it everywhere now, even on platforms you won't use |
| **Profile image** | `mark.svg` as 500×500 PNG, logo centred on dark `#05070D`. **No text** — it disappears at small sizes |
| **Cover** | 1640×856 (Facebook) · the bot replying + the line "A bot for your business in one tap" |
| **Short bio (150 chars)** | `Telegram & WhatsApp bots for your business — no code. Replies, sells and books 24/7. Start free 🇪🇬` |
| **Long description** | "BotYalla is an Egyptian platform that lets any business create a Telegram or WhatsApp bot in one tap — no code, no developer. The bot answers your customers, takes orders and bookings, and logs them in your dashboard. Start free forever, and pay with Vodafone Cash or InstaPay." |
| **Link** | `https://botyalla.com/?utm_source=<platform>&utm_medium=bio` |
| **Category** | Software Company / Technology Company |
| **Colours** | Background `#05070D` · cyan/violet accents from the logo |
| **Fonts** | Cairo (Arabic headings) · Noto Kufi Arabic (heavy headings) · Inter (English) |

> **UTM is mandatory:** use a different `utm_source` per platform. Without it GA4 lumps everything under "direct" and you will never know which platform brings customers. **These are the most valuable five minutes in the entire setup.**

---

### 14.1 Facebook — Business Page + Business Manager

**The order matters:** personal account (exists) → Page → Business Manager → ad account → pixel.

1. `facebook.com/pages/create` → name `BotYalla` → category **Software Company** → short description.
2. Profile image + cover + link + contact info (WhatsApp `+201097585951`).
3. **Add a CTA button:** "Sign Up" → `https://botyalla.com/register?utm_source=facebook&utm_medium=cta`
4. **`business.facebook.com`** → Create Business Portfolio → legal name → official email.
5. Business Settings → Accounts → Pages → Add → link your Page.
6. Business Settings → Ad Accounts → Create → currency **EGP**, timezone **Cairo**.
   > ⚠️ **Currency and timezone cannot be changed after the first spend.** Get it right first.
7. Events Manager → Connect Data Source → Web → Meta Pixel → name it `BotYalla Pixel` → **copy the Pixel ID**.
8. **Enable Conversions API** (Settings → Conversions API → Set up) — it recovers what the browser pixel loses to ad blockers and substantially improves attribution. **Do not skip it.**
9. **Verify your domain:** Business Settings → Brand Safety → Domains → Add `botyalla.com` → add the `meta-tag` to the site → Verify. **Mandatory** to control conversion events post-iOS 14.
10. **Aggregated Event Measurement:** prioritise `Purchase` → `CompleteRegistration` → `Lead` → `ViewContent`.

**Free offers:** Meta periodically offers **free ad credit (150–400 EGP)** to new Pages — it appears as a notification in Ads Manager. Check a week after creating the Page. **Meta Blueprint** is also entirely free for training.

---

### 14.2 Instagram — linked Business account

1. Install the app → Sign up → username `botyalla` → same image.
2. **Settings → Account type → Switch to Professional → Business → Software Company.**
3. **Link it to your Facebook Page** — this unlocks unified publishing, ads, Insights, Shop, and one shared inbox.
4. **Bio (150 chars) — use line breaks and emoji:**
   ```
   🤖 Telegram & WhatsApp bots for your business
   ⚡ One tap — no code
   🇪🇬 Free forever · Vodafone Cash
   👇 Start now
   ```
5. Bio link: `botyalla.com/?utm_source=instagram&utm_medium=bio`
6. **Create 3 empty Highlights now:** `Get Started` · `Success Stories` · `Pricing` — fill them from day one.

---

### 14.3 TikTok — account + Business Center

> **TikTok is the cheapest and fastest organic reach in Egypt today. If your time is limited, start here.**

1. `tiktok.com` → Sign up → username `botyalla`.
2. **Settings → Manage account → Switch to Business Account → Software.**
   This unlocks analytics, the commercial sound library, a bio link, and the message inbox.
3. **Bio (80 chars — very short, choose carefully):**
   ```
   A bot for your business in one tap 🤖 Free
   Telegram + WhatsApp · no code
   ```
4. Link: `botyalla.com/?utm_source=tiktok&utm_medium=bio`
5. **`business.tiktok.com`** → TikTok Ads Manager → currency **EGP**, timezone **Cairo**.
6. Assets → Events → Web Events → Setup → **TikTok Pixel** → install via GTM.

**Free offers:** TikTok regularly runs **"spend X, get X"** matches for new ad accounts (often matching up to ~1,500 EGP). Find it in Ads Manager → Promotions or in the welcome email. **Claim it before your first spend — it is not applied retroactively.**

---

### 14.4 Telegram channel — your most important owned asset

> **This is not a marketing channel — it is your home. The only platform where you genuinely own your audience with no algorithm between you.**

1. Telegram → ☰ → New Channel → name `BotYalla 🤖` → link `t.me/botyalla` → public.
2. Description: "A bot for your business in one tap · Tutorials, updates and offers first · botyalla.com"
3. Channel image = same profile image.
4. **Attach your own support bot to the channel** — live proof the product works: a visitor tries the bot instantly.
5. **Pin a welcome message** with: what the platform is · the free start link · the support link.
6. Create a **linked discussion group** — community drives retention more than any feature.

**Use it for:** product updates · short tutorials · exclusive "channel followers first" offers · new feature announcements.

---

### 14.5 WhatsApp Business — the direct sales channel

1. Install **WhatsApp Business** (not the regular app) on `+201097585951` or a dedicated number.
2. **Complete the business profile:** name · category · description · link · hours · address.
3. **Greeting message:**
   > "Welcome to BotYalla 👋
   > You can start your bot free right now at botyalla.com
   > Any question, write it here and we'll reply shortly."
4. **Quick replies (write them now):** `/price` · `/start` · `/whatsapp` · `/payment` · `/support`
5. **Labels:** `interested` · `trialling` · `subscribed` · `agency` · `follow-up`
6. **WhatsApp Status:** post daily — the highest view rate of any platform in Egypt.
7. **A `wa.me` link with prefilled text:**
   `https://wa.me/201097585951?text=I%20want%20to%20know%20more%20about%20BotYalla`

---

### 14.6 LinkedIn — the agency and partner channel

1. `linkedin.com/company/setup/new` → `BotYalla` → URL `linkedin.com/company/botyalla`.
2. Category: Software Development · Size: 2–10 · HQ: Cairo, Egypt.
3. **Description in English** (LinkedIn's Egyptian audience is mixed and professional):
   > "BotYalla helps Egyptian small businesses turn Telegram and WhatsApp into a 24/7 sales assistant — built in one tap, no code required. Arabic-first, local payments, free forever tier."
4. **Link it to your personal profile** — on LinkedIn, **the founder's account massively outperforms the company page** for reach. Post from your personal account and share to the page.
5. Update your profile: `Founder & CEO at BotYalla` + a branded banner.

---

### 14.7 YouTube — the long-term asset

1. Create a channel named `BotYalla` → URL `youtube.com/@botyalla`.
2. Banner 2560×1440 · same image · description + link.
3. **You do not need much content yet** — three videos suffice:
   - "How to build a Telegram bot for your business in 3 minutes" (full walkthrough)
   - "Telegram bot vs WhatsApp bot — which one is right for you"
   - "A full tour of the BotYalla dashboard"
4. Use **Shorts** to repost your TikTok videos — free extra reach at zero effort.

**Why YouTube matters despite being slow:** tutorial videos bring organic search **forever**. A "how do I build a WhatsApp bot" video will still bring customers in two years.

---

### 14.8 X (Twitter) — low priority

Reserve `@botyalla` now so nobody else takes it. Repurpose your content there. Do not invest time in it for the first three months — Egypt's small-business audience is not densely here.

---

### 14.9 Supporting tools (all free)

| Tool | Use | Note |
|---|---|---|
| **Meta Business Suite** | Schedule Facebook + Instagram, unified inbox | Completely free — use it as your operations hub |
| **Canva** | All design | **Canva Pro is free for 30 days** — use it in launch week to produce every asset at once |
| **CapCut** | Short-video editing | Free, and made by TikTok's parent — its templates are tuned for the platform |
| **Google Tag Manager** | All tracking tags | Free |
| **Microsoft Clarity** | Session recordings + heatmaps | **Free, unlimited** — the best deal in the market |
| **Linktree / link-in-bio** | Unnecessary | Every bio accepts one link — point it straight at the site with UTM |
| **Notion / Trello** | Content calendar | Optional |

---
---

# Part V — Per-Platform Execution Guides

## 15. Facebook & Instagram — the primary acquisition engine

### Organic — the weekly rhythm

| Day | Type | Example |
|---|---|---|
| Saturday | **Educational** — "how to" | "3 replies every restaurant bot must know" |
| Sunday | **Social proof** | A customer's bot screenshot + a real number |
| Monday | **Pain** — hits the nerve | "The message you didn't answer yesterday… who got that order?" |
| Tuesday | **Product demo** — screen video | 30 seconds: zero to working bot |
| Wednesday | **Story / behind the scenes** | "Why I built BotYalla" · "the hardest part of the product" |
| Thursday | **Engagement / question** | "What's the question your customers ask most?" |
| Friday | **Offer / call to action** | "Start free" + link |

**Operating rules:**
- **Reels first.** Meta gives Reels far more organic reach than images. Make 60% of your content vertical 9:16 video.
- **Put the link in the first comment, not the post** for organic posts — Facebook suppresses posts that send people off-platform.
- **Reply to every comment within an hour.** Early engagement determines the post's total reach.
- **Do not post the identical text to Facebook and Instagram** — shorten for Instagram, go long on Facebook.
- **Egypt's Facebook audience reads long posts.** Don't fear 200 words if it is a real story.

### Paid — campaign structure

**Stage 1 — Testing (T0 → T+7) · 200–300 EGP/day**

```
Campaign: BY | Traffic | Test
Objective: Traffic — cheap, fast data
Ad sets (3):
  AS-1 | Business interests  → page admins, entrepreneurs, e-commerce
  AS-2 | Sector interests    → restaurants, clinics, clothing shops
  AS-3 | Broad               → 25–45, Egypt, no interests (let the algorithm learn)
Creatives: 4 per ad set (2 video, 1 image, 1 carousel)
```

**Stage 2 — Conversions (T+8 → T+21) · 400–600 EGP/day**

```
Campaign: BY | Conversions | SignUp
Objective: Conversions → CompleteRegistration
Ad sets:
  CV-1 | Best audience from stage 1
  CV-2 | Lookalike 1% of registrants  ← needs at least 100 conversions
  CV-3 | Retarget: visited in 30 days, did not register   ← always cheapest
  CV-4 | Retarget: registered, no bot created             ← highest return
```

**Stage 3 — Scaling (T+22+)**
Increase budget 20% every 3 days on winners only. **Never double in one step** — it resets the campaign to learning and destroys optimisation.

### Retargeting — the cheapest money in the campaign

| Audience | Message | Priority |
|---|---|---|
| Viewed pricing, did not register | "The free plan isn't a trial — it's free forever" | ★★★ |
| **Registered, no bot created** | "Your bot is one tap away — let's finish it in a minute" | ★★★★ |
| Created a bot, did not subscribe | "Your customers are on WhatsApp — connect your bot to them" | ★★★ |
| Watched 50%+ of a video | "Saw how it works? Try it yourself, free" | ★★ |

> **The most important note in this section:** the "registered, no bot" audience is **the highest return on ad spend in the entire campaign**. These people have already proven intent and stopped at one obstacle. Hit them with an ad, an email, *and* a WhatsApp message.

### Ready ad copy (5 tested angles)

**Angle 1 — Pain**
> **Headline:** The message you didn't answer… who got that order?
> **Body:** Every day you miss messages while you're busy. Every missed message is an order someone else won.
> BotYalla builds you a Telegram or WhatsApp bot that replies in a second, takes orders and bookings, and logs them all in your dashboard.
> One tap. No code. **Free forever.**
> **CTA:** Start free

**Angle 2 — Economic comparison**
> **Headline:** A 5,000 EGP employee to answer messages… or a 299 EGP bot?
> **Body:** The employee sleeps, forgets, and quits. The bot replies 24/7, logs every order, and forgets nothing.
> Start free on Telegram today.
> **CTA:** See pricing

**Angle 3 — Ease**
> **Headline:** A bot for your business in 60 seconds — no developer
> **Body:** No BotFather, no code, no one to call. Press a button, confirm in Telegram, and your bot is live and linked to your account — with a direct link, a QR code, and a printable A4 poster for your shop.
> **CTA:** Build your bot now

**Angle 4 — Local (strongest in Egypt)**
> **Headline:** Built for Egypt — pay with Vodafone Cash
> **Body:** No international credit card, no dollar account. Vodafone Cash, InstaPay, or bank transfer, priced in EGP.
> Fully Arabic, with support in your timezone.
> **CTA:** Start free

**Angle 5 — Sector-specific (repeat per sector)**
> **Headline:** Your restaurant answers its own orders — while you're in the kitchen
> **Body:** Menu with prices, cart, and order — all inside the chat. The bot collects name, phone and address, and the order reaches you organised on Telegram.
> Try it free — free forever.
> **CTA:** Start free

---

## 16. TikTok — the cheapest reach in Egypt

### Why TikTok first

One successful TikTok can reach 100,000 Egyptians **at zero cost**. No other platform in Egypt offers that today. **Even if you never master the platform, the possibility alone justifies daily posting.**

### Format rules

| Rule | Detail |
|---|---|
| **Length** | 15–35 seconds. Shorter reaches further |
| **First 2 seconds** | Decide everything. Open with motion, large text, or a shocking question. **Never a logo first** |
| **On-screen text** | Mandatory — 80% watch without sound |
| **Audio** | A trending sound plus your voiceover. Trending audio genuinely lifts reach |
| **Voiceover** | Egyptian dialect, fast, high energy |
| **Face** | Show your face. Faces substantially lift engagement in the Egyptian market |
| **Cadence** | 1–2 per day. On TikTok, volume drives discovery more than polish |
| **Hashtags** | 3–5 only: `#مشروعك` `#مصر` `#تجارة_الكترونية` `#بوت` `#واتساب_بيزنس` |

### 10 video ideas for week one

1. **"I built a bot for a restaurant in 60 seconds — watch"** — a real, uncut screen recording. The strongest of all.
2. **"If you own a shop and reply to WhatsApp yourself, this is for you"** — direct to camera.
3. **"Telegram bot vs WhatsApp bot"** — simple explainer of a very common question.
4. **"A QR poster in your shop = customers talking to your bot"** — show the real poster hanging in a shop.
5. **"A bot that replies at 2am"** — black screen, 2:14, notification, instant reply.
6. **"They quoted you 20,000 for a bot?"** — a wry reaction to agency pricing.
7. **"3 replies every restaurant bot needs"** — pure value, no selling.
8. **"My first customer told me the bot sold for him"** — the real screenshot.
9. **"Why I built this platform"** — personal story, your face, honesty.
10. **"Try our bot right now"** — scan a QR on screen and watch the live reply.

### Cross-posting

Post **every** TikTok to Instagram Reels, Facebook Reels, and YouTube Shorts.
> **Remove the TikTok watermark first** (CapCut → export without watermark, or SnapTik). Meta suppresses videos carrying a competitor's watermark.

### TikTok ads

- Start with **Spark Ads** — boost an organic post that already performed, instead of building an ad from scratch. Cheaper and more native.
- Budget: 150–250 EGP/day for testing.
- Targeting: Egypt · 24–45 · interests: small business, e-commerce, entrepreneurship.
- **The rule:** only boost a video that passed 10,000 organic views. The algorithm has already voted for it.

---

## 17. Facebook Groups — the highest-intent hidden channel

> **This channel may outperform paid ads in your first two months. Do not skip it.**

In Egypt, small-business owners live in Facebook groups. These contain people **asking, in their own words**, for exactly the solution you sell.

### Targeting

Find and join 20–30 groups:
```
"Small business owners in Egypt"      "E-commerce Egypt"
"Restaurants & cafés — management"    "Social Media Egypt"
"Freelancers Egypt"                   "Online stores Egypt"
"Clinic owners"                       "Entrepreneurship Egypt"
"Dropshipping Egypt"                  "Digital marketing Egypt"
```

### The 80/20 rule — respect it or get banned

- **80% pure value:** answer people's questions with no mention of your product. Explain, help, share experience.
- **20% mentioning your product** — and only where it is the natural answer to the question.
- **Post no links for the first two weeks.** Build reputation first.
- **Read each group's rules.** Some ban links entirely — there, make people ask you in DMs.

### Ready templates

**The "value" template (post in 10 groups at T-1):**
> Something I learned working with shop owners this past year:
> More than half of lost orders are not lost over price — they are lost because **nobody replied fast enough**.
> A customer sends "how much?" at 11pm, nobody answers until morning, and by then they have bought elsewhere.
> Three simple things that reduce this without spending anything:
> 1️⃣ An instant auto-reply: "we got your message, we'll reply within X"
> 2️⃣ A ready menu/catalogue sent in one tap, not a fresh photo every time
> 3️⃣ Identify the two questions that make up 80% of messages and prepare a fixed reply
> Try them and tell me how it goes.

**The "launch" template (T0, in groups that allow it):**
> Today I launched something I've been building for months 🇪🇬
> **BotYalla** — it lets any business create a Telegram or WhatsApp bot **in one tap**, with no coding and no developer.
> The bot answers your customers, takes orders and bookings, and logs them in a dashboard.
> **Free forever** on Telegram — no credit card and no commercial registration.
> I built it because every existing tool is in English, requires an international Visa card, and is expensive. This one is in Arabic, priced in EGP, and paid with Vodafone Cash.
> I'd be honoured if you tried it and told me honestly what you think — link in the first comment 👇
> *(And if anyone needs help setting it up, message me and I'll help you personally, free.)*

> **That last line is the most important one.** Offering free personal help turns an ad post into a community post — and brings you your first customers.

---

## 18. Telegram — your home and your owned audience

| Activity | Detail |
|---|---|
| **Channel `t.me/botyalla`** | 3–5 posts per week: updates, tutorials, exclusive offers |
| **Support bot** | Your own bot on the channel = a permanent live demo |
| **Discussion group** | Linked to the channel — user community, your highest-leverage retention tool |
| **Exclusivity** | "Offer X goes to channel followers before anyone else" — gives a reason to subscribe |
| **Broadcasts** | Use the Broadcast system built into your own platform on your own channel — **you are your own best case study** |

> **A unique marketing asset you already have:** every customer who creates a bot gets a link and a QR poster. **Every poster hanging in a shop is a free billboard for you.** Run a programme: "print the poster, photograph it in your shop, send us the picture → one month free." Physical marketing at zero cost.

---

## 19. WhatsApp — direct selling

### WhatsApp Status — the most underrated tool

WhatsApp Status view rates in Egypt exceed any other platform. **Post daily during launch week.**

```
Day 1: "We're launching today 🚀" + product image
Day 2: "First 20 businesses built their bots" + screenshot
Day 3: "Watch a restaurant bot working" + 15-second video
Day 4: "40 spots left in the founders offer" + counter
```

### Direct outreach (manually and respectfully)

Message 100 business owners you know or find on Facebook:

> "Hi [name], I'm Youssef.
> I saw [business name]'s page and I liked what you do.
> I built a platform that lets any business create a Telegram or WhatsApp bot that answers customers and takes orders — **in one tap, free**.
> I'm honestly not selling you anything — I just want your opinion, because I learn from owners like you.
> Want me to send you a link to try it? Two minutes, no more."

**Rules you don't break:**
- **Personalise every message.** Name the business specifically. Copy-paste is detected instantly and burns your reputation.
- **Never message numbers that haven't engaged with you.** WhatsApp bans are real and painful.
- **20–30 messages per day maximum** from one number.
- **Ask for an opinion, not a sale.** Response rates double.

### Inside the product

You have a WhatsApp campaign system (3.28 EGP per marketing message from prepaid credit). **Use it on your own customer base** — and turn that into content: "how I use my own product." Transparency builds trust.

---

## 20. LinkedIn — the agency channel

**The audience here is entirely different:** freelancers, agencies, marketing managers. Don't sell them "a bot for your restaurant" — sell them **"add a new service for your clients without a developer."**

**Cadence:** two posts a week **from your personal account** (not the company page).

**Angles that work on LinkedIn:**
1. **The building journey:** "I built a SaaS in Egypt — the numbers and lessons, honestly"
2. **The technical lesson:** "Why I chose SQLite over PostgreSQL — and when I'll switch"
3. **Market reading:** "Why global tools fail in the Egyptian market"
4. **The partnership pitch:** "If you manage social media for clients, here's how to add a service at 100% margin"
5. **Transparency with numbers:** "First 30 days after launch — all the numbers"

> **"Build in public" posts have the highest reach on Arabic LinkedIn.** Share real numbers — failures as well as wins. This builds authority and brings partners, investors and hires, not just customers.

**Direct targeting:** search `Social Media Manager` + `Egypt`, send a connection request with a short note, and after acceptance offer the Agency plan at a partner rate.

---

## 21. Google — SEO, Maps and Ads

### 21.1 SEO — your most important long-term investment

**Your foundation is already excellent** (§2). What is missing is **content**.

**The first 8 articles — in priority order:**

| # | Target title | Search intent |
|---|---|---|
| 1 | How to build a Telegram bot for your business without coding (2026 guide) | Educational, high intent |
| 2 | WhatsApp business bots: the complete WhatsApp Cloud API guide for Egypt | Educational — a hard, valuable keyword |
| 3 | The best way to auto-reply to your customers — solutions compared | Comparison — buying intent |
| 4 | A bot for your restaurant: taking delivery orders on Telegram | Sector |
| 5 | A bot for clinics: automatic appointment booking | Sector |
| 6 | What does a WhatsApp bot cost in Egypt in 2026? | Very high buying intent |
| 7 | An Arabic ManyChat alternative: pricing and features compared | Competitor comparison |
| 8 | How to let customers order without you speaking to them | Pain |

**Writing rules:**
- 1,200–2,000 words, **in Arabic, with clear H2/H3 structure**.
- Every article ends with a call to action: "try it free".
- Interlink the articles.
- **Add `Article` schema** to each.
- **One excellent article beats five mediocre ones.** Publish one a week at high quality.

### 21.2 Google Business Profile

Create a business profile on Google Maps as `BotYalla` (even though you are online-only — choose "Service area business" and set Egypt). **It gives you brand-search visibility and a knowledge panel**, a strong trust signal in the Egyptian market.

### 21.3 Google Ads — later, not now

**Do not start Google Ads in month one.** Arabic search volume for "WhatsApp bot" is limited, and you will spend on broad, low-intent keywords.
**Start in months 2–3, and only on buying-intent keywords:**
```
"build whatsapp bot"  ·  "telegram bot for shops"  ·  "whatsapp auto reply"
"arabic chatbot"      ·  "ManyChat alternative"    ·  "restaurant bot"
```
Budget 100–200 EGP/day · phrase match, not broad · a dedicated landing page per ad group.

---

## 22. Email — highest return, lowest cost

**You already have an email campaign system. Use it from day one.**

### Welcome sequence (automated — 5 emails)

| # | Timing | Subject | Goal |
|---|---|---|---|
| 1 | Immediately | "Welcome — your bot is one tap away" | Bot creation (direct link) |
| 2 | +1 day | "Set up your bot in 3 minutes" | The AI setup agent |
| 3 | +3 days | "See how a restaurant takes its orders" | Success story |
| 4 | +7 days | "Your customers are on WhatsApp — connect your bot" | Upgrade |
| 5 | +14 days | "What's standing in your way?" | **An open question — starts a conversation and brings your most valuable feedback** |

### Win-back campaigns

| Segment | Message |
|---|---|
| **Registered, no bot** (★ most important) | "Your bot needs one tap — want me to help?" |
| Created a bot, never configured replies | "Let the AI agent set it up for you in a minute" |
| Active, not subscribed (after 30 days) | "You've hit the free plan limit — here's what's next" |
| Subscription about to expire | "Your subscription ends in 3 days" + 30% annual discount |

> **Capacity warning:** Brevo free = 300 emails/day for everything. Welcome sequences + receipts + password resets will consume that fast after launch. **Upgrade before you hit the wall** — an undelivered password reset is a lost customer.

---
---

# Part VI — Content

## 24. The five content pillars

| Pillar | Share | Purpose | Examples |
|---|---|---|---|
| **Educational** | 30% | Builds authority, gets shared | "3 replies every restaurant bot needs" |
| **Product demo** | 25% | Proves it is real and easy | Screen recording, zero to bot |
| **Social proof** | 20% | Removes risk | Customer screenshots, numbers, testimonials |
| **Pain / problem** | 15% | Stops the scroll | "The message you didn't answer…" |
| **Behind the scenes** | 10% | Builds relationship | Your story, your decisions, your mistakes |

---

## 25. 30-day calendar

**Key:** 🎥 short video · 📸 image/carousel · 📝 text post · 📧 email · 🔴 live · 💬 groups

### Launch week

| Day | TikTok/Reels | Facebook | Instagram | LinkedIn | Telegram | Other |
|---|---|---|---|---|---|---|
| **T-4** | 🎥 teaser 20s | 📝 teaser | 📸 story | — | — | — |
| **T-3** | 🎥 "why I built it" | 📝 the long story | 📸 carousel | 📝 building journey | channel opens | — |
| **T-2** | 🎥 product reveal 60s | 🎥 same | 🎥 reel | — | channel announce | 💬 WhatsApp to 50 |
| **T-1** | 🎥 "tomorrow" | 📝 countdown | 📸 story | — | pin the offer | 💬 10 groups (value) |
| **🚀 T0** | 🎥 launch | 📝 launch + 🎥 | 🎥 + story | 📝 launch | announce | 💬 15 groups · 📧 · 🔴 8pm |
| **T+1** | 🎥 first bots | 📸 user screenshots | 📸 | — | update | 💬 reply to everyone |
| **T+2** | 🎥 "120 businesses" | 📝 momentum | 📸 counter story | 📝 day one in numbers | update | 📧 reminder |
| **T+3** | 🎥 final 12 hours | 📝 last chance | 📸 hourly countdown | — | final call | 📧 last chance |

### Week 2

| Day | Content |
|---|---|
| 8 | 🎥 "how to build a restaurant bot" · 📝 launch results, fully transparent |
| 9 | 🎥 "Telegram vs WhatsApp" · 📸 comparison carousel |
| 10 | 🎥 real customer testimonial · 📧 "registered, no bot" campaign |
| 11 | 🎥 "a QR poster in your shop" · 📝 tip for retail |
| 12 | 🎥 feature demo (inbox) · 🔴 live Q&A |
| 13 | 🎥 "3 questions your customers ask" · 📸 |
| 14 | 📝 week in numbers · channel update |

### Week 3

| Day | Content |
|---|---|
| 15 | 🎥 success story with numbers · 📝 full case study |
| 16 | 🎥 "if you run a clinic" · launch `/clinics` |
| 17 | 📝 **LinkedIn: the agency offer** · start direct outreach |
| 18 | 🎥 white-label demo · 📧 agency campaign |
| 19 | 🎥 "the biggest mistake shop owners make" · 💬 groups |
| 20 | 🔴 webinar: "a bot for your restaurant in 20 minutes" |
| 21 | 📝 review + publish webinar clips |

### Week 4

| Day | Content |
|---|---|
| 22 | 🎥 "Bot Brain" (AI) demo |
| 23 | 📝 **first SEO article** + distribute everywhere |
| 24 | 🎥 second testimonial · 📧 upgrade campaign |
| 25 | 🎥 "why annual is cheaper" · 📸 savings calculator |
| 26 | 💬 second round of groups (new content) |
| 27 | 🎥 "you asked me a lot about…" — answer FAQs |
| 28 | 📝 **second SEO article** |
| 29 | 🔴 live: "30 days after launch — all the numbers" |
| 30 | 📝 **full transparent monthly report** + next month's plan |

> **The consistency rule:** one brilliant day followed by a week of silence equals zero. **An average day, every day, always wins.** If time is short, shoot 10 videos in one weekly session and schedule them.

---

## 26. Hook bank (first 3 seconds)

```
"The message you didn't answer yesterday… who got that order?"
"If you reply to WhatsApp yourself, this will save you hours"
"Someone quoted you 20,000 for a bot? Watch this"
"I built a restaurant bot in 60 seconds — no code"
"Your customer asks at 2am. You're asleep. The bot isn't."
"3 things every shop's bot must know"
"This poster in your shop = customers ordering by themselves"
"No developer. No Visa card. And free."
"I'm not selling you anything — just look at this"
"The most expensive employee in your shop… is the one who doesn't reply"
"Before you pay anyone for a bot, watch this"
"5,000 EGP employee… or a 299 EGP bot?"
```

## 26.2 Objection handling — memorise these

| Objection | Response |
|---|---|
| "I won't be able to set it up" | "There's an AI agent that asks you a few questions about your business and builds all the replies itself — and you see a preview before applying. And if you still need help, our team will set it up for you." |
| "It'll answer my customers wrong" | "You see every conversation in the inbox, and you can press 'take over' — the bot goes silent with that customer and you reply yourself." |
| "Why free? What's the catch?" | "The free plan is a full Telegram bot with unlimited messages — genuinely free forever. We make money when your business grows and needs WhatsApp or more bots." |
| "I don't want to give you Telegram credentials" | "We will never ask for your number or login code. The bot is created with your approval inside Telegram itself, or with a BotFather token if you prefer." |
| "I don't have a commercial registration" | "Telegram needs no paperwork — start today. Registration is only needed for official WhatsApp, and that's Meta's requirement, not ours." |
| "Too expensive" | "The free plan is free forever. And if you try it and like it, 299 EGP a month is about 10 EGP a day — far less than an employee." |
| "I don't have a Visa card" | "You don't need one. Vodafone Cash, InstaPay, or bank transfer." |
| "What if I change my mind?" | "There's no auto-renewal — renewing is in your hands. And if you change plans, your paid days carry over in value to the new plan." |

---
---

# Part VII — Media Assets: A Detailed Brief for Every File

> **How to use this part:** every asset has a filename, dimensions, duration, and a scene-by-scene description. Hand this section straight to a designer or videographer — or shoot it yourself with a phone and CapCut. **Priority:** ★★★ = don't launch without it · ★★ = week one · ★ = month one.

## 27.1 Static identity assets

| File | Size | Description |
|---|---|---|
| `by-avatar.png` ★★★ | 500×500 | `mark.svg` logo in white/cyan, centred on dark `#05070D` with a soft cyan glow. 15% margin all round. **No text at all** — it must read at 40px |
| `by-cover-fb.png` ★★★ | 1640×856 | Left of frame: a phone showing a real bot conversation (customer message + instant reply). Right: "A bot for your business in one tap." in heavy Noto Kufi Arabic, with `botyalla.com` and Telegram/WhatsApp icons beneath. Dark gradient background. **Leave the central 20% empty** — the profile image covers it on mobile |
| `by-cover-yt.png` ★★ | 2560×1440 (safe area 1546×423) | Same identity, text dead-centre within the safe area |
| `by-cover-li.png` ★★ | 1128×191 | A horizontal strip: logo right, "Telegram & WhatsApp bots for your business — no code" left, in English |
| `by-og-ar.png` ✅ | 1200×630 | **Already exists and works** |
| `by-og-en.png` ✅ | 1200×630 | **Already exists and works** |

---

## 27.2 Video — the most important assets

### ★★★ M-01 — "Zero to working bot" (the main launch film)
**Format:** 1080×1920 (9:16) · **Duration:** 55–70s · **Use:** homepage · every platform · primary ad

| Time | Scene | On-screen text |
|---|---|---|
| 0:00–0:03 | **A hand holding a phone, WhatsApp notifications stacking up fast.** Fast, irritating motion | "47 messages… and nobody replied" |
| 0:03–0:08 | Cut to your face, a sigh, then a smile | "There's an easier way" |
| 0:08–0:20 | **Real screen recording:** open botyalla.com → register → press "Create my bot" → confirm in Telegram → bot ready | "One tap" |
| 0:20–0:32 | The setup agent asks questions, you type one line about the business, the replies build on screen | "The AI agent sets it up" |
| 0:32–0:45 | **A second phone:** you send "do you deliver?" → the bot replies instantly with menu buttons | "And it answers your customers" |
| 0:45–0:55 | Dashboard: the order appears, organised, plus a Telegram notification | "And the order reaches you organised" |
| 0:55–1:05 | Logo + `botyalla.com` + "free forever" | "Start free — botyalla.com" |

**Production notes:** voice it yourself in Egyptian dialect, energetic and quick. Light rhythmic music. **Real screen recordings, no exaggerated speed-ups** — credibility is everything here. Add English subtitles for the international cut.

---

### ★★★ M-02 — "The lost message" (the pain film)
**Format:** 9:16 · **Duration:** 20–25s · **Use:** TikTok · Reels · expected top-performing ad

| Time | Scene | Text |
|---|---|---|
| 0:00–0:03 | Black screen, phone clock at **2:14am**, a WhatsApp notification lights up | "2:14 AM" |
| 0:03–0:07 | Customer message: "do you have this size?" · **no reply** · screen dims | "You're asleep" |
| 0:07–0:12 | Morning, you reply: "yes we have it" · customer: "sorry, I bought it elsewhere" | "Customers don't wait" |
| 0:12–0:18 | Same scenario **with the bot:** 2:14am → instant reply with sizes → completed order | "With BotYalla" |
| 0:18–0:23 | A "New order #1043" notification on your phone | "The order waited for you" |
| 0:23–0:25 | Logo + link | "botyalla.com · free" |

---

### ★★★ M-03 — "5,000 EGP employee or a 299 EGP bot" (economic comparison)
**Format:** 9:16 · **Duration:** 25–30s

A vertical split screen throughout:
- **Right — "Employee":** person icon · `5,000 EGP/month` · appearing in sequence: `sleeps 😴` · `forgets 🤯` · `quits 🚪` · `8 hours only ⏰`
- **Left — "BotYalla":** bot icon · `299 EGP/month` · appearing: `24/7 ⚡` · `never forgets 🧠` · `never quits ✅` · `logs every order 📊`

The right side fades out, the left glows. Close on: "Start free — without paying a pound." **Voice it calmly and confidently, not salesy.**

---

### ★★★ M-04 — "The QR poster" (the viral asset)
**Format:** 9:16 · **Duration:** 15–20s · **Highest viral potential**

Real footage in a shop: your hand hangs an A4 QR poster beside the till. A customer scans it. The bot opens and replies with the menu. The customer orders. The order notification lands on your phone while you stand there. **No voiceover** — music only, with short text cards: "One poster" → "in your shop" → "and your customers order by themselves" → "Start free".

> **Shoot this in a real shop.** If you don't have one, arrange with any shop owner you know — offer them a free year in exchange for filming. This video is worth that price.

---

### ★★ M-05 — "How to build a restaurant bot" (long tutorial)
**Format:** 16:9 · **Duration:** 3–4 min · **Use:** YouTube · SEO · `/restaurants` page
A full, uncut screen recording: create account → bot → menu with prices → cart → test an order → order arrives. Your voice explaining every step. **This is the video that will bring you organic search for years.**

### ★★ M-06 — "Telegram vs WhatsApp"
9:16 · 40s · split screen. Telegram: `free · instant · no paperwork · unlimited messages`. WhatsApp: `official · where your customers are · needs commercial registration · Meta templates`. Close: "Start with Telegram today, add WhatsApp when you're ready."

### ★★ M-07 — Customer testimonial template
9:16 · 20–30s · **a template repeated with every customer.** The shot: the owner in their shop, saying in 20 seconds: (1) who they are and what they do (2) what the problem was (3) what changed — **with a specific number**. Lower third: name · business · city.
> **20 seconds in a real customer's voice sells more than ten polished ads.** Make collecting testimonials a standing weekly task.

### ★★ M-08 — "Why I built BotYalla"
9:16 or 16:9 · 60–90s · **just you to camera, minimal editing.** Why you started, what you saw happening to shop owners, who you built it for. **Do not sell in it at all.** This video builds the relationship that sells later.

### ★ M-09 — Dashboard tour · ★ M-10 — "Bot Brain" (AI) demo · ★ M-11 — "How you get paid" (Vodafone Cash/InstaPay) · ★ M-12 — Live-stream clips (5 per stream)

---

## 27.3 Images and carousels

| File | Size | Description |
|---|---|---|
| **C-01 "3 steps"** ★★★ | 1080×1350 · 3 slides | 1: `Open your account free` · 2: `Press Create my bot` · 3: `Share it and take orders`. One large icon + one line per slide. **No filler** |
| **C-02 Plan comparison** ★★★ | 1080×1350 · 4 slides | One slide per plan: name · price · three features only · who it's for. Final slide: "Start free" |
| **C-03 "5 questions your customers ask"** ★★ | 1080×1350 · 6 slides | Pure value, no selling — **the most saved and shared format** |
| **S-01 Conversation screenshot** ★★★ | 1080×1920 | A real bot/customer conversation framed inside a phone mockup with a glow. **The most-reused asset you'll own** |
| **S-02 Dashboard screenshot** ★★ | 1080×1350 | The dashboard with real (or realistic) numbers — orders and revenue |
| **P-01 A4 QR poster** ★★★ | printable A4 | **Already in the product** — photograph it hanging in a real shop and use that photo everywhere |
| **T-01 Story templates** ★★ | 1080×1920 ×5 | Blank branded templates: `counter` · `customer quote` · `new feature` · `question` · `countdown` |

---

## 27.4 Ad assets

| File | Size | Note |
|---|---|---|
| `AD-video-9x16` ★★★ | 1080×1920 | M-02 and M-03 — 4 variants with different hooks |
| `AD-video-1x1` ★★ | 1080×1080 | Same content, square — performs better in the Facebook feed |
| `AD-static-1x1` ★★★ | 1080×1080 | 4 variants: pain · comparison · ease · local |
| `AD-carousel` ★★ | 1080×1080 ×4 | "3 steps + start" |

> **The creative testing rule:** produce **4 variants of every ad with identical body copy and a different hook**. The hook (first 3 seconds) determines 80% of the outcome. Don't test the body — test the hook.

---

## 27.5 Production day checklist (one day is enough)

**Kit:** your phone · a tripod (~150 EGP) · a lavalier mic (~200 EGP) · natural window light.

```
09:00–10:00  Setup: demo account ready · restaurant bot configured · clean screen
10:00–12:00  All screen recordings (M-01, M-05, M-06, M-09, M-10)
12:00–14:00  Camera footage: you to camera (M-08) + every hook (12 hooks)
14:00–15:00  Phone and notification shots (M-02, M-03)
15:00–17:00  Filming in a real shop (M-04 + P-01 + environment stills)
17:00–19:00  Edit the first 3 videos in CapCut
```

**Filming rules:** always vertical for social · light on your face, not behind it · a lavalier mic is mandatory (bad audio kills a video faster than bad video) · shoot every take three times · **shoot far more than you think you need**.

---
---

# Part VIII — Budget & Measurement

## 28. Three budgets

### A) Zero budget — fully organic

| Item | Cost |
|---|---|
| All platforms · Canva · CapCut · GTM · GA4 · Clarity · UptimeRobot | 0 |
| **Required:** 3–4 hours a day from you | your time |
| **Expected result (30 days):** 150–400 signups · 5–20 subscribers | — |

> This is a completely viable path. TikTok, Facebook groups, and direct WhatsApp can build your first 100 customers without a single pound. **Start here even if you have a budget** — to learn what works before you pay to amplify it.

### B) 5,000 EGP — recommended for launch

| Item | Amount | Note |
|---|---|---|
| Meta ads | 2,000 | 200 EGP/day × 10 days |
| TikTok ads (Spark) | 1,200 | 150 EGP/day × 8 days — on an organically successful post |
| Brevo upgrade | 400 | Avoids an email collapse on launch day |
| Mic + tripod + light | 600 | One-off investment |
| Design (Canva Pro + designer) | 500 | Or free with the Canva trial |
| Reserve | 300 | — |
| **Expected result:** 400–900 signups · 25–50 subscribers | | |

### C) 20,000 EGP — aggressive launch

| Item | Amount |
|---|---|
| Meta ads | 9,000 |
| TikTok ads | 5,000 |
| Micro-influencers (5 × 800 EGP) | 4,000 |
| Professional content production | 1,500 |
| Tools and upgrades | 500 |
| **Expected result:** 1,200–2,500 signups · 80–150 subscribers | |

> **On influencers:** in Egypt, **five micro-influencers (10–50k followers) in the small-business niche vastly outperform one large influencer** — their audience is more precise, their trust is higher, and they cost a tenth as much. Look for accounts posting about e-commerce and shop management.

---

## 29. Measurement and KPIs

### Dashboard — review every morning

| Metric | Target (30 days) | Source |
|---|---|---|
| Site visitors | 8,000–20,000 | GA4 |
| Signup rate | **≥ 6%** | GA4 |
| **`bot_created / sign_up`** ★ | **≥ 55%** | GA4 — **your North Star** |
| Free → paid | ≥ 5% | Admin panel |
| Cost per signup | ≤ 50 EGP | Ads Manager |
| Cost per paying customer | ≤ 900 EGP | Calculated |
| TikTok followers | 1,000+ | Analytics |
| Telegram subscribers | 300+ | Channel |
| Email deliverability | ≥ 95% | Brevo |

### The rhythm

**Daily (10 min):** signups · bots created · ad spend · error and 429 logs · Brevo counter · reply to every comment and message.

**Weekly (60 min):** best/worst 3 pieces of content · per-ad performance (kill anything below average) · watch 5 Clarity recordings · read all user feedback · **write down one lesson and act on it**.

**Monthly (3 hours):** full review · retention · CAC/LTV · the winning channel · **publish the report publicly** (it builds trust and doubles as content).

### Common measurement mistakes — avoid these

| Mistake | Correction |
|---|---|
| Chasing followers | Track signups and bots created. 500 followers ≠ 10 customers |
| Judging an ad after one day | Give it 3 days and 50 clicks before deciding |
| Changing everything at once | Change one variable so you know why |
| Watching signups alone | **`bot_created` is the real number** |
| Ignoring qualitative feedback | 10 user conversations are worth 1,000 rows of data |

---
---

# Part IX — Sustainable Growth

## 30. Partners, affiliates and agencies

**The affiliate programme is already built into your platform — launch it at T+4.**

### Suggested structure
```
Commission: 25% recurring for 12 months on every subscriber
            (25% of 299 = 75 EGP × 12 = 900 EGP from one customer)
Minimum payout: 500 EGP  ·  Paid via Vodafone Cash or InstaPay
```

### Who to target
1. **Small social media agencies** — they already have clients and can add a service at 100% margin
2. **Freelancers (design, marketing, web)** — they recommend to their clients
3. **Business content creators** — commission plus content
4. **Your happy users** — surface the affiliate programme in the dashboard after 30 days of use

### The agency pitch (ready LinkedIn message)
> "Hi [name], I see you manage social media for clients.
> I built a platform that lets you create Telegram and WhatsApp bots for your clients with no developer, under your own brand (white-label).
> You can bill the client 1,500–3,000 EGP a month, at a fraction of that in cost.
> Want me to set you up with a trial account to see it yourself?"

---

## 31. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Ad account suspension (Meta)** | Medium | High | Warm accounts 3 days · verify the domain · start with a small budget · **do not create a replacement account — file an appeal** |
| **Brevo 300/day limit** | **High** | High | Upgrade before launch · watch the counter daily |
| **429 choking registration (CGNAT)** | **High** | High | Raise the limit to 20 before launch · monitor logs |
| **`bot_created/sign_up` < 40%** | Medium | **Critical** | Pause spend immediately · Clarity · fix onboarding |
| **Server outage at peak** | Low | High | UptimeRobot · tested backup · a resource-upgrade plan |
| **Meta rejects a customer's WhatsApp verification** | Medium | Medium | Be upfront about requirements · route them to Telegram meanwhile |
| **A competitor copies the product** | Medium | Medium | Your moat is relationship, support and community — not the feature |
| **Law 151/2020 compliance** | Medium | **High (legal)** | Start licensing now — the grace period ends 1 November 2026 and review can take 90 working days |
| **Losing `FERNET_KEY`** | Low | **Catastrophic** | Back it up in two safe places today — losing it means re-linking every bot |
| **Burnout** | **High** | High | Batch filming weekly, not daily · schedule content · take one day off |

---

## Summary — the next ten steps, in order

```
1.  🔴 Install measurement (GTM + GA4 + Meta Pixel + TikTok Pixel + Clarity)
2.  🔴 Widen CSP to allow it — and confirm in the console that it fires
3.  🔴 Create the six accounts with one identity and reserve @botyalla everywhere
4.  🟠 SPF + Search Console + ADMIN_PASS + UptimeRobot
5.  🟠 Raise the registration limit to 20/10min · upgrade Brevo
6.  📹 One production day: M-01 · M-02 · M-03 · M-04 · M-08
7.  📅 Three warm-up days: post with no links and no ads
8.  🚀 Launch: the 72-hour "Founding 100" offer + a launch-day live stream
9.  📊 Watch `bot_created / sign_up` daily — below 50%, pause spend and fix
10. 🔁 Repeat: post daily · collect a testimonial weekly · optimise weekly
```

> **The final truth:** your product is technically more ready than 95% of what launches in the Egyptian market. The risk is not in the code — **it is in launching blind, and in stopping publishing after week one.**
>
> Discipline beats brilliance. Post daily, answer every message, and measure everything.
>
> **Good luck, Youssef 🚀**

---

*Prepared 15 September 2026 · BotYalla · botyalla.com*
