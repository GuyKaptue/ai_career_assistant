from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class UserProfile:
    user_id: str
    email: str
    full_name: str
    target_role: str = ""
    location: str = ""
    summary: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "email": self.email,
            "full_name": self.full_name,
            "target_role": self.target_role,
            "location": self.location,
            "summary": self.summary,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
