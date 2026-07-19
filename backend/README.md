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

Periodic syncing is disabled by default. Set `MAIL_SYNC_ENABLED=true` only after
the database and OAuth configuration are ready. Until then, use the manual sync
endpoint. Priority filtering always has a local rule-based fallback; the deployed
model is optional and uses an OpenAI-compatible chat-completions endpoint.

Database migration files are intentionally not included yet.
