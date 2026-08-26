"""
Dashboard API: read-only endpoints over the agent's own tables. This is
intentionally separate from any agent decision-making — it exists purely so
a human can see what the agent has learned. Also exposes a couple of
write endpoints for approving/rating emails from the dashboard, since that's
the natural place a human reviews queued drafts.
"""
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os

from app.database.database import get_conn, init_db, rows_to_dicts, loads
from app.database.repository import (
    PatternRepository, PreferenceRepository, ExperienceRepository,
    ComponentRepository, EmailRepository, FeedbackRepository,
)
from app.memory.semantic import SemanticMemory
from app.learning.learning_engine import LearningEngine

app = FastAPI(title="Email Agent Dashboard API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

learning_engine = LearningEngine()


@app.on_event("startup")
def startup():
    init_db()


@app.get("/api/summary")
def summary():
    with get_conn() as conn:
        total_leads = conn.execute("SELECT COUNT(*) c FROM leads").fetchone()["c"]
        total_emails = conn.execute("SELECT COUNT(*) c FROM emails").fetchone()["c"]
        sent = conn.execute("SELECT COUNT(*) c FROM emails WHERE sent=1").fetchone()["c"]
        pending = conn.execute("SELECT COUNT(*) c FROM emails WHERE approved=0 AND sent=0").fetchone()["c"]
        replies = conn.execute("SELECT COUNT(*) c FROM feedback WHERE replied=1").fetchone()["c"]
        avg_quality = conn.execute("SELECT AVG(quality_score) a FROM emails").fetchone()["a"] or 0
        avg_rating = conn.execute("SELECT AVG(rating) a FROM feedback WHERE rating IS NOT NULL").fetchone()["a"] or 0
    return {
        "total_leads": total_leads,
        "total_emails": total_emails,
        "sent": sent,
        "pending_review": pending,
        "replies": replies,
        "avg_quality_score": round(avg_quality, 3),
        "avg_rating": round(avg_rating, 2),
    }


@app.get("/api/strategies")
def strategies():
    return PatternRepository.all_for_prefix("strategy:")


@app.get("/api/components/{component_type}")
def components(component_type: str):
    return ComponentRepository.top_for_type(component_type, limit=20)


@app.get("/api/component-types")
def component_types():
    with get_conn() as conn:
        rows = conn.execute("SELECT DISTINCT component_type FROM email_components").fetchall()
    return [r["component_type"] for r in rows]


@app.get("/api/preferences")
def preferences():
    return PreferenceRepository.all()


@app.get("/api/semantic-statements")
def semantic_statements():
    return {"statements": SemanticMemory().derive_statements(min_samples=2)}


@app.get("/api/experiences")
def experiences(limit: int = 30):
    return ExperienceRepository.recent(limit=limit)


@app.get("/api/quality-trend")
def quality_trend(limit: int = 50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, quality_score, created_at, strategy FROM emails ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return list(reversed(rows_to_dicts(rows)))


@app.get("/api/pending-review")
def pending_review():
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT e.*, l.officer, l.company, l.email as lead_email, l.location
               FROM emails e JOIN leads l ON e.lead_id = l.id
               WHERE e.approved=0 AND e.sent=0
               ORDER BY e.id DESC"""
        ).fetchall()
    out = []
    for r in rows_to_dicts(rows):
        r["analyzer_report"] = loads(r.pop("analyzer_report_json"), {})
        r["components"] = loads(r.pop("components_json"), {})
        out.append(r)
    return out


@app.post("/api/emails/{email_id}/feedback")
def submit_feedback(email_id: int, rating: int = None, action: str = "approve",
                     comment: str = "", replied: bool = False):
    email = EmailRepository.get(email_id)
    if not email:
        raise HTTPException(404, "email not found")
    FeedbackRepository.create(email_id, rating, action, comment, replied)
    if action == "approve":
        EmailRepository.approve(email_id)
    return {"status": "recorded"}


# Serve the static dashboard HTML at /
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
