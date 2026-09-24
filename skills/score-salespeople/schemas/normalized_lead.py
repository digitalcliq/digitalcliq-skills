"""Common internal data model shared by all CRM adapters.

The scoring engine only ever sees these dataclasses. CRM-specific parsers
(parse_tekion.py, parse_vinsolutions.py) translate their proprietary export
formats into Lead objects before any math runs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal, Optional


class ActivityType(Enum):
    OUTBOUND_CALL = "outbound_call"
    OUTBOUND_TEXT = "outbound_text"
    OUTBOUND_EMAIL = "outbound_email"
    INBOUND_CALL = "inbound_call"
    INBOUND_TEXT = "inbound_text"
    INBOUND_EMAIL = "inbound_email"


@dataclass
class Activity:
    timestamp: datetime
    type: ActivityType
    salesperson_id: str
    is_auto_response: bool


@dataclass
class Appointment:
    set_timestamp: datetime
    set_by_salesperson_id: str
    scheduled_for: datetime
    status: Literal["set", "confirmed", "showed", "no_show", "cancelled"]
    show_timestamp: Optional[datetime] = None


@dataclass
class Deal:
    salesperson_id: str
    vehicle_type: Literal["new", "used"]
    written_timestamp: Optional[datetime] = None
    sold_timestamp: Optional[datetime] = None
    gross: Optional[float] = None


@dataclass
class Lead:
    lead_id: str
    created_timestamp: datetime
    source: str
    is_credit_app: bool

    assignment_history: list[tuple[datetime, str]] = field(default_factory=list)

    test_drive_taken: bool = False
    test_drive_timestamp: Optional[datetime] = None

    activities: list[Activity] = field(default_factory=list)
    appointment: Optional[Appointment] = None
    deal: Optional[Deal] = None

    def owner_at(self, timestamp: datetime) -> str:
        """Return whichever salesperson owned this lead at the given moment."""
        if not self.assignment_history:
            raise ValueError(f"Lead {self.lead_id} has no assignment history")
        valid = [(t, sp) for t, sp in self.assignment_history if t <= timestamp]
        if valid:
            return max(valid, key=lambda x: x[0])[1]
        return self.assignment_history[0][1]

    @property
    def initial_owner(self) -> str:
        return self.assignment_history[0][1] if self.assignment_history else ""

    @property
    def final_owner(self) -> str:
        return self.assignment_history[-1][1] if self.assignment_history else ""
