# Security Policy — BotYalla

This document outlines the security architecture, implemented controls, vulnerability reporting process, and recommended deployment hardening guidelines for the BotYalla platform.

---

## Supported Versions

| Version | Supported | Notes |
|---|---|---|
| 1.0.x | Yes | Current active release branch with security maintenance. |
| < 1.0.0 | No | Deprecated development builds. |

---

## Security Architecture and Controls

### 1. Authentication and Session Management

- **Password Hashing**: Passwords are cryptographically hashed using PBKDF2 with SHA-256 via Werkzeug security primitives. Plaintext passwords are never stored, transmitted, or logged.
- **Session Cookie Protection**: Configured with `HttpOnly`, `SameSite=Lax`, and the `Secure` flag (`COOKIE_SECURE=1` when operating over HTTPS).
- **Brute-Force Rate Limiting**: IP-level rate limiting on authentication routes prevents credential stuffing and dictionary guessing attacks.
- **Secret Management**: Application session signing relies on high-entropy `FLASK_SECRET` tokens generated via cryptographic random generators.

---

### 2. Threat Mitigation Matrix

| Threat Vector | Mitigation Strategy | Implementation Details |
|---|---|---|
| **SQL Injection** | Parameterized Queries | All SQLite interactions utilize parameterized query interfaces (`?` placeholders) with strict separation of SQL commands and user inputs. Direct string formatting or interpolation is strictly prohibited. |
| **Cross-Site Request Forgery (CSRF)** | Synchronizer Token Pattern | Cryptographic CSRF tokens are embedded in all web forms and validated on every state-changing HTTP request (`POST`, `PUT`, `DELETE`). Requests lacking valid tokens return HTTP 400 Bad Request. |
| **Cross-Site Scripting (XSS)** | Context-Aware Auto-Escaping | Jinja2 template autoescaping is enabled across all rendering contexts, neutralizing malicious HTML/JavaScript injection from user-submitted bot names, messages, or configurations. |
| **Open Redirection** | Route & Whitelist Validation | Language switchers and redirection handlers validate internal relative paths, rejecting external or unvalidated target destinations. |
| **Malicious File Uploads** | Multi-Factor File Verification | File uploads are constrained by file extension whitelisting, magic byte signature validation, an 8MB maximum payload cap, and sanitized file naming via `secure_filename()`. |
| **Insecure Direct Object References (IDOR)** | Strict Ownership Verification | Strict object-level access controls guarantee that bots and conversational trees are only accessible by their authenticated creator (HTTP 404 for unowned entities). Administrative endpoints enforce role authorization (HTTP 403). |

---

### 3. Payment Processing and Verification Security

BotYalla implements a dual-layer verification architecture tailored for regional and offline payment channels (such as Vodafone Cash, InstaPay, and direct bank transfer):

- **Zero Automatic Activation**: Subscriptions are never activated automatically upon receipt upload; explicit authorization from an authenticated platform administrator is mandatory.
- **Strict Administrative Authorization**: Approval webhooks and callback queries strictly verify that the interacting account matches the designated platform administrator Telegram ID (`admin_chat_id`).
- **Atomic Transaction Lifecycle**: Subscription activations execute within atomic database transactions, preventing double-activation or race conditions on the same payment record.
- **Server-Authoritative Pricing**: Pricing and subscription duration (30 days) are enforced strictly server-side from predefined system configuration (`plans.py`), eliminating client-side parameter tampering.
- **Receipt Deduplication Fingerprinting**: Every uploaded payment proof is hashed using SHA-256. Identical receipt hashes are flagged and blocked from duplicate submission.
- **Media Isolation**: Payment receipt images are stored in a protected storage directory with restricted web access, transmitted exclusively to authorized administrators via secure Telegram API calls.

---

### 4. Role-Based Access Control (RBAC)

The system implements three discrete user roles:

| Role | Permissions | Constraints |
|---|---|---|
| **admin** (Platform Owner) | Full system administrative access: user management, role assignments, platform payment destination settings, subscription overrides, and payment approval. | The primary administrator account (User ID 1) is permanently locked to the `admin` role and cannot be demoted or deleted. |
| **support** (Support Staff) | Read-only administrative access: viewing system metrics, user directories, and payment audit logs. | Cannot alter user roles, modify global platform settings, or execute payment approvals. |
| **user** (Subscriber / Client) | Management of personal bots, conversation flows, business templates, and individual subscription plans. | Restricted exclusively to self-owned resources. Blocked users (`is_blocked=1`) are denied login access immediately. |

---

## Production Hardening Recommendations

For production deployments, platform administrators must adhere to the following best practices:

1. **Enforce HTTPS**: Always operate behind a reverse proxy (e.g., Nginx) with valid TLS/SSL certificates (e.g., Let's Encrypt Certbot) and configure `COOKIE_SECURE=1` in `.env`.
2. **Protect Secrets and Environment Files**: Never commit `.env` or the SQLite database file (`botyalla.db`) to public version control. These files contain API keys and Telegram bot tokens.
3. **Automated Database Backups**: Schedule regular encrypted backups of `botyalla.db` and the `/uploads` directory to an offsite storage location.
4. **Principle of Least Privilege**: Run the Gunicorn and Python processes under a dedicated non-root system user (e.g., `botyalla`).
5. **Network Firewall Configuration**: Restrict incoming traffic on your server to ports 80 (HTTP) and 443 (HTTPS), binding Gunicorn strictly to `127.0.0.1:8000`.

---

## Reporting a Security Vulnerability

We take the security of BotYalla and its users seriously. If you discover a potential security vulnerability, please follow responsible disclosure guidelines:

1. **Do not create a public GitHub issue** or disclose the vulnerability publicly before it has been addressed.
2. Send a detailed report directly to the security maintainer:
   - **Email**: info@youssefalsherief.tech
   - **Subject Line**: `[SECURITY] BotYalla Vulnerability Report`
3. Please include:
   - A description of the vulnerability and its potential impact.
   - Step-by-step instructions or proof-of-concept (PoC) to reproduce the issue.
   - Affected versions and configurations.
4. You will receive an acknowledgement within 48 hours, followed by updates on triage, remediation, and public disclosure timelines.
