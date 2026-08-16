"""Declarative base and shared conventions for Paperazzi database models."""

from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


Timestamped = sa.Column(
    "created_at", sa.DateTime(), nullable=False, default=utcnow, server_default=sa.func.now()
)
