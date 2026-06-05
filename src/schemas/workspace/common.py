from pydantic import BaseModel


class Message(BaseModel):
    message: str


class GoogleAuthURL(BaseModel):
    auth_url: str
