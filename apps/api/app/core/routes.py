"""Web routes the API needs to name.

The API composes hrefs for the app to render. That is deliberate: when a
component built its own document URL it went on pointing at
`/knowledge/<id>` for months after that module was withdrawn, and the API
had no way to notice — it was returning a perfectly valid citation that
resolved to a 404.

So every surface that shows a document — the Copilot's sources, the
document library, the evidence library, a control's evidence, a policy's
current document, a search hit — asks this module where that document
lives. One route, named once, and changing it changes every link.
"""

from __future__ import annotations

import uuid
from urllib.parse import urlencode

# The canonical Document Detail route. There is exactly one, and both the
# document library and a Copilot citation open it.
DOCUMENT_ROUTE = "/documents"

# Prefixes the web app rewrites to a 404: the modules retired when
# Veyntra narrowed to compliance. Mirrors RETIRED_MODULE_PREFIXES in
# apps/web/middleware.ts — a link landing on one of these is dead, which
# is exactly the failure this module exists to make impossible. Kept in
# step by tests on both sides.
RETIRED_ROUTE_PREFIXES = (
    "/sales",
    "/support",
    "/automation",
    "/knowledge",
    "/settings/integrations",
    "/recommendations",
    "/briefing",
    "/reports",
)


def document_detail_href(
    document_id: uuid.UUID | str,
    *,
    passage: str | None = None,
    section: str | None = None,
) -> str:
    """Where to open one document.

    `document_id` is the knowledge Document id, not the File id — the
    same identifier a Copilot citation carries, so a document opened from
    the library and the same document opened from a citation are the same
    URL and the same page.

    A passage, where given, travels in the query string so the reader
    lands on it. Without one the page opens at the top, which is what
    arriving from the document library should do.
    """
    query = urlencode(
        {key: value for key, value in (("passage", passage), ("section", section)) if value}
    )
    href = f"{DOCUMENT_ROUTE}/{document_id}" + (f"?{query}" if query else "")
    assert_reachable(href)
    return href


def assert_reachable(href: str) -> None:
    """A link the API hands out may never point into a withdrawn module.

    Checked on every href rather than left to a test, because the failure
    is invisible from here: a 200 with a well-formed link, and a customer
    who finds out by clicking it.
    """
    if any(href.startswith(prefix) for prefix in RETIRED_ROUTE_PREFIXES):
        raise AssertionError(
            f"href {href!r} points into a module withdrawn from the product"
        )


__all__ = [
    "DOCUMENT_ROUTE",
    "RETIRED_ROUTE_PREFIXES",
    "assert_reachable",
    "document_detail_href",
]
