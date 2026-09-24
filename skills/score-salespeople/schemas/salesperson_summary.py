"""Aggregated per-salesperson summary, used when the CRM provides a
pre-rolled User Activity Report instead of lead-level data.

This is the data shape Tekion's 'User Activity Report - By Sales Rep'
delivers. Each row = one salesperson, with totals computed by Tekion.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Role = Literal["salesperson", "bdc", "other_bucket", "placeholder"]


@dataclass
class SalespersonSummary:
    name: str

    # Lead funnel
    good_leads: int = 0
    appointments_created: int = 0
    appointments_scheduled: int = 0
    appointments_confirmed: int = 0
    appointments_shown: int = 0
    sold: float = 0.0  # fractional, .5 means split deal

    # Task discipline
    total_tasks: int = 0
    completed_tasks: int = 0
    active_tasks: int = 0
    tasks_overdue: int = 0

    # Outbound activity
    calls_out: int = 0
    calls_out_contacted: int = 0
    texts_sent: int = 0
    emails_sent: int = 0

    # Video engagement
    videos_sent: int = 0
    video_sent_leads: int = 0

    # Classification (set during scoring pipeline)
    role: Role = "salesperson"
    role_reason: str = ""

    @property
    def total_outbound(self) -> int:
        return self.calls_out + self.texts_sent + self.emails_sent

    @property
    def tasks_per_lead(self) -> float:
        return self.total_tasks / self.good_leads if self.good_leads else 0.0

    @property
    def touches_per_lead(self) -> float:
        return self.total_outbound / self.good_leads if self.good_leads else 0.0

    # Direct rate calculations used by the engine
    def sale_conversion(self) -> float:
        return self.sold / self.good_leads if self.good_leads else 0.0

    def set_rate(self) -> float:
        return self.appointments_scheduled / self.good_leads if self.good_leads else 0.0

    def show_rate(self) -> float:
        return self.appointments_shown / self.appointments_scheduled if self.appointments_scheduled else 0.0

    def task_completion(self) -> float:
        return self.completed_tasks / self.total_tasks if self.total_tasks else 0.0

    def call_connection(self) -> float:
        return self.calls_out_contacted / self.calls_out if self.calls_out else 0.0

    def confirmation_rate(self) -> float:
        return self.appointments_confirmed / self.appointments_scheduled if self.appointments_scheduled else 0.0

    def video_adoption(self) -> float:
        return self.video_sent_leads / self.good_leads if self.good_leads else 0.0
