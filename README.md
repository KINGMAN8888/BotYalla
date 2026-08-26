# BotYalla

### The No-Code Telegram Bot SaaS Platform for Businesses

BotYalla is a full-featured, multi-tenant SaaS platform that allows businesses and individuals to create, configure, and operate automated Telegram bots without writing any code. It includes an AI-assisted bot generator, industry-tailored bot templates, real-time analytics, mass broadcast tools, and a dual-layer local payment verification system.

---

## Key Features

- **No-Code Conversational Flow Builder**: Build structured interactive menus, dynamic multi-step question flows, custom buttons, and automated triggers.
- **AI-Powered Bot Configuration**: Automatically generate complete bot workflows, greetings, product catalogs, and responses from a simple text description using Google Gemini (Gemini 2.5 Flash) or Groq (Llama 3.3 70B). Includes an offline algorithmic fallback generator that guarantees continuous operation without external API dependencies.
- **Pre-Built Business Templates**:
  - **Mini E-Commerce Store**: Product catalogs, product image support, shopping cart, and order submission.
  - **Bookings and Appointments**: Automated scheduling, time-slot selection, and conflict prevention.
  - **Customer Service and Lead Generation**: Contact detail collection, FAQ responses, and inquiry routing.
  - **Custom Conversational Tree**: Free-form interactive menu builder.
- **Real-Time Analytics and CRM**: Track active bots, conversation volume, customer leads, placed orders, booking logs, and export user data to CSV.
- **Subscriber Broadcast Engine**: Send targeted broadcast messages and promotional announcements to bot subscribers.
- **Native Bilingual Support (i18n)**: Complete Arabic (RTL) and English (LTR) localization with an instant language switcher across the dashboard and templates.
- **SaaS Monetization and Local Payments**: Pre-configured subscription tiers (Free, Pro, Business) supporting regional payment channels (Vodafone Cash, InstaPay, direct bank transfer).
- **Dual-Layer Payment Verification**:
  - Layer 1 (Automated): Image validation, SHA-256 receipt deduplication fingerprinting, and optional OCR amount inspection.
  - Layer 2 (Administrative): Platform Telegram bot instant notifications with inline approve/reject buttons and web dashboard controls.
- **Administrative Suite**: Unified web portal for user role management (Admin, Support, User), account suspension, manual tier assignments, and real-time operational notifications sent directly to the owner via Telegram.

---

## Technical Architecture

BotYalla is engineered for reliability, minimal dependencies, and straightforward maintenance.

- **Backend Framework**: Python 3.11+ and Flask 3.0.
- **Bot Engine**: `python-telegram-bot` (v21.6) executing in a dedicated background `asyncio` event loop thread.
- **Database Layer**: SQLite with a clean abstracted data access interface (`database.py`) allowing seamless migration to PostgreSQL.
- **Production Server**: Gunicorn (`workers=1`, `threads=4`) behind an Nginx reverse proxy.
- **Security Controls**: CSRF protection, secure cookie flags (`COOKIE_SECURE`), PBKDF2 password hashing via Werkzeug, brute-force login throttling, and role-based access control (RBAC).

---

## Quick Start (Local Development)

### 1. Prerequisites

- Python 3.11 or higher
- Git

### 2. Clone and Setup Environment

Clone the repository and initialize a virtual environment:

```bash
git clone https://github.com/USERNAME/BotYalla.git
cd BotYalla

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# On Windows (Command Prompt):
.\venv\Scripts\activate.bat

# On Linux / macOS:
source venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Copy the sample environment file and adjust your settings:

```bash
# On Linux / macOS:
cp .env.example .env

# On Windows:
copy .env.example .env
```

Generate a secure Flask secret key and update `.env`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 5. Launch the Application

```bash
python app.py
```

Access the web dashboard at `http://127.0.0.1:5000`.

> **Note**: The default administrative account is initialized on the first run (`Username: admin`, `Password: admin1234` or configured via `ADMIN_USER` and `ADMIN_PASS` in `.env`). It is strongly recommended to change these credentials immediately via the Account Settings page.

---

## Environment Configuration

The application is configured using environment variables in `.env`:

| Variable | Description | Default | Required |
|---|---|---|---|
| `FLASK_SECRET` | Secret key used for signing session cookies | Generated key | Yes |
| `COOKIE_SECURE` | Set to `1` when serving over HTTPS; `0` for local HTTP | `0` | Yes |
| `ADMIN_USER` | Initial administrative username created on first launch | `admin` | No |
| `ADMIN_PASS` | Initial administrative password created on first launch | `change_this_strong_password_here` | No |
| `HOST` | Local development host binding | `127.0.0.1` | No |
| `PORT` | Local development port | `5000` | No |
| `GEMINI_API_KEY` | Google Gemini API key for AI bot setup (`gemini-2.5-flash`) | Optional | No |
| `GROQ_API_KEY` | Groq API key for AI bot setup (`llama-3.3-70b-versatile`) | Optional | No |

---

## Subscription Plans

Plan structures and feature limits are defined in `plans.py`:

| Plan | Price (EGP/mo) | Active Bot Limit | Core Features |
|---|---|---|---|
| **Free** | 0 | 1 Bot | 1 active bot, smart offline fallback generator, basic analytics |
| **Pro** | 199 | 5 Bots | Up to 5 bots, AI configuration agent, broadcast campaigns, full analytics, media upload |
| **Business** | 499 | Unlimited | Unlimited bots, all Pro features, priority support, full CSV data exports |

---

## Production Deployment

### Option A: Automated Linux VPS Deployment (Ubuntu / Debian)

A deployment script is provided in `deploy/deploy.sh`. It automates package installation, user isolation, virtual environment creation, systemd service creation, and Nginx reverse proxy configuration.

```bash
sudo bash deploy/deploy.sh https://github.com/USERNAME/BotYalla.git yourdomain.com
```

To configure free SSL certificates with Let's Encrypt:

```bash
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

### Option B: Docker Container

Build and run using the included Docker configuration:

```bash
# Build the Docker image
docker build -t botyalla .

# Run container on port 8000
docker run -d -p 8000:8000 --env-file .env --name botyalla_app botyalla
```

### Option C: Shared Hosting / Windows Server

For Windows or specific hosting platforms, refer to the step-by-step guides in the `docs/` directory.

---

## Documentation

Detailed guides are available in the `docs/` directory:

- [User Guide](docs/USER_GUIDE.md): Complete guide for platform owners and subscribed business clients.
- [Deployment Guide](docs/DEPLOYMENT.md): Production server setup, Nginx reverse proxy, and SSL configuration.
- [Architecture](docs/ARCHITECTURE.md): System design, threading model, and database schemas.
- [Security Model](docs/SECURITY.md): Security practices, session protections, and access controls.
- [Hostinger Guide](docs/HOSTINGER.md): Specific instructions for deploying on Hostinger infrastructure.

---

## Platform Bot Commands (Admin Controls)

When the platform notification bot is linked in the Admin Settings, administrators can manage the system directly within Telegram:

- `/stats`: Platform metrics (total users, active subscriptions, revenue).
- `/pending`: List pending payment receipts with inline approve and reject buttons.
- `/users`: Display recently registered accounts.
- `/revenue`: Financial breakdown by subscription tier.

---

## License & Ownership

Developed and maintained by **Youssef Alsherief**.

- Website: [youssefalsherief.tech](https://youssefalsherief.tech/)
- Email: info@youssefalsherief.tech
- Phone: +20 109 758 5951
