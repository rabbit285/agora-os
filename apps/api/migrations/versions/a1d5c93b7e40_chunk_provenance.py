"""Chunk provenance: the heading and page a citation can point a person at.

A citation used to render as "Document da7966ef · chunk 5" because that
was all a chunk knew about itself. Neither half of that is something the
customer can look up in their own copy of the document. The heading the
document gives itself, and the page it fell on, are.

Existing rows are left NULL rather than backfilled with a guess: the
source text is not in the database (only its chunks are), so a page
number could only be invented here. Re-indexing a document populates
them, and a citation with neither degrades to the document title.

Revision ID: a1d5c93b7e40
Revises: f8a3c47e91d2
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a1d5c93b7e40"
down_revision = "f8a3c47e91d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_chunks", sa.Column("section_label", sa.String(length=200), nullable=True)
    )
    op.add_column("document_chunks", sa.Column("page_number", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("document_chunks", "page_number")
    op.drop_column("document_chunks", "section_label")
