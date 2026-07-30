"""Side-effect-only import of every domain model module.

SQLAlchemy resolves string ForeignKey targets (e.g. `ForeignKey("users.id")`)
against whatever tables have been registered in `Base.metadata` in the
*current process* — which only happens when a model's module has actually
been imported somewhere. The FastAPI app imports every router/service and
therefore every model as a side effect of normal startup, but a bare
Temporal activity or script that only imports the one or two model modules
it directly touches will hit `NoReferencedTableError` the moment a flush
needs to resolve a foreign key into a table it never imported (e.g.
`documents.created_by -> users.id`, when only `app.knowledge.models` and
`app.core.models` were imported).

Import this module for its side effects wherever a process might issue a
flush without having gone through `app.main`'s import graph first — Alembic
migrations and Temporal activities, in particular.
"""

from __future__ import annotations

from app.ai import models as _ai_models  # noqa: F401
from app.audit import models as _audit_models  # noqa: F401
from app.automation import models as _automation_models  # noqa: F401
from app.compliance import models as _compliance_models  # noqa: F401
from app.core import models as _core_models  # noqa: F401
from app.identity import models as _identity_models  # noqa: F401
from app.integrations import models as _integrations_models  # noqa: F401
from app.knowledge import models as _knowledge_models  # noqa: F401
from app.sales import models as _sales_models  # noqa: F401
from app.secops import models as _secops_models  # noqa: F401
from app.support import models as _support_models  # noqa: F401
from app.trust_center import models as _trust_center_models  # noqa: F401
