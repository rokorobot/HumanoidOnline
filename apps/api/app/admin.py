"""Minimal internal admin (SQLAdmin) over the knowledge layer.

Internal CRUD only — not the public contract, not styled (02_ARCHITECTURE.md §1,
API contract §7). Association tables with composite keys are intentionally not
registered here. No auth layer in WS2: this must be network-gated in deployment,
not exposed publicly.
"""
from __future__ import annotations

from fastapi import FastAPI
from sqladmin import Admin, ModelView

from app.db.session import engine
from app.models.buyer_requirement import BuyerRequirement
from app.models.capability import Capability
from app.models.commercial import AvailabilityOffer, Deployment, PricingOffer
from app.models.commercial_lead import CommercialLead, CommercialLeadProvider
from app.models.evidence import EvidenceSource
from app.models.manufacturer import Manufacturer, Provider
from app.models.match_result import MatchResult
from app.models.robot import Robot, RobotVariant
from app.models.spec import SpecDefinition
from app.models.use_case import UseCase


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


_VIEWS = [
    ManufacturerAdmin, ProviderAdmin, RobotAdmin, RobotVariantAdmin, UseCaseAdmin,
    CapabilityAdmin, SpecDefinitionAdmin, PricingOfferAdmin, AvailabilityOfferAdmin,
    DeploymentAdmin, EvidenceSourceAdmin, BuyerRequirementAdmin, MatchResultAdmin,
    CommercialLeadAdmin, CommercialLeadProviderAdmin,
]


def mount_admin(app: FastAPI) -> Admin:
    admin = Admin(app, engine, title="HumanoidOnline — internal admin")
    for view in _VIEWS:
        admin.add_view(view)
    return admin
