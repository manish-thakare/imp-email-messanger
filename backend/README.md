# AI Email Guardian backend

This API creates user accounts, connects one or more Gmail or Outlook inboxes,
and presents fetched messages in one priority-sorted feed.

## Implemented API flow

1. `POST /api/v1/auth/register` creates the application user.
2. `POST /api/v1/auth/login` returns a bearer token.
3. `GET /api/v1/users/me` returns the signed-in user.
4. `GET /api/v1/email-accounts/oauth/{gmail|outlook}/start` returns a provider consent URL.
5. The provider callback stores encrypted connection credentials.
6. `GET /api/v1/email-accounts/` lists connected inboxes.
7. `POST /api/v1/email-accounts/{account_id}/sync` fetches and classifies an inbox.
8. `GET /api/v1/messages/priority` returns the combined important-email feed.

Copy `.env.example` to `.env`, then supply Gmail and/or Outlook OAuth credentials.
The registered provider callback URLs must exactly match the URLs in the example.
Tokens are encrypted with `MAIL_TOKEN_ENCRYPTION_KEY` before database storage.

## Credential safety

`.env`, downloaded OAuth client-secret JSON files, access tokens, and webhook secrets
must never be committed. If a credential was committed previously, revoke and rotate it
in the provider console before using this project. Removing a file from Git prevents a
new leak; it does not invalidate a credential or erase repository history.

Periodic syncing is disabled by default. Set `MAIL_SYNC_ENABLED=true` only after
the database and OAuth configuration are ready. Until then, use the manual sync
endpoint. Priority filtering always has a local rule-based fallback; the deployed
model is optional and uses an OpenAI-compatible chat-completions endpoint.

Database migrations are managed with Alembic; see the next section before running the API against a new database.

## Database migrations

Alembic now owns the database schema. Once the PostgreSQL credentials in `.env`
are correct, apply the initial schema from the repository root:

```powershell
& <python> -m alembic -c alembic.ini upgrade head
```

This creates the user, connected-inbox, fetched-message, WhatsApp contact, and
WhatsApp notification-outbox tables. The third revision also adds a classification
fingerprint, allowing unchanged emails to avoid repeated rule or LLM evaluation.
No migration is run automatically.

Before applying a non-empty database, take a backup and inspect the current revision:

```powershell
& <python> -m alembic -c alembic.ini current
& <python> -m alembic -c alembic.ini upgrade head
& <python> -m alembic -c alembic.ini check
```

The initial Gmail import is intentionally bounded by `MAIL_SYNC_BATCH_SIZE`; later
syncs use the Gmail History API. Outlook uses Microsoft Graph delta links from the
first sync onward. Do not edit an applied revision—create a new Alembic revision for
future schema changes.

## LLM priority classification

The built-in rule classifier is always available. To enable the optional
OpenAI-compatible classifier, configure `LLM_PRIORITY_ENABLED`,
`LLM_PRIORITY_API_URL`, and `LLM_PRIORITY_MODEL` in the local `.env` file. The
classifier asks for a tightly validated JSON response and falls back to rules on any
provider or validation failure.

By default, email body previews are **not** sent to the LLM. Set
`LLM_PRIORITY_SEND_BODY_PREVIEW=true` only after a privacy and data-processing review;
`LLM_PRIORITY_MAX_BODY_CHARACTERS` bounds the amount shared. Changing the configured
model or `LLM_PRIORITY_CLASSIFICATION_VERSION` intentionally causes stored emails to
be classified again.

## Background sync

`MAIL_SYNC_ENABLED=true` starts the optional polling worker. It obtains a PostgreSQL
advisory lock so only one application replica syncs inboxes at a time; set the same
`MAIL_SYNC_WORKER_LOCK_ID` across replicas. For large production deployments, run this
worker separately from the API service and keep provider rate limits in mind.

## WhatsApp priority chat

WhatsApp delivery is disabled until the Meta Cloud API configuration is added to
the untracked `.env` file:

```text
WHATSAPP_ENABLED=true
WHATSAPP_GRAPH_API_VERSION=<approved Meta Graph API version>
WHATSAPP_PHONE_NUMBER_ID=<Meta phone number ID>
WHATSAPP_ACCESS_TOKEN=<system-user access token>
WHATSAPP_VERIFY_TOKEN=<random webhook challenge secret>
WHATSAPP_APP_SECRET=<Meta app secret>
WHATSAPP_PRIORITY_TEMPLATE_NAME=priority_email_alert
WHATSAPP_TEMPLATE_LANGUAGE=en_US
```

Create and approve a `priority_email_alert` template with three body variables:
sender, email subject, and priority reason. Configure Meta's public HTTPS
webhook URL as `/api/v1/whatsapp/webhook`. Users opt in through
`PUT /api/v1/whatsapp/contact`; inbound `LATEST`, `STOP`, and `START` messages
then return a summary or manage alerts. Never put working secrets in
`.env.example` or commit client-secret JSON files.
