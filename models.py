"""Data models for the relationship ranking system."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class Bucket(Enum):
    UNASSIGNED = "unassigned"
    CLOSE = "close"
    CASUAL = "casual"
    ACQUAINTANCE = "acquaintance"


# Bucket configuration: (seed_score, floor_score)
BUCKET_CONFIG = {
    Bucket.CLOSE: {"seed": 750.0, "floor": 600.0},
    Bucket.CASUAL: {"seed": 450.0, "floor": 200.0},
    Bucket.ACQUAINTANCE: {"seed": 150.0, "floor": 0.0},
    Bucket.UNASSIGNED: {"seed": 450.0, "floor": 0.0},  # default to casual-range
}


@dataclass
class Contact:
    """A person imported from contacts."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    phone: str = ""
    email: str = ""
    organization: str = ""

    def display_name(self) -> str:
        """Best available name for display."""
        if self.name:
            return self.name
        if self.email:
            return self.email
        if self.phone:
            return self.phone
        return f"Unknown ({self.id[:8]})"


@dataclass
class ContactState:
    """Scoring state for a contact in the ranking system."""
    contact_id: str
    bucket: Bucket = Bucket.UNASSIGNED
    score: float = 450.0       # Glicko-style mu
    rd: float = 350.0          # Rating Deviation (uncertainty)
    volatility: float = 0.06   # How erratic the score is
    comparison_count: int = 0
    last_compared_at: Optional[str] = None  # ISO timestamp
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def apply_bucket(self, bucket: Bucket) -> None:
        """Set bucket and seed the score. RD drops from max to moderate
        because we now have *some* info (the user's bucket choice)."""
        self.bucket = bucket
        config = BUCKET_CONFIG[bucket]
        self.score = config["seed"]
        # RD drops from 350 (no info) to 200 (bucket info, but no pairwise yet)
        self.rd = 200.0


@dataclass
class Comparison:
    """Record of a single pairwise comparison."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    contact_a_id: str = ""
    contact_b_id: str = ""
    winner_id: Optional[str] = None  # None = equal
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
