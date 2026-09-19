"""Auth request/response schemas."""

from pydantic import BaseModel, EmailStr

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

    model_config = {"json_schema_extra": {
        "example": {"email": "user@example.com", "password": "securepassword123"}
    }}

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

    model_config = {"json_schema_extra": {
        "example": {"access_token": "eyJ...", "token_type": "bearer"}
    }}

class UserResponse(BaseModel):
    id: str
    email: str

    model_config = {"from_attributes": True}
