"""ORM models mirroring db/schema.sql.

`db/schema.sql` is canonical (AGENTS.md rule 2): these models mirror it. We never
`create_all()` / autogenerate DDL, and every PG enum uses ``create_type=False``.
Importing this package registers all models on ``Base.metadata``.

WS2 covers the Knowledge Layer plus the commercial *read* models (pricing /
availability / deployment) needed to render the three independent dimensions and
price states. Decision- and transaction-layer tables (buyer_requirement,
match_result, commercial_lead*) are later workstreams and are intentionally
absent here.
"""
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
