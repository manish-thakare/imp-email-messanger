"""OAuth connection and token-refresh support for Gmail and Outlook."""

import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    create_signed_token,
    decode_signed_token,
    decrypt_provider_token,
    encrypt_provider_token,
)
from app.models.monitored_email_account import MonitoredEmailAccount
from app.repositories.monitored_email_account_repository import MonitoredEmailAccountRepository


class MailOAuthError(ValueError):
    """A user-safe error raised when a provider connection cannot be completed."""


class MailOAuthService:
    """Build OAuth consent links, save credentials, and refresh expired access tokens."""

    def __init__(self, db: AsyncSession):
        """Use one database session for the current OAuth callback or sync operation."""
        self.db = db
        self.account_repo = MonitoredEmailAccountRepository(db)

    def build_authorization_url(self, provider: str, user_id: int) -> str:
        """Create a consent URL containing a signed, short-lived user ownership state."""
        provider_config = self._provider_config(provider)
        state = create_signed_token(
            {
                "purpose": "mail_oauth",
                "provider": provider,
                "uid": user_id,
                "nonce": secrets.token_urlsafe(16),
            },
            timedelta(minutes=10),
        )
        parameters = {
            "client_id": provider_config["client_id"],
            "redirect_uri": provider_config["redirect_uri"],
            "response_type": "code",
            "scope": provider_config["scope"],
            "state": state,
        }
        if provider == "gmail":
            parameters.update({"access_type": "offline", "prompt": "consent"})
        return f"{provider_config['authorization_url']}?{urlencode(parameters)}"

    async def complete_connection(
        self, provider: str, code: str, state: str
    ) -> MonitoredEmailAccount:
        """Exchange a provider callback code and associate its inbox with the state owner."""
        state_data = decode_signed_token(state)
        if (
            not state_data
            or state_data.get("purpose") != "mail_oauth"
            or state_data.get("provider") != provider
            or not isinstance(state_data.get("uid"), int)
        ):
            raise MailOAuthError("The email connection link is invalid or has expired")

        token_data = await self._exchange_code(provider, code)
        access_token = token_data.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise MailOAuthError("The email provider did not issue an access token")

        email_address = await self._get_provider_email(provider, access_token)
        existing = await self.account_repo.get_by_provider_email(provider, email_address)
        if existing is not None and existing.user_id != state_data["uid"]:
            raise MailOAuthError("This email account is already connected to another user")

        refresh_token = token_data.get("refresh_token")
        expires_at = _expires_at(token_data.get("expires_in"))
        if existing is None:
            account = MonitoredEmailAccount(
                user_id=state_data["uid"],
                provider=provider,
                email_address=email_address,
                status="active",
                encrypted_access_token=encrypt_provider_token(access_token),
                encrypted_refresh_token=(
                    encrypt_provider_token(refresh_token) if isinstance(refresh_token, str) else None
                ),
                token_expires_at=expires_at,
            )
            return await self.account_repo.create(account)

        existing.encrypted_access_token = encrypt_provider_token(access_token)
        if isinstance(refresh_token, str) and refresh_token:
            existing.encrypted_refresh_token = encrypt_provider_token(refresh_token)
        existing.token_expires_at = expires_at
        existing.status = "active"
        existing.error_message = None
        return await self.account_repo.save(existing)

    async def get_valid_access_token(self, account: MonitoredEmailAccount) -> str:
        """Return a usable provider token, refreshing it shortly before it expires."""
        if not account.encrypted_access_token:
            raise MailOAuthError("This email account has no stored access token")
        expires_at = account.token_expires_at
        if expires_at is None or expires_at > datetime.now(timezone.utc) + timedelta(seconds=60):
            return decrypt_provider_token(account.encrypted_access_token)

        if not account.encrypted_refresh_token:
            raise MailOAuthError("Please reconnect this email account to continue syncing")
        refreshed = await self._refresh_token(account.provider, account.encrypted_refresh_token)
        access_token = refreshed.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise MailOAuthError("The email provider did not refresh the access token")
        account.encrypted_access_token = encrypt_provider_token(access_token)
        if isinstance(refreshed.get("refresh_token"), str):
            account.encrypted_refresh_token = encrypt_provider_token(refreshed["refresh_token"])
        account.token_expires_at = _expires_at(refreshed.get("expires_in"))
        return access_token

    async def _exchange_code(self, provider: str, code: str) -> dict[str, object]:
        """Exchange a one-time OAuth code for provider credentials."""
        provider_config = self._provider_config(provider)
        data = {
            "client_id": provider_config["client_id"],
            "client_secret": provider_config["client_secret"],
            "redirect_uri": provider_config["redirect_uri"],
            "grant_type": "authorization_code",
            "code": code,
        }
        return await self._post_token_request(provider_config["token_url"], data)

    async def _refresh_token(self, provider: str, encrypted_refresh_token: str) -> dict[str, object]:
        """Use the stored refresh credential to obtain a new short-lived access token."""
        provider_config = self._provider_config(provider)
        data = {
            "client_id": provider_config["client_id"],
            "client_secret": provider_config["client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": decrypt_provider_token(encrypted_refresh_token),
        }
        if provider == "outlook":
            data["scope"] = provider_config["scope"]
        return await self._post_token_request(provider_config["token_url"], data)

    async def _post_token_request(self, url: str, data: dict[str, str]) -> dict[str, object]:
        """Call a provider token endpoint and translate failures into safe API errors."""
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.post(url, data=data)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MailOAuthError("The email provider rejected the authorization request") from exc
        token_data = response.json()
        if not isinstance(token_data, dict):
            raise MailOAuthError("The email provider returned an invalid token response")
        return token_data

    async def _get_provider_email(self, provider: str, access_token: str) -> str:
        """Ask the provider which mailbox was just authorized by the user."""
        profile_url = (
            "https://www.googleapis.com/oauth2/v3/userinfo"
            if provider == "gmail"
            else "https://graph.microsoft.com/v1.0/me?$select=mail,userPrincipalName"
        )
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(
                    profile_url,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MailOAuthError("Unable to identify the authorized email account") from exc

        profile = response.json()
        email_address = profile.get("email") if provider == "gmail" else (
            profile.get("mail") or profile.get("userPrincipalName")
        )
        if not isinstance(email_address, str) or "@" not in email_address:
            raise MailOAuthError("The email provider did not return an email address")
        return email_address.lower()

    def _provider_config(self, provider: str) -> dict[str, str]:
        """Return endpoints and configured credentials for one supported provider."""
        if provider == "gmail":
            config = {
                "client_id": settings.GMAIL_CLIENT_ID,
                "client_secret": settings.GMAIL_CLIENT_SECRET,
                "redirect_uri": settings.GMAIL_REDIRECT_URI
                or f"{settings.API_BASE_URL.rstrip('/')}/api/v1/email-accounts/oauth/gmail/callback",
                "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_url": "https://oauth2.googleapis.com/token",
                "scope": "openid email https://www.googleapis.com/auth/gmail.readonly",
            }
        elif provider == "outlook":
            config = {
                "client_id": settings.OUTLOOK_CLIENT_ID,
                "client_secret": settings.OUTLOOK_CLIENT_SECRET,
                "redirect_uri": settings.OUTLOOK_REDIRECT_URI
                or f"{settings.API_BASE_URL.rstrip('/')}/api/v1/email-accounts/oauth/outlook/callback",
                "authorization_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
                "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                "scope": "offline_access User.Read Mail.Read",
            }
        else:
            raise MailOAuthError("Email provider must be gmail or outlook")

        if not config["client_id"] or not config["client_secret"]:
            raise MailOAuthError(f"{provider.title()} OAuth is not configured")
        return {key: str(value) for key, value in config.items()}


def _expires_at(expires_in: object) -> datetime:
    """Turn provider expiry seconds into a timezone-aware database timestamp."""
    try:
        seconds = max(0, int(expires_in))
    except (TypeError, ValueError):
        seconds = 3600
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)
