"""Pydantic request schemas for the WildIdea web API."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=6)
    invite_code: Optional[str] = None
    opt_in_improvement: bool = False


class LoginRequest(BaseModel):
    email: str
    password: str


class RedeemInviteRequest(BaseModel):
    code: str


class CreateRunRequest(BaseModel):
    problem: str = Field(min_length=2)
    slot_count: int = Field(default=10, ge=1, le=30)
    forbid_terms: list[str] = Field(default_factory=list)
    search_enabled: bool = False
    parallel: int = Field(default=10, ge=1, le=10)
    generation_mode: str = Field(default="speed")


class FeedbackRequest(BaseModel):
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    label: Optional[str] = None
    comment: Optional[str] = None
    adopted: bool = False


class InteractionEventRequest(BaseModel):
    run_id: Optional[str] = None
    candidate_id: Optional[str] = None
    event_type: str
    payload: dict = Field(default_factory=dict)


class CreateInviteCodeRequest(BaseModel):
    code: Optional[str] = None
    bonus_credits: int = Field(default=10, ge=1, le=10000)
    max_redemptions: Optional[int] = Field(default=None, ge=1)
    expires_at: Optional[datetime] = None


class AdminCreditAdjustmentRequest(BaseModel):
    amount: int
    reason: str = "admin_adjustment"
