from pydantic import BaseModel, EmailStr

class userSchema(BaseModel):
    username: str
    password: str

