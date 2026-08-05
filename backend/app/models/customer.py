from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Float,
)

from sqlalchemy.sql import func

from app.database.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    organization_id = Column(
        Integer,
        ForeignKey("organizations.id"),
        nullable=False,
    )

    # Identity

    first_name = Column(
        String,
        nullable=False,
    )

    last_name = Column(
        String,
    )

    email = Column(
        String,
        index=True,
    )

    phone = Column(
        String,
    )


    # Business information

    company = Column(
        String,
    )

    job_title = Column(
        String,
    )


    # Human notes

    notes = Column(
        Text,
    )


    # ==========================
    # AI CUSTOMER INTELLIGENCE
    # ==========================

    lifecycle_stage = Column(
        String,
        default="NEW",
    )

    buying_intent = Column(
        String,
        default="UNKNOWN",
    )

    opportunity_score = Column(
        Float,
        default=0,
    )

    engagement_score = Column(
        Float,
        default=0,
    )

    risk_level = Column(
        String,
        default="LOW",
    )

    communication_style = Column(
        String,
        nullable=True,
    )

    pain_points = Column(
        Text,
        nullable=True,
    )

    next_best_action = Column(
        String,
        nullable=True,
    )

    ai_profile = Column(
        Text,
        nullable=True,
    )


    # ==========================
    # SYSTEM
    # ==========================

    is_active = Column(
        Boolean,
        default=True,
    )


    created_at = Column(
        DateTime,
        server_default=func.now(),
    )


    updated_at = Column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )


    # ==========================
    # REVIEW ENGINE
    # ==========================

    last_reviewed_at = Column(
        DateTime,
        nullable=True,
    )


    next_review_at = Column(
        DateTime,
        nullable=True,
    )
