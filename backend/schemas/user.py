"""
User-related request/response schemas.

Design decisions (interview talking points):
1. Separate Create / Login / Response schemas — each endpoint gets exactly the
   fields it needs. Response NEVER includes hashed_password (security boundary).
2. EmailStr validates email format automatically (rejects "notanemail").
3. min_length on password enforces a basic policy at the API edge.
4. from_attributes=True lets Pydantic read directly from a SQLAlchemy object.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from models.user import UserRole


class UserCreate(BaseModel):
    """Input for registration."""
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)  # bcrypt max is 72 bytes
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole = UserRole.PARALEGAL  # default least-privilege role


class UserLogin(BaseModel):
    """Input for login."""
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """
    Output for any endpoint returning a user.
    NOTE: no password / hashed_password field — this is the security boundary.
    """
    id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    firm_id: uuid.UUID
    firm_name: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
