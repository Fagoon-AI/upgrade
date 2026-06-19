from pydantic import BaseModel, Field, ConfigDict

class UserInDB(BaseModel):
    id: str = Field(alias="_id")
    model_config = ConfigDict(populate_by_name=True)

user = UserInDB(_id="123")
print("user.id:", hasattr(user, "id"), getattr(user, "id", None))
print("user._id:", hasattr(user, "_id"), getattr(user, "_id", None))
