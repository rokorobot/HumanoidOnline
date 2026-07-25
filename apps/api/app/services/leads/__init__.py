"""Commercial-lead capture (WS7) — the first commercial conversion.

`service.capture_lead` orchestrates the whole write path (requirement-linked and
direct Robot-Detail captures), enforcing the WS7 integrity rules; `routing`
computes deterministic PENDING provider routes. All DB access lives here so the
router stays a thin HTTP edge.
"""
from app.services.leads.service import capture_lead

__all__ = ["capture_lead"]
