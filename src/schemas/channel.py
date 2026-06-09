from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator


class ChannelConfigRequest(BaseModel):
    channel: Literal["whatsapp", "messenger", "telegram"] = Field(
        ..., description="Channel to configure for the agent"
    )
    phone_number_id: Optional[str] = Field(
        default=None,
        description="WhatsApp phone number ID for Meta Graph API",
    )
    app_secret: Optional[str] = Field(
        default=None,
        description="App secret for WhatsApp/Messenger webhook validation",
    )
    access_token: Optional[str] = Field(
        default=None,
        description="WhatsApp permanent access token",
    )
    page_id: Optional[str] = Field(
        default=None,
        description="Facebook page ID for Messenger",
    )
    page_access_token: Optional[str] = Field(
        default=None,
        description="Facebook page access token for Messenger",
    )
    bot_token: Optional[str] = Field(
        default=None,
        description="Telegram bot token from @BotFather",
    )

    @model_validator(mode="after")
    def validate_channel_fields(cls, values):
        channel = values.channel
        if channel == "whatsapp":
            required = ["phone_number_id", "app_secret", "access_token"]
        elif channel == "messenger":
            required = ["page_id", "app_secret", "page_access_token"]
        elif channel == "telegram":
            required = ["bot_token"]
        else:
            raise ValueError("Unsupported channel")

        missing = [field for field in required if not getattr(values, field)]
        if missing:
            raise ValueError(f"Missing required fields for {channel}: {', '.join(missing)}")

        return values
