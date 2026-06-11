import os
from datetime import datetime, timedelta
from typing import Optional
from loguru import logger
import httpx
import asyncio
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from src.core.settings import system_setting
from src.core.exceptions import GoogleAPICallError, UnauthorizedGoogleAccess
from src.workspace_crud.crud.google_token import GoogleTokenCRUD
from src.workspace_crud.crud.user import UserCRUD
from src.models.google_token import GoogleToken
from src.models.google_user import User


class GoogleAuthService:
    def __init__(self, user_crud: UserCRUD, google_token_crud: GoogleTokenCRUD):
        self.user_crud = user_crud
        self.google_token_crud = google_token_crud

    def get_auth_flow(self):
        """Initializes a Google OAuth2.0 flow."""
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": system_setting.GOOGLE_CLIENT_ID,
                    "client_secret": system_setting.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [system_setting.GOOGLE_REDIRECT_URI],
                }
            },
            scopes=system_setting.GOOGLE_AUTH_SCOPES,
        )
        flow.redirect_uri = system_setting.GOOGLE_REDIRECT_URI
        return flow

    async def get_authorization_url(self) -> str:
        """Generates the Google authorization URL."""
        flow = self.get_auth_flow()
        authorization_url, state = flow.authorization_url(
            access_type="offline", include_granted_scopes="true"
        )
        logger.info(f"Generated Google authorization URL: {authorization_url}")
        logger.debug(f"Google auth flow state: {state}")
        return authorization_url

    async def exchange_code_for_token(self, auth_code: str, code_verifier: Optional[str] = None) -> dict:
        """Exchanges the authorization code for tokens and user info."""
        flow = self.get_auth_flow()
        try:
            logger.info("Step 1: Attempting to fetch token from Google with auth code.")
            
            # Relax scope matching for unverified apps
            os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
            if system_setting.ENV.lower() in ["development", "dev", "local"]:
                os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

            if code_verifier:
                try:
                    setattr(flow, "code_verifier", code_verifier)
                    logger.debug("Set PKCE code_verifier on flow for token exchange.")
                except Exception:
                    logger.warning("Unable to set code_verifier on Flow instance.")

            try:
                flow.fetch_token(code=auth_code)
            except Exception as e:
                msg = str(e)
                if "Scope has changed" in msg or "scope has changed" in msg:
                    logger.warning(f"Google returned a different scope set than requested: {msg}")
                    if not getattr(flow, "credentials", None):
                        logger.error("No credentials available after scope change error.")
                        raise
                else:
                    raise

            credentials = flow.credentials
            logger.info("Step 2: Successfully fetched token from Google.")

            token_expiry = credentials.expiry
            if not token_expiry:
                logger.warning("credentials.expiry was not provided, defaulting to 1 hour.")
                token_expiry = datetime.utcnow() + timedelta(hours=1)

            logger.info("Step 3: Attempting to get user info from Google.")
            user_info = await self._get_user_info_from_google(credentials.token)
            google_id = user_info.get("id")
            email = user_info.get("email")
            name = user_info.get("name")
            profile_pic_url = user_info.get("picture")
            logger.info(f"Step 4: Successfully got user info. Google ID: {google_id}, Email: {email}")

            if not google_id or not email:
                raise UnauthorizedGoogleAccess(
                    detail="Could not retrieve essential user info from Google."
                )

            # FIX: Safely check if this social account is already linked
            logger.info(f"Step 5: Checking if user with google_id '{google_id}' exists in DB.")
            google_link_user = await self.user_crud.get_by_google_id(google_id)
            
            system_user_id_to_return = None
            google_user_pk = None

            if not google_link_user:
                # FIX: Do not attempt to write a dictionary or object here. 
                # We don't have a system_user_id yet. The callback router handles this cleanly.
                logger.warning("Step 6: Google user entry not found. Proceeding as a new link registration flow.")
            else:
                logger.info(f"Step 7: Existing Google link found for System User: {google_link_user.system_user_id}")
                system_user_id_to_return = str(google_link_user.system_user_id)
                google_user_pk = google_link_user.id

            # Only save/upsert the Google integration token if the account binding table row exists
            if google_user_pk:
                logger.info(f"Step 8: Preparing to upsert Google Token for user_id: {google_user_pk}")
                google_token_obj = GoogleToken(
                    user_id=google_user_pk,
                    access_token=credentials.token,
                    refresh_token=credentials.refresh_token,
                    token_uri=credentials.token_uri,
                    client_id=credentials.client_id,
                    client_secret=credentials.client_secret,
                    scopes=list(credentials.scopes),
                    token_expiry=token_expiry,
                )
                await self.google_token_crud.upsert_token(google_token_obj)
                logger.success(f"Step 9: Successfully upserted Google tokens.")
            else:
                logger.warning("Step 8/9: Skipping database token save because social account linkage isn't complete yet.")

            expires_in_seconds = None
            if hasattr(credentials, "expires_in") and credentials.expires_in is not None:
                expires_in_seconds = int(credentials.expires_in)
            elif token_expiry:
                time_diff = token_expiry - datetime.utcnow()
                expires_in_seconds = max(int(time_diff.total_seconds()), 0)

            logger.success("Step 10: exchange_code_for_token completed successfully.")
            
            # Return system_user_id_to_return back so callback router can resolve the main user
            return {
                "user_id": system_user_id_to_return,
                "google_id": google_id,
                "email": email,
                "access_token": credentials.token,
                "expires_in": expires_in_seconds,
                "refresh_token_available": credentials.refresh_token is not None,
                "profile_pic_url": profile_pic_url
            }
        except Exception as e:
            logger.error(f"Error exchanging authorization code for token: {e}", exc_info=True)
            raise UnauthorizedGoogleAccess(detail=f"Failed to authenticate with Google: {e}")
        
    async def _get_user_info_from_google(self, access_token: str) -> dict:
        """Fetches basic user info using the access token."""
        userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
        headers = {"Authorization": f"Bearer {access_token}"}
        try:
            def _sync_fetch_user_info():
                with httpx.Client() as client:
                    response = client.get(userinfo_url, headers=headers)
                    response.raise_for_status()
                    return response.json()

            user_info = await asyncio.to_thread(_sync_fetch_user_info)
            return user_info
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching user info from Google: {e.response.status_code} - {e.response.text}", exc_info=True)
            raise UnauthorizedGoogleAccess(detail=f"Failed to get user info from Google: {e.response.text}")
        except httpx.RequestError as e:
            logger.error(f"Network error fetching user info from Google: {e}", exc_info=True)
            raise UnauthorizedGoogleAccess(detail=f"Network error getting user info from Google: {e}")
        except Exception as e:
            logger.error(f"Unexpected error fetching user info from Google: {e}", exc_info=True)
            raise UnauthorizedGoogleAccess(detail=f"An unexpected error occurred getting user info: {e}")

    async def get_credentials_for_user(self, user_id: str) -> Credentials:
        """
        Retrieves and refreshes Google Credentials for a given user.
        This is the primary method for getting active Google credentials
        to make API calls.
        """
        google_token_data = await self.google_token_crud.get_by_user_id(user_id)
        if not google_token_data:
            raise UnauthorizedGoogleAccess(detail="No Google token found for user.")

        creds = Credentials(
            token=google_token_data.access_token,
            refresh_token=google_token_data.refresh_token,
            token_uri=google_token_data.token_uri,
            client_id=google_token_data.client_id,
            client_secret=google_token_data.client_secret,
            scopes=google_token_data.scopes,
        )

        creds.expiry = google_token_data.token_expiry

        if not creds.valid or creds.expired and creds.refresh_token:
            logger.info(f"Refreshing Google token for user {user_id}...")
            try:
                creds.refresh(Request())
                logger.info(f"Google token refreshed successfully for user {user_id}.")

                await self.google_token_crud.update_token(
                    user_id,
                    {
                        "access_token": creds.token,
                        "token_expiry": creds.expiry,
                        "updated_at": datetime.utcnow(),
                    },
                )
                logger.info(f"Updated Google token in DB for user {user_id}.")
            except Exception as e:
                logger.error(f"Error refreshing Google token for user {user_id}: {e}")
                raise UnauthorizedGoogleAccess(
                    detail="Failed to refresh Google access token. Please re-authenticate."
                )
        elif creds.expired and not creds.refresh_token:
            logger.warning(
                f"Google token expired for user {user_id} and no refresh token available. User needs to re-authenticate."
            )
            raise UnauthorizedGoogleAccess(
                detail="Google access token expired. Please re-authenticate to get a refresh token."
            )

        return creds