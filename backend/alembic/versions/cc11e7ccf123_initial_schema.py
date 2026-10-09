"""initial schema

Revision ID: cc11e7ccf123
Revises:
Create Date: 2026-09-28 20:02:38.208798

"""
from collections.abc import Sequence

import sqlalchemy as sa
from geoalchemy2 import Geography
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "cc11e7ccf123"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TIMESTAMPTZ = sa.DateTime(timezone=True)
NOW = sa.text("now()")
EMPTY_JSONB = sa.text("'{}'::jsonb")
POINT = Geography("POINT", srid=4326, spatial_index=False)


def str_enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=32,
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "daily_reports",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("ops_date", sa.Date(), nullable=False),
        sa.Column("metrics", JSONB(), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.Column("sent_at", TIMESTAMPTZ, nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_daily_reports")),
        sa.UniqueConstraint("ops_date", name=op.f("uq_daily_reports_ops_date")),
    )

    op.create_table(
        "districts",
        sa.Column("code", sa.String(4), nullable=False),
        sa.Column("name_th", sa.String(100), nullable=False),
        sa.Column("province_name_th", sa.String(100), nullable=False),
        sa.CheckConstraint(
            "code ~ '^[0-9]{4}$'",
            name=op.f("ck_districts_code_format"),
        ),
        sa.PrimaryKeyConstraint("code", name=op.f("pk_districts")),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("job_type", sa.String(50), nullable=False),
        sa.Column("payload", JSONB(), server_default=EMPTY_JSONB, nullable=False),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column(
            "status",
            str_enum("job_status", "pending", "running", "succeeded", "failed"),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("run_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.Column("locked_at", TIMESTAMPTZ, nullable=True),
        sa.Column("locked_by", sa.String(100), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.Column("updated_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.Column("finished_at", TIMESTAMPTZ, nullable=True),
        sa.CheckConstraint(
            "status <> 'running' OR locked_at IS NOT NULL",
            name=op.f("ck_jobs_running_has_locked_at"),
        ),
        sa.CheckConstraint(
            "attempts >= 0",
            name=op.f("ck_jobs_attempts_non_negative"),
        ),
        sa.CheckConstraint(
            "max_attempts > 0",
            name=op.f("ck_jobs_max_attempts_positive"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_jobs")),
        sa.UniqueConstraint("idempotency_key", name=op.f("uq_jobs_idempotency_key")),
    )
    op.create_index("ix_jobs_status_run_at", "jobs", ["status", "run_at"])

    op.create_table(
        "line_users",
        sa.Column("user_id", sa.String(33), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("report_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("false_report_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_blocked", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("first_seen_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_line_users")),
    )

    op.create_geospatial_table(
        "incidents",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("location", POINT, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("district_code", sa.String(4), nullable=False),
        sa.Column(
            "status",
            str_enum("incident_status", "open", "in_progress", "closed", "false_alarm"),
            server_default="open",
            nullable=False,
        ),
        sa.Column("ops_date", sa.Date(), nullable=False),
        sa.Column("created_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.Column("closed_at", TIMESTAMPTZ, nullable=True),
        sa.CheckConstraint(
            "(status IN ('closed', 'false_alarm')) = (closed_at IS NOT NULL)",
            name=op.f("ck_incidents_closed_at_matches_status"),
        ),
        sa.ForeignKeyConstraint(
            ["district_code"],
            ["districts.code"],
            name=op.f("fk_incidents_district_code_districts"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incidents")),
    )
    op.create_geospatial_index(
        "idx_incidents_location",
        "incidents",
        ["location"],
        postgresql_using="gist",
    )
    op.create_index(op.f("ix_incidents_district_code"), "incidents", ["district_code"])
    op.create_index("ix_incidents_ops_date", "incidents", ["ops_date"])
    op.create_index("ix_incidents_status_closed_at", "incidents", ["status", "closed_at"])

    op.create_table(
        "volunteers",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("line_user_id", sa.String(33), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("district_code", sa.String(4), nullable=False),
        sa.Column(
            "status",
            str_enum("volunteer_status", "pending", "approved", "rejected", "suspended"),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("approved_at", TIMESTAMPTZ, nullable=True),
        sa.Column("created_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.CheckConstraint(
            "status <> 'approved' OR approved_at IS NOT NULL",
            name=op.f("ck_volunteers_approved_has_approved_at"),
        ),
        sa.ForeignKeyConstraint(
            ["district_code"],
            ["districts.code"],
            name=op.f("fk_volunteers_district_code_districts"),
        ),
        sa.ForeignKeyConstraint(
            ["line_user_id"],
            ["line_users.user_id"],
            name=op.f("fk_volunteers_line_user_id_line_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_volunteers")),
        sa.UniqueConstraint("line_user_id", name=op.f("uq_volunteers_line_user_id")),
    )
    op.create_index(op.f("ix_volunteers_district_code"), "volunteers", ["district_code"])

    op.create_table(
        "assignments",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("incident_id", sa.BigInteger(), nullable=False),
        sa.Column("volunteer_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "status",
            str_enum("assignment_status", "accepted", "arrived", "done", "withdrawn"),
            server_default="accepted",
            nullable=False,
        ),
        sa.Column("accepted_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.Column("completed_at", TIMESTAMPTZ, nullable=True),
        sa.CheckConstraint(
            "(status = 'done') = (completed_at IS NOT NULL)",
            name=op.f("ck_assignments_completed_at_matches_status"),
        ),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_assignments_incident_id_incidents"),
        ),
        sa.ForeignKeyConstraint(
            ["volunteer_id"],
            ["volunteers.id"],
            name=op.f("fk_assignments_volunteer_id_volunteers"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assignments")),
        sa.UniqueConstraint(
            "incident_id",
            "volunteer_id",
            name=op.f("uq_assignments_incident_id_volunteer_id"),
        ),
    )
    op.create_index(op.f("ix_assignments_volunteer_id"), "assignments", ["volunteer_id"])

    op.create_table(
        "incident_events",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("incident_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column(
            "actor_type",
            str_enum("actor_type", "system", "reporter", "volunteer", "admin"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.String(64), nullable=True),
        sa.Column("payload", JSONB(), server_default=EMPTY_JSONB, nullable=False),
        sa.Column("created_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_incident_events_incident_id_incidents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_incident_events")),
    )
    op.create_index(
        "ix_incident_events_incident_id_created_at",
        "incident_events",
        ["incident_id", "created_at"],
    )

    op.create_geospatial_table(
        "reports",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("incident_id", sa.BigInteger(), nullable=True),
        sa.Column("reporter_user_id", sa.String(33), nullable=False),
        sa.Column("location", POINT, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_path", sa.String(500), nullable=True),
        sa.Column("ops_date", sa.Date(), nullable=False),
        sa.Column("created_at", TIMESTAMPTZ, server_default=NOW, nullable=False),
        sa.ForeignKeyConstraint(
            ["incident_id"],
            ["incidents.id"],
            name=op.f("fk_reports_incident_id_incidents"),
        ),
        sa.ForeignKeyConstraint(
            ["reporter_user_id"],
            ["line_users.user_id"],
            name=op.f("fk_reports_reporter_user_id_line_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reports")),
    )
    op.create_geospatial_index(
        "idx_reports_location",
        "reports",
        ["location"],
        postgresql_using="gist",
    )
    op.create_index(op.f("ix_reports_incident_id"), "reports", ["incident_id"])
    op.create_index(op.f("ix_reports_ops_date"), "reports", ["ops_date"])
    op.create_index(op.f("ix_reports_reporter_user_id"), "reports", ["reporter_user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_reports_reporter_user_id"), table_name="reports")
    op.drop_index(op.f("ix_reports_ops_date"), table_name="reports")
    op.drop_index(op.f("ix_reports_incident_id"), table_name="reports")
    op.drop_geospatial_index(
        "idx_reports_location",
        table_name="reports",
        postgresql_using="gist",
        column_name="location",
    )
    op.drop_geospatial_table("reports")

    op.drop_index("ix_incident_events_incident_id_created_at", table_name="incident_events")
    op.drop_table("incident_events")

    op.drop_index(op.f("ix_assignments_volunteer_id"), table_name="assignments")
    op.drop_table("assignments")

    op.drop_index(op.f("ix_volunteers_district_code"), table_name="volunteers")
    op.drop_table("volunteers")

    op.drop_index("ix_incidents_status_closed_at", table_name="incidents")
    op.drop_index("ix_incidents_ops_date", table_name="incidents")
    op.drop_index(op.f("ix_incidents_district_code"), table_name="incidents")
    op.drop_geospatial_index(
        "idx_incidents_location",
        table_name="incidents",
        postgresql_using="gist",
        column_name="location",
    )
    op.drop_geospatial_table("incidents")

    op.drop_table("line_users")

    op.drop_index("ix_jobs_status_run_at", table_name="jobs")
    op.drop_table("jobs")

    op.drop_table("districts")
    op.drop_table("daily_reports")
