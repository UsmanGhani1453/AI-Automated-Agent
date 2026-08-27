"""
Dashboard API for the adaptive email agent.

The dashboard is responsible for:
- viewing agent state
- reviewing drafts
- saving user edits
- recording approval/rejection
- triggering preference learning

Sending remains disabled here for safety.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.database.database import (
    get_conn,
    init_db,
    loads,
    rows_to_dicts,
)
from app.database.repository import (
    ComponentRepository,
    EmailRepository,
    ExperienceRepository,
    FeedbackRepository,
    InboxMessageRepository,
    PatternRepository,
    PreferenceRepository,
)
from app.email.reply_generator import ReplyGenerator
from app.learning.experience import Experience
from app.learning.learning_engine import LearningEngine
from app.memory.semantic import SemanticMemory


app = FastAPI(
    title="Adaptive Email Agent Dashboard API"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

learning_engine = LearningEngine()


class DraftEditRequest(BaseModel):
    body: str = Field(
        min_length=1,
        description="User's edited version of the draft",
    )


class FeedbackRequest(BaseModel):
    action: str = Field(
        description="approve, reject, or edit"
    )
    rating: int | None = Field(
        default=None,
        ge=1,
        le=5,
    )
    comment: str = ""
    replied: bool = False


@app.on_event("startup")
def startup():
    init_db()


# ----------------------------------------------------------------------
# Summary
# ----------------------------------------------------------------------

@app.get("/api/summary")
def summary():
    with get_conn() as conn:
        total_leads = conn.execute(
            "SELECT COUNT(*) c FROM leads"
        ).fetchone()["c"]

        total_emails = conn.execute(
            "SELECT COUNT(*) c FROM emails"
        ).fetchone()["c"]

        sent = conn.execute(
            "SELECT COUNT(*) c FROM emails WHERE sent=1"
        ).fetchone()["c"]

        pending = conn.execute(
            """
            SELECT COUNT(*) c
            FROM emails
            WHERE approved=0 AND sent=0
            """
        ).fetchone()["c"]

        replies = conn.execute(
            """
            SELECT COUNT(*) c
            FROM feedback
            WHERE replied=1
            """
        ).fetchone()["c"]

        avg_quality = conn.execute(
            "SELECT AVG(quality_score) a FROM emails"
        ).fetchone()["a"] or 0

        avg_rating = conn.execute(
            """
            SELECT AVG(rating) a
            FROM feedback
            WHERE rating IS NOT NULL
            """
        ).fetchone()["a"] or 0

        inbox_messages = conn.execute(
            "SELECT COUNT(*) c FROM inbox_messages"
        ).fetchone()["c"]

    return {
        "total_leads": total_leads,
        "total_emails": total_emails,
        "sent": sent,
        "pending_review": pending,
        "replies": replies,
        "inbox_messages": inbox_messages,
        "avg_quality_score": round(
            avg_quality,
            3,
        ),
        "avg_rating": round(
            avg_rating,
            2,
        ),
    }


# ----------------------------------------------------------------------
# Learning / memory
# ----------------------------------------------------------------------

@app.get("/api/strategies")
def strategies():
    return PatternRepository.all_for_prefix(
        "strategy:"
    )


@app.get("/api/components/{component_type}")
def components(component_type: str):
    return ComponentRepository.top_for_type(
        component_type,
        limit=20,
    )


@app.get("/api/component-types")
def component_types():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT component_type
            FROM email_components
            ORDER BY component_type
            """
        ).fetchall()

    return [
        row["component_type"]
        for row in rows
    ]


@app.get("/api/preferences")
def preferences():
    return PreferenceRepository.all()


@app.get("/api/semantic-statements")
def semantic_statements():
    return {
        "statements": SemanticMemory()
        .derive_statements(min_samples=2)
    }


@app.get("/api/experiences")
def experiences(limit: int = 30):
    limit = max(
        1,
        min(limit, 200),
    )

    return ExperienceRepository.recent(
        limit=limit
    )


@app.get("/api/quality-trend")
def quality_trend(limit: int = 50):
    limit = max(
        1,
        min(limit, 200),
    )

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                quality_score,
                created_at,
                strategy
            FROM emails
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return list(
        reversed(
            rows_to_dicts(rows)
        )
    )


# ----------------------------------------------------------------------
# Inbox
# ----------------------------------------------------------------------

@app.get("/api/inbox")
def inbox(limit: int = 50):
    limit = max(
        1,
        min(limit, 200),
    )

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM inbox_messages
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return rows_to_dicts(rows)


