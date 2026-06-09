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

    async def exchange_code_for_token(self, auth_code: str) -> dict:
        """Exchanges the authorization code for tokens and user info."""
        flow = self.get_auth_flow()
        try:
            logger.info("Step 1: Attempting to fetch token from Google with auth code.")
            flow.fetch_token(code=auth_code)
            credentials = flow.credentials
            logger.info("Step 2: Successfully fetched token from Google.")

            token_expiry = credentials.expiry
            if not token_expiry:
                logger.warning(
                    "credentials.expiry was not provided, defaulting to 1 hour."
                )
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

            logger.info(f"Step 5: Checking if user with google_id '{google_id}' exists in DB.")
            user = await self.user_crud.get_by_google_id(google_id)
            if not user:
                logger.warning(f"Step 6a: User not found. Creating a new user object in memory.")
                user = User(
                    google_id=google_id,
                    email=email,
                    name=name,
                    profile_pic_url=profile_pic_url,
                )
                logger.info("Step 6b: Attempting to save the new user to the database.")
                created_user = await self.user_crud.create_user(user)
                if not created_user or not created_user.id:
                    logger.error("CRITICAL: create_user method did not return a valid user with an ID!")
                    raise Exception("Failed to create user in the database.")
                user = created_user
                logger.success(f"Step 6c: Successfully saved new user with DB ID: {user.id}")
                logger.info(f"New user created: {user.email}")
            else:
                logger.info(f"Step 7a: User found with ID {user.id}. Attempting to update.")
                await self.user_crud.update_user(
                    user.id,
                    {
                        "email": email,
                        "name": name,
                        "profile_pic_url": profile_pic_url,
                        "updated_at": datetime.utcnow(),
                    },
                )
                logger.info(f"Step 7b: Existing user {user.email} updated.")

            logger.info(f"Step 8: Preparing to upsert Google Token for user_id: {user.id}")
            google_token_obj = GoogleToken(
                user_id=user.id,
                access_token=credentials.token,
                refresh_token=credentials.refresh_token,
                token_uri=credentials.token_uri,
                client_id=credentials.client_id,
                client_secret=credentials.client_secret,
                scopes=list(credentials.scopes),
                token_expiry=token_expiry,
            )
            await self.google_token_crud.upsert_token(google_token_obj)
            logger.success(f"Step 9: Successfully upserted Google tokens for user {user.id}.")

            expires_in_seconds = None
            if (
                hasattr(credentials, "expires_in")
                and credentials.expires_in is not None
            ):
                expires_in_seconds = int(credentials.expires_in)
            elif token_expiry:
                time_diff = token_expiry - datetime.utcnow()
                if time_diff.total_seconds() > 0:
                    expires_in_seconds = int(time_diff.total_seconds())
                else:
                    expires_in_seconds = 0
            logger.success("Step 10: exchange_code_for_token completed successfully.")
            return {
                "user_id": user.id,
                "google_id": user.google_id,
                "email": user.email,
                "access_token": credentials.token,
                "expires_in": expires_in_seconds,
                "refresh_token_available": credentials.refresh_token is not None,
            }
        except Exception as e:
            logger.error(
                f"Error exchanging authorization code for token: {e}", exc_info=True
            )
            raise UnauthorizedGoogleAccess(
                detail=f"Failed to authenticate with Google: {e}"
            )

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
                # If refresh fails, delete the invalid token and force re-auth
                # In prod, you might want to mark the token as invalid
                # and prompt the user to re-authenticate gracefully.
                # await self.google_token_crud.delete_token(user_id) # Consider this action
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
