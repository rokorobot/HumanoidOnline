"""ORM models mirroring db/schema.sql.

WS1 establishes the *pattern* with two neutral infrastructure tables — `region`
(geography) and `event_log` (analytics). The full knowledge model
(manufacturers, robots, variants, specs, evidence, …) is WS2 and is deliberately
NOT implemented here. Importing this package registers the models on
`Base.metadata`.
"""
from app.models.event_log import EventLog
from app.models.region import Region

__all__ = ["EventLog", "Region"]
