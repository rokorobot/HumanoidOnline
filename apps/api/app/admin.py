"""Minimal internal admin (SQLAdmin) over the knowledge layer.

Internal CRUD only — not the public contract, not styled (02_ARCHITECTURE.md §1,
API contract §7). Association tables with composite keys are intentionally not
registered here.

WS8.1 / R1 (gap B1): this surface is no longer unauthenticated. It now requires
application-level authentication **and** fails closed when unconfigured. The
network boundary (DEP P4) is still owed by WS8.7/WS8.8 — see `mount_admin`.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from sqladmin import Admin, ModelView

from app.config import get_settings
from app.db.session import engine
from app.models.buyer_requirement import BuyerRequirement
from app.models.capability import Capability
from app.models.commercial import AvailabilityOffer, Deployment, PricingOffer
from app.models.commercial_lead import CommercialLead, CommercialLeadProvider
from app.models.discovery import (
    CandidateClaim,
    CandidateImageRef,
    DiscoveryCandidate,
    DiscoverySource,
    PromotionAudit,
)
from app.models.evidence import EvidenceSource
from app.models.manufacturer import Manufacturer, Provider
from app.models.match_result import MatchResult
from app.models.robot import Robot, RobotVariant
from app.models.robot_image import RobotImage
from app.models.spec import SpecDefinition
from app.models.use_case import UseCase
from app.security.admin_auth import AdminAuth

logger = logging.getLogger(__name__)


class ManufacturerAdmin(ModelView, model=Manufacturer):
    column_list = [Manufacturer.slug, Manufacturer.name, Manufacturer.deployment_status]
    column_searchable_list = [Manufacturer.slug, Manufacturer.name]
    name_plural = "Manufacturers"


class ProviderAdmin(ModelView, model=Provider):
    column_list = [Provider.slug, Provider.name, Provider.type, Provider.is_active]
    name_plural = "Providers"


class RobotAdmin(ModelView, model=Robot):
    column_list = [Robot.slug, Robot.name, Robot.commercial_status, Robot.is_published]
    column_searchable_list = [Robot.slug, Robot.name]
    name_plural = "Robots"


class RobotVariantAdmin(ModelView, model=RobotVariant):
    column_list = [RobotVariant.slug, RobotVariant.name, RobotVariant.is_developer]
    name_plural = "Robot variants"


class RobotImageAdmin(ModelView, model=RobotImage):
    # MEDIA-01 provenance triage. identity_status / rights_status decide display
    # eligibility — never the presence of image_url.
    column_list = [
        RobotImage.robot_id, RobotImage.image_type, RobotImage.source_type,
        RobotImage.source_name, RobotImage.identity_status, RobotImage.rights_status,
        RobotImage.is_primary, RobotImage.is_official,
    ]
    name_plural = "Robot images (MEDIA-01)"


class UseCaseAdmin(ModelView, model=UseCase):
    column_list = [UseCase.slug, UseCase.name, UseCase.category]
    name_plural = "Use cases"


class CapabilityAdmin(ModelView, model=Capability):
    column_list = [Capability.slug, Capability.name, Capability.category]
    name_plural = "Capabilities"


class SpecDefinitionAdmin(ModelView, model=SpecDefinition):
    column_list = [SpecDefinition.key, SpecDefinition.label, SpecDefinition.value_type]
    name_plural = "Spec definitions"


class PricingOfferAdmin(ModelView, model=PricingOffer):
    column_list = [
        PricingOffer.robot_id, PricingOffer.transaction_type,
        PricingOffer.price_type, PricingOffer.price, PricingOffer.currency,
    ]
    name_plural = "Pricing offers"


class AvailabilityOfferAdmin(ModelView, model=AvailabilityOffer):
    column_list = [
        AvailabilityOffer.robot_id, AvailabilityOffer.transaction_type,
        AvailabilityOffer.availability_status,
    ]
    name_plural = "Availability offers"


class DeploymentAdmin(ModelView, model=Deployment):
    column_list = [Deployment.robot_id, Deployment.customer_name, Deployment.status]
    name_plural = "Deployments"


class EvidenceSourceAdmin(ModelView, model=EvidenceSource):
    column_list = [
        EvidenceSource.subject_type, EvidenceSource.source_type,
        EvidenceSource.confidence, EvidenceSource.verified_at,
    ]
    name_plural = "Evidence sources"


class BuyerRequirementAdmin(ModelView, model=BuyerRequirement):
    column_list = [
        BuyerRequirement.id, BuyerRequirement.use_case_id,
        BuyerRequirement.preferred_transaction, BuyerRequirement.created_at,
    ]
    name_plural = "Buyer requirements"


class MatchResultAdmin(ModelView, model=MatchResult):
    column_list = [
        MatchResult.requirement_id, MatchResult.robot_id, MatchResult.rank,
        MatchResult.score, MatchResult.category,
    ]
    name_plural = "Match results"


class CommercialLeadAdmin(ModelView, model=CommercialLead):
    # The transaction objects finally surface to internal ops (WS7 §16). Read/
    # triage only — SQLAdmin, not a CRM. `lead_status` transitions happen here
    # (admin-owned); the public capture path never sets anything but 'NEW'.
    column_list = [
        CommercialLead.id, CommercialLead.created_at, CommercialLead.contact_email,
        CommercialLead.organization, CommercialLead.country_region_id,
        CommercialLead.preferred_transaction, CommercialLead.lead_status,
    ]
    column_searchable_list = [CommercialLead.contact_email, CommercialLead.organization]
    column_sortable_list = [CommercialLead.created_at, CommercialLead.lead_status]
    name_plural = "Commercial leads"


class CommercialLeadProviderAdmin(ModelView, model=CommercialLeadProvider):
    column_list = [
        CommercialLeadProvider.lead_id, CommercialLeadProvider.provider_id,
        CommercialLeadProvider.robot_id, CommercialLeadProvider.status,
        CommercialLeadProvider.contacted_at,
    ]
    name_plural = "Commercial lead — provider routes"


class DiscoverySourceAdmin(ModelView, model=DiscoverySource):
    # DATA-D1 radar registry. A source is crawler-eligible only when reviewed +
    # access-permitted + enabled (DATA-D1.9, enforced by a DB CHECK).
    column_list = [
        DiscoverySource.key, DiscoverySource.name, DiscoverySource.source_class,
        DiscoverySource.tos_status, DiscoverySource.robots_status,
        DiscoverySource.eligibility_reviewed_by, DiscoverySource.is_enabled,
    ]
    column_searchable_list = [DiscoverySource.key, DiscoverySource.name]
    name_plural = "Discovery sources (DATA-D1)"


class DiscoveryCandidateAdmin(ModelView, model=DiscoveryCandidate):
    # Noncanonical research triage. Promotion to canonical is NOT done here — it is
    # the governed CLI (app.cli.promote_candidate); the pipeline never promotes.
    column_list = [
        DiscoveryCandidate.candidate_name, DiscoveryCandidate.candidate_manufacturer,
        DiscoveryCandidate.entity_type, DiscoveryCandidate.identity_status,
        DiscoveryCandidate.status, DiscoveryCandidate.trace_state,
        DiscoveryCandidate.promoted_robot_id,
    ]
    column_searchable_list = [
        DiscoveryCandidate.candidate_name, DiscoveryCandidate.candidate_manufacturer,
    ]
    column_sortable_list = [DiscoveryCandidate.status, DiscoveryCandidate.identity_status]
    name_plural = "Discovery candidates (DATA-D1)"


class CandidateClaimAdmin(ModelView, model=CandidateClaim):
    column_list = [
        CandidateClaim.candidate_id, CandidateClaim.field_key,
        CandidateClaim.claimed_value, CandidateClaim.claim_status,
    ]
    name_plural = "Candidate claims (DATA-D1)"


class CandidateImageRefAdmin(ModelView, model=CandidateImageRef):
    column_list = [
        CandidateImageRef.candidate_id, CandidateImageRef.image_url,
        CandidateImageRef.credited_to, CandidateImageRef.media_status,
    ]
    name_plural = "Candidate images (DATA-D1, reference-only)"


class PromotionAuditAdmin(ModelView, model=PromotionAudit):
    column_list = [
        PromotionAudit.candidate_id, PromotionAudit.action,
        PromotionAudit.promoted_robot_id, PromotionAudit.approved_by,
        PromotionAudit.created_at,
    ]
    name_plural = "Promotion audit (DATA-D1, append-only)"
    # WS8.1 / R6 (gap B5): the append-only promise is now enforced, not merely
    # documented. These flags remove create/edit/delete from the admin UI; the
    # ORM listeners in `app.models.discovery` are the backstop that also covers
    # any other session (defence in depth — the UI flag alone is not the gate).
    can_create = False
    can_edit = False
    can_delete = False


_VIEWS = [
    ManufacturerAdmin, ProviderAdmin, RobotAdmin, RobotVariantAdmin, RobotImageAdmin,
    UseCaseAdmin,
    CapabilityAdmin, SpecDefinitionAdmin, PricingOfferAdmin, AvailabilityOfferAdmin,
    DeploymentAdmin, EvidenceSourceAdmin, BuyerRequirementAdmin, MatchResultAdmin,
    CommercialLeadAdmin, CommercialLeadProviderAdmin,
    DiscoverySourceAdmin, DiscoveryCandidateAdmin, CandidateClaimAdmin,
    CandidateImageRefAdmin, PromotionAuditAdmin,
]


def admin_is_configured() -> bool:
    """True when every credential the admin needs is present."""
    s = get_settings()
    return bool(s.admin_username and s.admin_password and s.admin_session_secret)


def mount_admin(app: FastAPI) -> Admin | None:
    """Mount the internal admin, or refuse to mount it (WS8.1 / R1).

    Fail closed (WS8-L5): with no configured credentials the surface is **not
    mounted at all**. Returning ``None`` is the correct, safe outcome — never
    mount an unauthenticated CRUD surface over buyer PII.

    This is B1 *stage 1*. The network boundary that puts admin on a separate
    protected host/listener (DEP P4) is realized in WS8.7 (R27) and probed from
    outside in WS8.8 (R29). Both layers are mandatory; neither substitutes for
    the other.
    """
    s = get_settings()
    if not admin_is_configured():
        logger.warning(
            "Internal admin NOT mounted: ADMIN_USERNAME, ADMIN_PASSWORD and "
            "ADMIN_SESSION_SECRET must all be set. Refusing to expose an "
            "unauthenticated admin surface (WS8.1 / R1)."
        )
        return None

    admin = Admin(
        app,
        engine,
        title="HumanoidOnline — internal admin",
        authentication_backend=AdminAuth(
            secret_key=s.admin_session_secret,
            username=s.admin_username,
            password=s.admin_password,
        ),
    )
    for view in _VIEWS:
        admin.add_view(view)
    return admin
