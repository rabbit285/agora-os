"""Carry the processor a document named onto the activity it becomes

Transfers detected zero on real data, and the pipeline was not broken —
a payload was dropped at the acceptance boundary.

`draft_activity_from_document` reads "OpenAI" and "United States" out of
an uploaded document and puts them in the draft as `vendor_named` and
`destination_country`. It deliberately does not resolve them to a vendor
row, on the sound grounds that a document naming "OpenAI" is not proof it
means the vendor record of that name. But `privacy_accept` only ever read
`vendor_ids`, so on acceptance those two facts were discarded: the
document knew there was a US transfer, and the activity that came out of
it knew nothing.

Transfer detection then had one edge to work from —
`ProcessingActivityVendor` — and a document-derived activity has none. So
it proposed nothing, correctly, from a record that had been stripped of
the reason to propose anything.

These columns keep what the document said, as what it is: a name someone
wrote down, not a link to a vetted record. Detection matches it against
the vendor register where a row exists and proposes by name where none
does, and either way a person still confirms the mechanism.

Revision ID: a9d4c17e35b2
Revises: f7a3b91d2e64
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a9d4c17e35b2"
down_revision = "f7a3b91d2e64"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # What a source document called the processor, verbatim. Not a
    # foreign key: this is a claim in a file, and promoting it to a link
    # would attach the activity to a record nobody checked.
    op.add_column(
        "processing_activities",
        sa.Column("processor_named", sa.String(length=300), nullable=True),
    )
    # ISO 3166-1 alpha-2 where the document gave one clearly enough to
    # resolve; null when it named a place the product could not map.
    op.add_column(
        "processing_activities",
        sa.Column("destination_country_named", sa.String(length=2), nullable=True),
    )

    # The logical identity of a detected transfer, so re-running
    # detection reconciles instead of duplicating. Derived from what the
    # transfer is *about* — this activity, this recipient — never from
    # the wording of the draft.
    op.add_column(
        "data_transfers", sa.Column("source_key", sa.String(length=200), nullable=True)
    )
    # Which edge detection followed to find it, shown so a reviewer can
    # check the inference rather than trust it.
    op.add_column(
        "data_transfers", sa.Column("detected_from", sa.String(length=300), nullable=True)
    )
    # Set when something underneath a confirmed transfer moves — a vendor
    # changing country, a new DPA. Never rewrites the confirmed record.
    op.add_column(
        "data_transfers", sa.Column("review_reason", sa.String(length=1000), nullable=True)
    )
    op.create_index(
        "ix_data_transfers_source_key",
        "data_transfers",
        ["organization_id", "source_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_data_transfers_source_key", table_name="data_transfers")
    op.drop_column("data_transfers", "review_reason")
    op.drop_column("data_transfers", "detected_from")
    op.drop_column("data_transfers", "source_key")
    op.drop_column("processing_activities", "destination_country_named")
    op.drop_column("processing_activities", "processor_named")