@app.get("/api/inbox/{message_id}")
def inbox_message(message_id: int):
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM inbox_messages
            WHERE id=?
            """,
            (message_id,),
        ).fetchone()

    if not row:
        raise HTTPException(
            404,
            "inbox message not found",
        )

    return dict(row)


# ----------------------------------------------------------------------
# Pending drafts
# ----------------------------------------------------------------------

@app.get("/api/pending-review")
def pending_review():
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                e.*,
                l.officer,
                l.company,
                l.email AS lead_email,
                l.location
            FROM emails e
            LEFT JOIN leads l
                ON e.lead_id = l.id
            WHERE e.approved=0
              AND e.sent=0
            ORDER BY e.id DESC
            """
        ).fetchall()

    output = []

    for row in rows_to_dicts(rows):
        row["analyzer_report"] = loads(
            row.pop(
                "analyzer_report_json"
            ),
            {},
        )

        row["components"] = loads(
            row.pop(
                "components_json"
            ),
            {},
        )

        output.append(row)

    return output


@app.get("/api/emails/{email_id}")
def get_email(email_id: int):
    email = EmailRepository.get(
        email_id
    )

    if not email:
        raise HTTPException(
            404,
            "email not found",
        )

    return email


# ----------------------------------------------------------------------
# Edit + learning
# ----------------------------------------------------------------------

@app.post("/api/emails/{email_id}/edit")
def edit_email(
    email_id: int,
    request: DraftEditRequest,
):
    email = EmailRepository.get(
        email_id
    )

    if not email:
        raise HTTPException(
            404,
            "email not found",
        )

    edited_body = request.body.strip()

    if not edited_body:
        raise HTTPException(
            400,
            "edited body cannot be empty",
        )

    original_body = (
        email.get("body")
        or ""
    ).strip()

    EmailRepository.set_user_edit(
        email_id,
        edited_body,
    )

    FeedbackRepository.create(
        email_id=email_id,
        rating=None,
        action="edit",
        comment="Edited through dashboard",
        replied=False,
    )

    lead_id = email.get(
        "lead_id"
    )

    with get_conn() as conn:
        lead_row = conn.execute(
            """
            SELECT *
            FROM leads
            WHERE id=?
            """,
            (lead_id,),
        ).fetchone()

    if not lead_row:
        raise HTTPException(
            404,
            "lead not found",
        )

    lead = dict(lead_row)

    experience = Experience(
        lead=lead,
        strategy=(
            email.get("strategy")
            or "INBOX_REPLY"
        ),
        components=email.get(
            "components",
            {},
        ),
        generated_email=original_body,
        analyzer_report=email.get(
            "analyzer_report",
            {},
        ),
        decision={
            "source": "dashboard_edit",
            "email_id": email_id,
        },
        user_action="edit",
        user_edited_email=edited_body,
        rating=None,
        replied=False,
        comment="Edited through dashboard",
        outcome="edited",
    )

    learning_result = learning_engine.learn(
        experience,
        email_id=email_id,
        component_ids=None,
    )

    return {
        "status": "learned",
        "email_id": email_id,
        "learning": learning_result,
    }


# ----------------------------------------------------------------------
# Approve / reject
# ----------------------------------------------------------------------

@app.post("/api/emails/{email_id}/feedback")
def submit_feedback(
    email_id: int,
    request: FeedbackRequest,
):
    email = EmailRepository.get(
        email_id
    )

    if not email:
        raise HTTPException(
            404,
            "email not found",
        )

    action = request.action.lower().strip()

    if action not in {
        "approve",
        "reject",
    }:
        raise HTTPException(
            400,
            "action must be approve or reject",
        )

    if action == "approve":
        rating = (
            request.rating
            if request.rating is not None
            else 5
        )

        EmailRepository.approve(
            email_id
        )

    else:
        rating = (
            request.rating
            if request.rating is not None
            else 2
        )

    FeedbackRepository.create(
        email_id=email_id,
        rating=rating,
        action=action,
        comment=request.comment,
        replied=request.replied,
    )

    return {
        "status": "recorded",
        "email_id": email_id,
        "action": action,
        "rating": rating,
    }


# ----------------------------------------------------------------------
# Static dashboard
# ----------------------------------------------------------------------

_static_dir = os.path.join(
    os.path.dirname(__file__),
    "static",
)

if os.path.isdir(_static_dir):
    app.mount(
        "/",
        StaticFiles(
            directory=_static_dir,
            html=True,
        ),
        name="static",
    )