from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Usernames are case-sensitive ("Bat" != "bat"), so MySQL needs a binary collation.
Username = String(64).with_variant(mysql.VARCHAR(64, collation="utf8mb4_bin"), "mysql")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(Username, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
