"""AGENT-02 public projections — the boundary where internal identity stops.

The governed read layer (`services/reads.py`) serializes for the website and the
public HTTP API, and its `RobotListItem` carries `id` — the row's PostgreSQL
UUID. That is legitimate there and stays. It is **not** legitimate on an agent
surface: `docs/20` §8 makes the slug the canonical external identifier and states
that internal database UUIDs are never the public contract, §20 forbids database
selectors outright, and §21.10 requires that no raw database identifier appear in
any request or response.

So this module is a projection, not a second serializer. It consumes the governed
`RobotListItem` and reshapes *identity* only — dropping the internal id, deriving
`canonical_url` from the slug. It never recomputes a robot fact: `price_display`,
`primary_image`, `available_modes` and the UNKNOWN-bearing spec fields are passed
through exactly as the governed read produced them, so pricing semantics
(`docs/20` §10), MEDIA-01 image eligibility and `null`-means-UNKNOWN (§9.1) can
only ever have one implementation.

`PriceDisplay` and `RobotImagePrimary` are reused deliberately: they are value
objects carrying no identifiers, and re-declaring them here would fork the
pricing and image display rules — the opposite of the point.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import PriceDisplay
from app.schemas.robot import RobotImagePrimary, RobotListItem

#: The citable address of a robot (`docs/20` §8). Relative because this is the
#: transport-independent semantic layer: the absolute origin belongs to whichever
#: binding serves it, and this service has no governed origin helper to borrow.
CANONICAL_ROBOT_PATH = "/robots/{slug}"


def canonical_robot_url(slug: str) -> str:
    """`/robots/{slug}` — derived from the canonical slug and nothing else.

    Never from a database id, never from a caller-supplied value, and with no
    alternate aliases: §8 has exactly one citable address per robot.
    """
    return CANONICAL_ROBOT_PATH.format(slug=slug)


class AgentManufacturerRef(BaseModel):
    """A manufacturer as an agent may see it: slug + name, no row id."""

    slug: str
    name: str


class AgentRobotListItem(BaseModel):
    """The `docs/20` §5 list projection, exactly.

    Mandatory: `slug`, `name`, `commercial_status`, `canonical_url`,
    `manufacturer`, `deployment_count`, `updated_at`. UNKNOWN-capable (present as
    `null`, key never omitted): `payload_kg`, `height_cm`, `mobility`.
    Conditional: `price_display`, `available_modes`, `primary_image`.

    Fields the HTTP schema also carries — `id`, `summary`, `hero_image_url` — are
    deliberately absent. `id` is forbidden (§8/§20); the other two are simply not
    in the ratified projection, and adding output fields is an additive decision
    for the contract to take, not for this layer to assume.
    """

    slug: str
    name: str
    commercial_status: str
    canonical_url: str
    manufacturer: AgentManufacturerRef
    payload_kg: float | None = None
    height_cm: float | None = None
    mobility: str | None = None
    price_display: PriceDisplay | None = None
    available_modes: list[str]
    deployment_count: int
    primary_image: RobotImagePrimary | None = None
    updated_at: datetime


def project_list_item(item: RobotListItem) -> AgentRobotListItem:
    """Project one governed list read onto the agent surface.

    Identity is reshaped; facts are forwarded untouched.
    """
    return AgentRobotListItem(
        slug=item.slug,
        name=item.name,
        commercial_status=item.commercial_status,
        canonical_url=canonical_robot_url(item.slug),
        manufacturer=AgentManufacturerRef(
            slug=item.manufacturer.slug, name=item.manufacturer.name
        ),
        payload_kg=item.payload_kg,
        height_cm=item.height_cm,
        mobility=item.mobility,
        price_display=item.price_display,
        available_modes=item.available_modes,
        deployment_count=item.deployment_count,
        primary_image=item.primary_image,
        updated_at=item.updated_at,
    )
