from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    organization_name: str = Field(min_length=1, max_length=200)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=12, max_length=200)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str | None
    email_verified_at: datetime | None
    mfa_enabled: bool

    model_config = {"from_attributes": True}


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str

    model_config = {"from_attributes": True}


class SignupResponse(BaseModel):
    user: UserOut
    organization: OrganizationOut


class LoginResponse(BaseModel):
    user: UserOut
    mfa_required: bool


class VerifyEmailRequest(BaseModel):
    token: str


class MfaEnrollResponse(BaseModel):
    provisioning_uri: str


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=8)


class InvitationCreate(BaseModel):
    email: EmailStr
    role_key: str = Field(min_length=1, max_length=100)


class InvitationOut(BaseModel):
    id: uuid.UUID
    email: str
    role_key: str
    accepted_at: datetime | None
    expires_at: datetime

    model_config = {"from_attributes": True}


class AcceptInvitationRequest(BaseModel):
    token: str
    full_name: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, min_length=12, max_length=200)


class AcceptInvitationResponse(BaseModel):
    user: UserOut
    organization: OrganizationOut


class SsoStartResponse(BaseModel):
    authorization_url: str


class SsoProviderStatusOut(BaseModel):
    provider: str
    configured: bool
