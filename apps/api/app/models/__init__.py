"""ORM models mirroring db/schema.sql.

`db/schema.sql` is canonical (AGENTS.md rule 2): these models mirror it. We never
`create_all()` / autogenerate DDL, and every PG enum uses ``create_type=False``.
Importing this package registers all models on ``Base.metadata``.

WS2 covers the Knowledge Layer plus the commercial *read* models (pricing /
availability / deployment). WS5 adds the first Decision-layer *write* model,
`buyer_requirement` (Phase-2 buyer intent). Matching (`match_result`) and the
transaction layer (`commercial_lead*`) are later workstreams (WS6/WS7) and are
intentionally absent here.
"""
from app.models.buyer_requirement import BuyerRequirement
from app.models.capability import Capability, RobotCapability
from app.models.commercial import AvailabilityOffer, Deployment, PricingOffer
from app.models.event_log import EventLog
from app.models.evidence import EvidenceSource
from app.models.manufacturer import Manufacturer, Provider
from app.models.region import Region
from app.models.robot import Robot, RobotStatusHistory, RobotVariant
from app.models.spec import SpecDefinition, Specification
from app.models.use_case import UseCase, UseCaseFit

__all__ = [
    "AvailabilityOffer",
    "BuyerRequirement",
    "Capability",
    "Deployment",
    "EventLog",
    "EvidenceSource",
    "Manufacturer",
    "PricingOffer",
    "Provider",
    "Region",
    "Robot",
    "RobotCapability",
    "RobotStatusHistory",
    "RobotVariant",
    "SpecDefinition",
    "Specification",
    "UseCase",
    "UseCaseFit",
]
