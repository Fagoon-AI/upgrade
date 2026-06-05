from pydantic import BaseModel, Field, field_validator
from typing import List


class WebLoaderRequestModel(BaseModel):
    urls: List[str] = Field(..., description="List of HTTPS URLs to load from the web")

    @field_validator("urls", mode="before")
    def check_https(cls, urls):
        for url in urls:
            if not url.startswith("https://"):
                raise ValueError(f"URL '{url}' must start with 'https://'")
        return urls
