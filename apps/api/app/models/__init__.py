"""ORM models mirroring db/schema.sql.

`db/schema.sql` is canonical (AGENTS.md rule 2): these models mirror it. We never
`create_all()` / autogenerate DDL, and every PG enum uses ``create_type=False``.
Importing this package registers all models on ``Base.metadata``.

WS2 covers the Knowledge Layer plus the commercial *read* models (pricing /
availability / deployment). WS5 adds `buyer_requirement` and WS6 adds
`match_result` (the Decision layer). WS7 adds the transaction layer
(`commercial_lead` + `commercial_lead_robot` + `commercial_lead_provider`).

DATA-D1 adds the discovery layer; DATA-D1.LIVE Slice A adds the acquisition
layer (`app.models.acquisition`) — schema only, no adapter or crawler.
"""
from app.models.acquisition import (
    CandidateCommercialSignal,
    CrawlRun,
    DiscoveryEvidenceExcerpt,
    ExtractionResult,
    FetchedPage,
    SourceEligibilityReview,
)
from app.models.buyer_requirement import BuyerRequirement
from app.models.capability import Capability, RobotCapability
from app.models.commercial import AvailabilityOffer, Deployment, PricingOffer
from app.models.commercial_lead import (
    CommercialLead,
    CommercialLeadProvider,
    CommercialLeadRobot,
)
from app.models.discovery import (
    CandidateClaim,
    CandidateImageRef,
    DiscoveryCandidate,
    DiscoverySource,
    PromotionAudit,
)
from app.models.event_log import EventLog
from app.models.evidence import EvidenceSource
from app.models.manufacturer import Manufacturer, Provider
from app.models.match_result import MatchResult
from app.models.region import Region
from app.models.robot import Robot, RobotStatusHistory, RobotVariant
from app.models.robot_image import RobotImage
from app.models.spec import SpecDefinition, Specification
from app.models.use_case import UseCase, UseCaseFit

__all__ = [
    "AvailabilityOffer",
    "BuyerRequirement",
    "Capability",
    "CandidateClaim",
    "CandidateCommercialSignal",
    "CandidateImageRef",
    "CommercialLead",
    "CommercialLeadProvider",
    "CommercialLeadRobot",
    "CrawlRun",
    "Deployment",
    "DiscoveryCandidate",
    "DiscoveryEvidenceExcerpt",
    "DiscoverySource",
    "EventLog",
    "EvidenceSource",
    "ExtractionResult",
    "FetchedPage",
    "Manufacturer",
    "MatchResult",
    "PricingOffer",
    "PromotionAudit",
    "Provider",
    "Region",
    "Robot",
    "RobotCapability",
    "RobotImage",
    "RobotStatusHistory",
    "RobotVariant",
    "SourceEligibilityReview",
    "SpecDefinition",
    "Specification",
    "UseCase",
    "UseCaseFit",
]
