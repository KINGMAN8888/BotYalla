<div align="left">
  <img src="static/logo.svg" alt="BotYalla Logo" height="70">
</div>

# BotYalla

### The No-Code Telegram Bot SaaS Platform for Businesses

BotYalla is a full-featured, multi-tenant SaaS platform that enables businesses, agencies, and creators to design, launch, and manage intelligent Telegram bots without writing a single line of code. Built with Python, Flask, and the modern `python-telegram-bot` framework, BotYalla combines a visual conversation flow engine, generative AI automation, built-in business templates, subscriber broadcasting, real-time analytics, and a dual-layer local payment verification pipeline.

---

## Table of Contents

- [System Architecture](#system-architecture)
  - [High-Level Architecture](#high-level-architecture)
  - [Execution and Threading Model](#execution-and-threading-model)
  - [Dual-Layer Payment Flow](#dual-layer-payment-flow)
  - [Core Modules and Responsibilities](#core-modules-and-responsibilities)
  - [Database Schema](#database-schema)
- [Key Features](#key-features)
- [Pre-Built Bot Templates](#pre-built-bot-templates)
- [Subscription Plans and Pricing](#subscription-plans-and-pricing)
- [Environment Configuration](#environment-configuration)
- [Platform Bot Admin Commands](#platform-bot-admin-commands)
- [Quick Start Guide](#quick-start-guide)
- [Production Deployment](#production-deployment)
  - [Automated Linux VPS Script](#automated-linux-vps-script)
  - [Docker Containerization](#docker-containerization)
- [Documentation Index](#documentation-index)
- [License](#license)
- [Author and Contact](#author-and-contact)

---

## System Architecture

### High-Level Architecture

```mermaid
flowchart TD
    subgraph ClientLayer ["Client Access Layer"]
        WebUser["End User / Admin Browser"]
        TgUser["Telegram Subscribers"]
    end

    subgraph InfrastructureLayer ["Infrastructure & Reverse Proxy"]
        Nginx["Nginx Web Server (Port 80 / 443 + SSL)"]
        Gunicorn["Gunicorn WSGI Server (1 Worker, 4 Threads)"]
    end

    subgraph ApplicationLayer ["Application Layer (Flask Web Service)"]
        FlaskApp["Flask Web Core (app.py)"]
        AuthModule["Authentication & RBAC (auth.py)"]
        FlowModule["Conversation Flow Engine (flow_engine.py)"]
        AIModule["AI Configuration Engine (ai_agent.py)"]
        PaymentModule["Payment Verification Engine (payments.py)"]
        I18nModule["Internationalization (i18n.py)"]
    end

    subgraph DataLayer ["Data & Storage Layer"]
        DB[("SQLite Database (database.py)")]
        UploadsDir["Local File System (/uploads)"]
    end

    subgraph BotRuntimeLayer ["Bot Execution Runtime (Dedicated Asyncio Thread)"]
        BotManager["Bot Manager (bot_manager.py)"]
        PlatformBot["Platform Admin Bot (platform_bot.py)"]
        TenantBots["Tenant Business Bots (templates_bot.py)"]
    end

    subgraph ExternalServices ["External Services & APIs"]
        TelegramAPI["Telegram Bot API"]
        GeminiAPI["Google Gemini API (gemini-2.5-flash)"]
        GroqAPI["Groq API (llama-3.3-70b-versatile)"]
    end

    WebUser -->|HTTPS| Nginx
    Nginx -->|Proxy Pass 127.0.0.1:8000| Gunicorn
    Gunicorn --> FlaskApp

    FlaskApp --> AuthModule
    FlaskApp --> FlowModule
    FlaskApp --> AIModule
    FlaskApp --> PaymentModule
    FlaskApp --> I18nModule
    FlaskApp --> DB

    PaymentModule --> UploadsDir
    PaymentModule -.-> PlatformBot

    AIModule -->|REST API| GeminiAPI
    AIModule -->|REST API| GroqAPI

    BotManager --> DB
    BotManager --> PlatformBot
    BotManager --> TenantBots

    TenantBots <-->|Long Polling / Webhook| TelegramAPI
    PlatformBot <-->|Admin Notifications & Callbacks| TelegramAPI
    TgUser <--> TelegramAPI
```

---

### Execution and Threading Model

BotYalla separates web request servicing from continuous Telegram bot polling to maintain high responsiveness and state consistency:

- **Web Service**: Powered by Flask and WSGI (Gunicorn), handling administrative requests, user authentication, bot builder interfaces, payment processing, and analytics dashboards.
- **Bot Engine (`BotManager`)**: Runs an isolated background `asyncio` event loop thread started on application initialization.
- **Multi-Tenant Polling**: Each active bot runs as an independent `telegram.ext.Application` instance registered within the shared runtime manager.
- **Platform Management Bot**: Operates concurrently on the same event loop to listen for platform-level administrative callbacks and dispatch real-time alerts.

---

### Dual-Layer Payment Flow

To prevent unauthorized subscription activation while supporting regional payment channels without direct webhooks (e.g., Vodafone Cash, InstaPay, direct bank transfer), BotYalla employs a two-tier verification mechanism:

```mermaid
sequenceDiagram
    autonumber
    actor Subscriber as Subscriber
    participant Web as Web Dashboard
    participant Storage as File Storage & DB
    participant Bot as Platform Telegram Bot
    actor Admin as Platform Admin

    Subscriber->>Web: Selects Plan & Uploads Payment Receipt
    Note over Web: Layer 1: Automated Sanity Checks
    Web->>Web: Validate File Type & Image Dimensions
    Web->>Web: Compute SHA-256 Hash to Detect Duplicate Receipts
    Web->>Web: Run OCR Inspection (Optional Target Amount Match)
    Web->>Storage: Store Receipt & Mark Status as Pending
    Web->>Bot: Forward Receipt & Metadata to Admin Chat
    Bot->>Admin: Send Telegram Notification with Inline Approve / Reject Actions
    
    alt Admin Approves
        Admin->>Bot: Click Approve Button
        Note over Bot: Layer 2: Administrative Authorization
        Bot->>Storage: Atomically Activate 30-Day Subscription
        Bot->>Admin: Send Confirmation Notification
        Storage-->>Subscriber: Dashboard Access Granted
    else Admin Rejects
        Admin->>Bot: Click Reject Button
        Bot->>Storage: Update Status to Rejected
        Bot->>Admin: Send Rejection Notification
    end
```

---

### Core Modules and Responsibilities

| Module | Primary Responsibility | Key Functions / Classes |
|---|---|---|
| `app.py` | Central Flask application, routing, session lifecycle, CSRF enforcement, and plan authorization. | Main application entry point, route definitions, error handlers. |
| `bot_manager.py` | Orchestration of tenant bots and the platform bot in a background `asyncio` event loop. | `BotManager`, `start_all()`, `start_bot()`, `stop_bot()`. |
| `flow_engine.py` | No-code dynamic conversational engine supporting branching, state transitions, and input capture. | `FlowEngine`, `handle_message()`, `handle_callback()`. |
| `templates_bot.py` | Domain-specific handlers for pre-built business models (Stores, Bookings, Support). | Template dispatchers, catalog renderers, booking slot calculators. |
| `ai_agent.py` | AI automation engine translating business prompts into complete bot configurations. | `call_gemini()`, `call_groq()`, offline fallback generator. |
| `payments.py` | Payment receipt validation, SHA-256 duplicate fingerprinting, and OCR analysis. | `verify_receipt()`, `compute_image_hash()`, `extract_ocr_data()`. |
| `platform_bot.py` | Administrative Telegram bot handling real-time notifications and approval callbacks. | `PlatformBot`, notification dispatchers, command handlers. |
| `database.py` | Database abstraction layer for SQLite with transactional safety. | Schema definitions, user management, bot CRUD, subscription state. |
| `auth.py` | Password encryption, hashing, and credential validation using Werkzeug security utilities. | `hash_password()`, `check_password()`. |
| `plans.py` | Subscription tier specifications, pricing constants, and feature boundary enforcement. | `PLANS`, `plan()`, `plan_name()`. |
| `i18n.py` | Localization repository supporting Arabic (RTL) and English (LTR). | Translation dictionaries, direction helper functions. |
| `tg_helpers.py` | Telegram token validation, admin linking, and shared message formatting. | `validate_token()`, `get_bot_info()`. |

---

### Database Schema

| Table Name | Description | Key Attributes |
|---|---|---|
| `users` | User accounts and dashboard credentials | `id`, `username`, `password`, `role` (admin, support, user), `created_at`, `is_blocked` |
| `bots` | Individual Telegram bot configurations | `id`, `user_id`, `token`, `template`, `config_json`, `is_active`, `created_at` |
| `subscriptions` | Active user billing plans and validity periods | `id`, `user_id`, `plan`, `expires_at`, `status`, `created_at` |
| `payments` | Audit logs of uploaded receipts and verification state | `id`, `user_id`, `method`, `amount`, `receipt_file`, `image_hash`, `status`, `reviewed_at` |
| `platform` | Global platform settings and payment destination details | `key`, `value` (Vodafone Cash, InstaPay, Admin Bot Token, Admin Chat ID) |
| `events` | Real-time analytics event stream | `id`, `bot_id`, `event_type` (start, lead, order, booking), `metadata_json`, `created_at` |
| `bot_users` | Subscribers and lead directory for each managed bot | `id`, `bot_id`, `telegram_id`, `username`, `first_name`, `created_at` |

---

## Key Features

- **No-Code Conversational Flow Builder**: Visual step-by-step tree constructor enabling interactive menus, button callbacks, variable collection, and automated replies without writing code.
- **AI-Powered Bot Generation**: Generate full bot settings, greetings, product catalogs, and responses from simple business descriptions using Google Gemini (`gemini-2.5-flash`) or Groq (`llama-3.3-70b-versatile`), supported by a built-in offline algorithmic fallback engine.
- **Audience Broadcasting**: Transmit mass marketing campaigns, announcements, and media updates directly to subscribers across any managed bot.
- **Real-Time Analytics Dashboard**: Monitor conversation metrics, active user engagement, lead generation rates, store orders, and appointment bookings, with full CSV export capabilities.
- **Full Internationalization (i18n)**: Seamless bidirectional support for Arabic (RTL) and English (LTR) across all dashboard screens and bot responses.
- **Multi-Role Administration**: Dedicated web administrative suite with access controls (`admin`, `support`, `user`), subscriber tracking, and manual tier overrides.
- **Robust Security Posture**: Session encryption via configurable secrets, secure HTTPS cookie enforcement, PBKDF2 password hashing, CSRF protection, and brute-force login throttling.

---

## Pre-Built Bot Templates

| Template | Target Use Case | Key Capabilities |
|---|---|---|
| **Mini E-Commerce Store** | Retail, restaurants, boutique shops, digital products | Product catalog with images, categories, shopping cart, checkout, order notifications. |
| **Bookings & Appointments** | Clinics, salons, consultants, service businesses | Automated calendar scheduling, dynamic slot calculation, double-booking prevention. |
| **Customer Support & Leads** | Agencies, corporate inquiries, service desks | Structured lead capture, contact forms, automated FAQs, instant admin notification. |
| **Custom Flow Builder** | Generalized business workflows, interactive forms | Step-by-step decision trees, custom button paths, custom input capture. |

---

## Subscription Plans and Pricing

Plan configuration and tier definitions can be modified in `plans.py`:

| Plan Tier | Price | Bot Limit | AI Generation | Broadcast Engine | Analytics & Media | Export Access |
|---|---|---|---|---|---|---|
| **Free** | 0 EGP / mo | 1 Bot | Smart Offline Generator | Disabled | Basic Metrics | Disabled |
| **Pro** | 199 EGP / mo | 5 Bots | Gemini / Groq + Fallback | Enabled | Full Metrics + Media | Basic Export |
| **Business** | 499 EGP / mo | Unlimited | Gemini / Groq + Fallback | Enabled | Full Metrics + Media | Full CSV Export |

---

## Environment Configuration

The platform loads configuration values from `.env`. An annotated template is available in `.env.example`:

| Parameter | Type | Default Value | Description |
|---|---|---|---|
| `FLASK_SECRET` | String | Generated Key | Secret key used for signing session cookies. |
| `COOKIE_SECURE` | Integer | `0` | Set to `1` in production behind HTTPS; `0` for local HTTP development. |
| `ADMIN_USER` | String | `admin` | Default administrative username created automatically on first run. |
| `ADMIN_PASS` | String | `change_this_strong_password_here` | Default administrative password created on first run. |
| `HOST` | String | `127.0.0.1` | Local network binding address for development. |
| `PORT` | Integer | `5000` | Local network port for development. |
| `GEMINI_API_KEY` | String | None | Google Gemini API key for AI generation features. |
| `GROQ_API_KEY` | String | None | Groq API key for alternative Llama 3.3 AI generation. |

---

## Platform Bot Admin Commands

When the platform notification bot is configured with your Telegram Admin ID, you can manage operations remotely via Telegram:

| Command | Access Level | Description |
|---|---|---|
| `/stats` | Admin | Real-time platform summary: total users, active subscriptions, revenue. |
| `/pending` | Admin | Displays pending payment submissions with interactive Approve and Reject buttons. |
| `/users` | Admin | Lists the most recently registered user accounts on the platform. |
| `/revenue` | Admin | Provides a financial breakdown of income generated per subscription tier. |

---

## Quick Start Guide

### 1. Prerequisites

- Python 3.11 or higher
- Git

### 2. Clone and Setup Environment

```bash
# Clone repository
git clone https://github.com/USERNAME/BotYalla.git
cd BotYalla

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# Windows (Command Prompt):
.\venv\Scripts\activate.bat

# Linux / macOS:
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

```bash
# Copy template configuration
# Linux / macOS:
cp .env.example .env

# Windows:
copy .env.example .env
```

Generate a secure Flask secret key:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Paste the generated string into `FLASK_SECRET` inside `.env`.

### 5. Start the Server

```bash
python app.py
```

Navigate to `http://127.0.0.1:5000` in your browser.

> **Security Advisory**: Change the default admin password (`Username: admin`, `Password: admin1234` or values specified in `ADMIN_USER` / `ADMIN_PASS`) immediately upon first login via the Account Settings page.

---

## Production Deployment

### Automated Linux VPS Script

An automated deployment script is available in `deploy/hostinger_deploy.sh` for Ubuntu/Debian servers. It manages package installation, user isolation, virtual environments, the frontend build, systemd daemonization, Nginx, firewall, and daily backups. It is idempotent — running it twice is safe. See `docs/PRODUCTION.md` for the full runbook.

```bash
# Run automated setup script
sudo bash deploy/hostinger_deploy.sh yourdomain.com

# Configure SSL certificate via Let's Encrypt
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

### Docker Containerization

Run BotYalla within an isolated Docker container:

```bash
# Build the Docker image
docker build -t botyalla .

# Run the container on port 8000
docker run -d -p 8000:8000 --env-file .env --name botyalla_app botyalla
```

---

## Documentation Index

| Documentation File | Location | Content Overview |
|---|---|---|
| **Security Policy** | [SECURITY.md](SECURITY.md) / [docs/SECURITY.md](docs/SECURITY.md) | Vulnerability disclosure, threat matrices, and production hardening. |
| **User Guide** | [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | Platform owner workflows, client bot creation, and dashboard usage. |
| **Deployment Guide** | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Production server setup, Nginx reverse proxy, and SSL configuration. |
| **Architecture Guide** | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Component architecture, event loops, and database design. |
| **Hostinger VPS Guide** | [docs/HOSTINGER.md](docs/HOSTINGER.md) | Specific setup instructions for Hostinger infrastructure. |

---

## License

This project is licensed under the terms of the MIT License. See the [LICENSE](LICENSE) file for complete license terms.

---

## Author and Contact

Developed and maintained by **Youssef Alsherief**.

| Channel | Details |
|---|---|
| **Website** | [youssefalsherief.tech](https://youssefalsherief.tech/) |
| **Email** | info@youssefalsherief.tech |
| **Phone** | +20 109 758 5951 |
