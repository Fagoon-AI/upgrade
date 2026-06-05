from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
import bcrypt
import secrets
import hashlib
from pydantic import BaseModel, EmailStr, Field, field_validator
from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema
from pydantic import ConfigDict
from bson import ObjectId

from src.utils.upgrade_auth.app_error import AppError


class PyObjectId(str):
    """
    Custom Pydantic type for MongoDB ObjectId.
    Handles serialization and deserialization of ObjectId to/from string.
    """
    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: Any, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        def validate_object_id(value: Any) -> str:
            if isinstance(value, ObjectId):
                return str(value)
            if isinstance(value, str) and ObjectId.is_valid(value):
                return value
            raise ValueError("Invalid ObjectId")

        def serialize_object_id(value: Any) -> str:
            if isinstance(value, ObjectId):
                return str(value)
            return value

        return core_schema.json_or_python_schema(
            json_schema=core_schema.no_info_plain_validator_function(validate_object_id),
            python_schema=core_schema.union_schema([
                core_schema.is_instance_schema(ObjectId),
                core_schema.no_info_plain_validator_function(validate_object_id),
            ]),
            serialization=core_schema.plain_serializer_function_ser_schema(
                serialize_object_id,
                info_arg=False,
                when_used='json'
            )
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        # Directly define the JSON schema for a string representing an ObjectId
        return JsonSchemaValue(
            {
                "type": "string",
                "pattern": "^[0-9a-fA-F]{24}$",
                "description": "A valid MongoDB ObjectId (24-character hexadecimal string)"
            }
        )


class UserBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    photo: str = "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9e/Male_Avatar.jpg/800px-Male_Avatar.jpg"
    role: str = "user"  # 'user', 'premium', 'employee', 'admin', 'superadmin'
    visited: int = 0
    verified: bool = False
    bio: Optional[str] = None
    description: Optional[str] = None
    social_media: Dict[str, Optional[str]] = Field(
        default_factory=lambda: {
            "facebook": None,
            "github": None,
            "instagram": None,
            "linkedin": None,
        }
    )
    token: Optional[str] = None

    @field_validator("social_media", mode="before")
    @classmethod
    def map_social_media_keys(cls, v: Any) -> Dict[str, Optional[str]]:
        if isinstance(v, dict):
            mapped_data = {
                "facebook": v.get("facebook") or v.get("additionalProp1"),
                "github": v.get("github") or v.get("additionalProp2"),
                "instagram": v.get("instagram") or v.get("additionalProp3"),
                "linkedin": v.get("linkedin") or v.get("additionalProp4"),
            }
            return {k: val for k, val in mapped_data.items() if val is not None}
        return v


class UserCreate(UserBase):
    """
    Pydantic model for user creation (input).
    """
    password: str = Field(..., min_length=8)
    password_confirm: str

    @field_validator("password_confirm")
    @classmethod
    def validate_passwords_match(cls, value: str, info: Any) -> str:
        if "password" in info.data and value != info.data["password"]:
            raise ValueError("Passwords do not match!")
        return value

class UserUpdate(BaseModel):
    """
    Pydantic model for user update (input) - partial updates are handled by .update(filtered_body).
    """
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    photo: Optional[str] = None
    bio: Optional[str] = None
    description: Optional[str] = None
    social_media: Optional[Dict[str, Optional[str]]] = None


class PasswordResetRequest(BaseModel):
    """
    Pydantic model for password reset (input via token).
    Does NOT include password_current.
    """
    password: str = Field(..., min_length=8)
    password_confirm: str

    @field_validator("password_confirm")
    @classmethod
    def validate_passwords_match(cls, value: str, info: Any) -> str:
        if "password" in info.data and value != info.data["password"]:
            raise ValueError("New passwords do not match!")
        return value


class PasswordUpdate(BaseModel):
    """
    Pydantic model for password update (input).
    """
    password_current: str
    password: str = Field(..., min_length=8)
    password_confirm: str

    @field_validator("password_confirm")
    @classmethod
    def validate_new_passwords_match(cls, value: str, info: Any) -> str:
        if "password" in info.data and value != info.data["password"]:
            raise ValueError("New passwords do not match!")
        return value

class UserInDB(UserBase):
    """
    Pydantic model for database representation of User.
    """
    id: str = Field(alias="_id")
    password: str
    password_changed_at: Optional[datetime] = None
    password_reset_token: Optional[str] = None
    password_reset_expires: Optional[datetime] = None
    active: bool = True

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: lambda dt: dt.isoformat(), ObjectId: str}
    )

    def correct_password(self, candidate_password: str) -> bool:
        """
        Compares a plaintext password with the hashed password stored in the database.
        """
        if not self.password:
            return False
        return bcrypt.checkpw(candidate_password.encode("utf-8"), self.password.encode("utf-8"))

    def changed_password_after(self, jwt_timestamp: int) -> bool:
        """
        Checks if the user's password was changed after the JWT was issued.
        jwt_timestamp is typically the 'iat' (issued at) claim from the JWT.
        """
        if self.password_changed_at:
            if self.password_changed_at.tzinfo is None:
                changed_timestamp = int(self.password_changed_at.replace(tzinfo=timezone.utc).timestamp())
            else:
                changed_timestamp = int(self.password_changed_at.timestamp())
            return jwt_timestamp < changed_timestamp
        return False

    def create_password_reset_token(self) -> str:
        """
        Generates a cryptographically strong password reset token,
        hashes it, and stores the hashed token and its expiration date
        in the user document. Returns the unhashed token for sending to the user.
        """
        reset_token = secrets.token_hex(32)
        self.password_reset_token = hashlib.sha256(reset_token.encode("utf-8")).hexdigest()
        self.password_reset_expires = datetime.now(timezone.utc) + timedelta(minutes=10)
        return reset_token

class UserResponse(UserBase):
    """
    Pydantic model for response (hide password and other sensitive fields).
    """
    id: str = Field(alias="_id")
    verified: bool
    access_token: Optional[str] = None

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: lambda dt: dt.isoformat(), ObjectId: str}
    )


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    url: Optional[str] = None

class RefreshToken(BaseModel):
    id: str = Field(alias="_id")
    user_id: str = Field(...)
    token: str = Field(...)
    expires_at: datetime = Field(...)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: lambda dt: dt.isoformat(), ObjectId: str}
    )


class LoginSuccessResponse(BaseModel):
    status: str = "success"
    message: str = "Login successful"
    id: str = None
    token:str = None

class AccessTokenResponse(BaseModel):
    access_token: str

class LoginFailureResponse(BaseModel):
    status: str = "error"
    message: str = "Invalid credentials or authentication failed"

class MeResponse(BaseModel):
    name: str
    email: EmailStr
    photo: str
    role: str
    visited: int
    verified: bool
    bio: Optional[str] = None
    description: Optional[str] = None
    social_media: Dict[str, Optional[str]]
    access: List[Dict[str, Any]] = []
    access_token: str


    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: lambda dt: dt.isoformat()}
    )