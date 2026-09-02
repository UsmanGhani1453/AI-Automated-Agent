"""
Thin repository layer. Every module that needs persistence goes through here
instead of writing raw SQL inline, so the schema can change in one place.
"""
from app.database.database import get_conn, now, dumps, loads, row_to_dict, rows_to_dicts


class LeadRepository:
    @staticmethod
    def create(officer, company, fleet_size, location, email, category=None):
        with get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO leads (officer, company, fleet_size, location, email, category, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (officer, company, fleet_size, location, email, category, now()),
            )
            return cur.lastrowid

    @staticmethod
    def get(lead_id):
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
            return row_to_dict(row)

    @staticmethod
    def get_by_email(email):
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM leads WHERE email=?", (email,)).fetchone()
            return row_to_dict(row)

    @staticmethod
    def find_or_create(lead_data):
        existing = LeadRepository.get_by_email(lead_data["email"])
        if existing:
            return existing
        lead_id = LeadRepository.create(
            lead_data.get("officer"), lead_data.get("company"),
            lead_data.get("fleet_size"), lead_data.get("location"),
            lead_data["email"], lead_data.get("category"),
        )
        return LeadRepository.get(lead_id)

    @staticmethod
    def mark_contacted(lead_id):
        with get_conn() as conn:
            conn.execute(
                "UPDATE leads SET status='contacted', last_contacted_at=? WHERE id=?",
                (now(), lead_id),
            )

    @staticmethod
    def set_status(lead_id, status):
        with get_conn() as conn:
            conn.execute("UPDATE leads SET status=? WHERE id=?", (status, lead_id))

    @staticmethod
    def recently_contacted(lead_id, days=14):
        with get_conn() as conn:
            row = conn.execute(
                """SELECT last_contacted_at FROM leads WHERE id=?""", (lead_id,)
            ).fetchone()
            if not row or not row["last_contacted_at"]:
                return False
            from datetime import datetime, timezone
            last = datetime.fromisoformat(row["last_contacted_at"])
            delta = datetime.now(timezone.utc) - last
            return delta.days < days


class SuppressionRepository:
    @staticmethod
    def is_suppressed(email):
        with get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM suppression_list WHERE email=?", (email,)
            ).fetchone()
            return row is not None

    @staticmethod
    def add(email, reason=""):
        with get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO suppression_list (email, reason, created_at) VALUES (?, ?, ?)",
                (email, reason, now()),
            )


class InboxMessageRepository:
    @staticmethod
    def upsert(message, analysis=None):
        analysis = analysis or {}
        mailbox_id = str(message["id"])
        thread_key = message.get("thread_key") or message.get("message_id") or mailbox_id
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO inbox_messages
                   (mailbox_id, message_id, thread_key, from_name, from_email,
                    to_header, subject, sent_at, body, category, intent, urgency,
                    requested_action, should_reply, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(mailbox_id) DO UPDATE SET
                    message_id=excluded.message_id, thread_key=excluded.thread_key,
                    from_name=excluded.from_name, from_email=excluded.from_email,
                    to_header=excluded.to_header, subject=excluded.subject,
                    sent_at=excluded.sent_at, body=excluded.body,
                    category=excluded.category, intent=excluded.intent,
                    urgency=excluded.urgency, requested_action=excluded.requested_action,
                    should_reply=excluded.should_reply, updated_at=excluded.updated_at""",
                (
                    mailbox_id, message.get("message_id", ""), thread_key,
                    message.get("from_name", ""), message.get("from_email", ""),
                    message.get("to", ""), message.get("subject", ""),
                    message.get("date", ""), message.get("body", ""),
                    analysis.get("category", ""), analysis.get("intent", ""),
                    analysis.get("urgency", ""), analysis.get("requested_action", ""),
                    int(bool(analysis.get("should_reply"))), now(), now(),
                ),
            )
            row = conn.execute(
                "SELECT * FROM inbox_messages WHERE mailbox_id=?", (mailbox_id,)
            ).fetchone()
            return row_to_dict(row)

    @staticmethod
    def mark_processed(mailbox_id, draft_email_id=None):
        with get_conn() as conn:
            conn.execute(
                """UPDATE inbox_messages
                   SET processed=1, draft_email_id=?, updated_at=?
                   WHERE mailbox_id=?""",
                (draft_email_id, now(), str(mailbox_id)),
            )

    @staticmethod
    def by_thread(thread_key, limit=20):
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM inbox_messages WHERE thread_key=? ORDER BY id ASC LIMIT ?",
                (thread_key, limit),
            ).fetchall()
            return rows_to_dicts(rows)

    @staticmethod
    def recent_for_sender(from_email, limit=20):
        with get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM inbox_messages
                   WHERE lower(from_email)=lower(?) ORDER BY id DESC LIMIT ?""",
                (from_email, limit),
            ).fetchall()
            return rows_to_dicts(rows)


class ConversationProfileRepository:
    @staticmethod
    def upsert(thread_key, participant_email, participant_name, subject, message_count, summary):
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO conversation_profiles
                   (thread_key, participant_email, participant_name, subject,
                    last_message_at, message_count, summary_json, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(thread_key) DO UPDATE SET
                    participant_email=excluded.participant_email,
                    participant_name=excluded.participant_name,
                    subject=excluded.subject,
                    last_message_at=excluded.last_message_at,
                    message_count=excluded.message_count,
                    summary_json=excluded.summary_json,
                    updated_at=excluded.updated_at""",
                (thread_key, participant_email, participant_name, subject,
                 now(), message_count, dumps(summary), now()),
            )
            row = conn.execute(
                "SELECT * FROM conversation_profiles WHERE thread_key=?", (thread_key,)
            ).fetchone()
            result = row_to_dict(row)
            if result:
                result["summary"] = loads(result.pop("summary_json"), {})
            return result

    @staticmethod
    def get(thread_key):
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM conversation_profiles WHERE thread_key=?", (thread_key,)
            ).fetchone()
            result = row_to_dict(row)
            if result:
                result["summary"] = loads(result.pop("summary_json"), {})
            return result


class EmailRepository:
    @staticmethod
    def create(lead_id, strategy, components, body, quality_score, analyzer_report, version=1):
        with get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO emails
                   (lead_id, strategy, components_json, body, quality_score,
                    analyzer_report_json, version, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (lead_id, strategy, dumps(components), body, quality_score,
                 dumps(analyzer_report), version, now()),
            )
            return cur.lastrowid

    @staticmethod
    def get(email_id):
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM emails WHERE id=?", (email_id,)).fetchone()
            d = row_to_dict(row)
            if d:
                d["components"] = loads(d.pop("components_json"), {})
                d["analyzer_report"] = loads(d.pop("analyzer_report_json"), {})
            return d

    @staticmethod
    def set_user_edit(email_id, edited_body):
        with get_conn() as conn:
            conn.execute("UPDATE emails SET user_edited_body=? WHERE id=?", (edited_body, email_id))

    @staticmethod
    def approve(email_id):
        with get_conn() as conn:
            conn.execute("UPDATE emails SET approved=1 WHERE id=?", (email_id,))

    @staticmethod
    def mark_sent(email_id):
        with get_conn() as conn:
            conn.execute("UPDATE emails SET sent=1, sent_at=? WHERE id=?", (now(), email_id))

    @staticmethod
    def recent_for_lead(lead_id, limit=5):
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM emails WHERE lead_id=? ORDER BY id DESC LIMIT ?",
                (lead_id, limit),
            ).fetchall()
            return rows_to_dicts(rows)

    @staticmethod
    def set_outgoing_message_id(email_id, message_id):
        with get_conn() as conn:
            conn.execute(
                "UPDATE emails SET outgoing_message_id=? WHERE id=?",
                (message_id, email_id),
            )



class ComponentRepository:
    """Stores individual email building blocks (greeting/opening/cta/etc) and their learned scores."""

    @staticmethod
    def upsert(component_type, text):
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM email_components WHERE component_type=? AND text=?",
                (component_type, text),
            ).fetchone()
            if row:
                return row_to_dict(row)
            cur = conn.execute(
                """INSERT INTO email_components (component_type, text, created_at)
                   VALUES (?, ?, ?)""",
                (component_type, text, now()),
            )
            return {
                "id": cur.lastrowid, "component_type": component_type, "text": text,
                "positive_score": 0.5, "uses": 0, "positive_count": 0,
                "negative_count": 0, "reply_count": 0,
            }

    @staticmethod
    def top_for_type(component_type, limit=5):
        with get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM email_components WHERE component_type=?
                   ORDER BY positive_score DESC, uses DESC LIMIT ?""",
                (component_type, limit),
            ).fetchall()
            return rows_to_dicts(rows)

    @staticmethod
    def record_usage(component_id):
        with get_conn() as conn:
            conn.execute("UPDATE email_components SET uses = uses + 1 WHERE id=?", (component_id,))

    @staticmethod
    def apply_feedback(component_id, rating, replied=False):
        """Update a component's running score using a simple explainable formula.

        score = (positive_count + 2*reply_count) / (positive_count + negative_count + 2*reply_count + smoothing)
        This is Laplace-smoothed so a component with few samples doesn't swing wildly,
        and a reply (strong positive signal) counts double.
        """
        with get_conn() as conn:
            row = conn.execute("SELECT * FROM email_components WHERE id=?", (component_id,)).fetchone()
            if not row:
                return
            pos = row["positive_count"] + (1 if rating >= 4 else 0)
            neg = row["negative_count"] + (1 if rating <= 2 else 0)
            replies = row["reply_count"] + (1 if replied else 0)
            smoothing = 2.0
            score = (pos + 2 * replies + smoothing * 0.5) / (pos + neg + 2 * replies + smoothing)
            conn.execute(
                """UPDATE email_components
                   SET positive_count=?, negative_count=?, reply_count=?, positive_score=?
                   WHERE id=?""",
                (pos, neg, replies, score, component_id),
            )


class ReplyRepository:
    """Phase 1: raw + structured recipient replies. Idempotent on mailbox_id
    so the same inbox message can never be learned from twice."""

    @staticmethod
    def get_by_mailbox_id(mailbox_id):
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM replies WHERE mailbox_id=?", (str(mailbox_id),)
            ).fetchone()
            return row_to_dict(row)

    @staticmethod
    def create_or_get(mailbox_id, raw_fields):
        """Insert the raw reply if it's new; otherwise return the existing
        row untouched (idempotency — never overwrite a processed reply)."""
        existing = ReplyRepository.get_by_mailbox_id(mailbox_id)
        if existing:
            return existing, False
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO replies
                   (mailbox_id, message_id, in_reply_to, references_header, thread_key,
                    sender_email, recipient_email, subject, raw_reply, received_at,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(mailbox_id), raw_fields.get("message_id", ""),
                    raw_fields.get("in_reply_to", ""), raw_fields.get("references", ""),
                    raw_fields.get("thread_key", ""), raw_fields.get("sender_email", ""),
                    raw_fields.get("recipient_email", ""), raw_fields.get("subject", ""),
                    raw_fields.get("raw_reply", ""), raw_fields.get("received_at", now()),
                    now(), now(),
                ),
            )
        return ReplyRepository.get_by_mailbox_id(mailbox_id), True

    @staticmethod
    def set_match(mailbox_id, lead_id, email_id, method, confidence):
        with get_conn() as conn:
            conn.execute(
                """UPDATE replies
                   SET matched_lead_id=?, matched_email_id=?, match_method=?,
                       match_confidence=?, updated_at=?
                   WHERE mailbox_id=?""",
                (lead_id, email_id, method, confidence, now(), str(mailbox_id)),
            )

    @staticmethod
    def set_analysis(mailbox_id, analysis):
        with get_conn() as conn:
            conn.execute(
                """UPDATE replies
                   SET intent=?, sentiment=?, interest_level=?, objection=?, question=?,
                       requested_action=?, urgency=?, topic=?, outcome=?,
                       analysis_confidence=?, analysis_json=?, updated_at=?
                   WHERE mailbox_id=?""",
                (
                    analysis["intent"], analysis["sentiment"], analysis["interest_level"],
                    analysis["objection"], analysis["question"], analysis["requested_action"],
                    analysis["urgency"], analysis["topic"], analysis["outcome"],
                    analysis["confidence"], dumps(analysis), now(), str(mailbox_id),
                ),
            )

    @staticmethod
    def set_requires_review(mailbox_id, requires_review):
        with get_conn() as conn:
            conn.execute(
                "UPDATE replies SET requires_review=?, updated_at=? WHERE mailbox_id=?",
                (int(bool(requires_review)), now(), str(mailbox_id)),
            )

    @staticmethod
    def mark_learned(mailbox_id):
        with get_conn() as conn:
            conn.execute(
                "UPDATE replies SET learned=1, updated_at=? WHERE mailbox_id=?",
                (now(), str(mailbox_id)),
            )

    @staticmethod
    def is_learned(mailbox_id):
        row = ReplyRepository.get_by_mailbox_id(mailbox_id)
        return bool(row and row.get("learned"))

    @staticmethod
    def for_email(email_id):
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM replies WHERE matched_email_id=? ORDER BY id ASC", (email_id,)
            ).fetchall()
            return rows_to_dicts(rows)

    @staticmethod
    def pending_review(limit=20):
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM replies WHERE requires_review=1 AND learned=0 ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return rows_to_dicts(rows)


class FeedbackRepository:
    @staticmethod
    def create(email_id, rating, action, comment="", replied=False):
        with get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO feedback (email_id, rating, action, comment, replied, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (email_id, rating, action, comment, int(replied), now()),
            )
            return cur.lastrowid


class ExperienceRepository:
    @staticmethod
    def create(lead_id, email_id, context, decision, evaluation, outcome, feedback):
        with get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO experiences
                   (lead_id, email_id, context_json, decision_json, evaluation_json,
                    outcome, feedback_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (lead_id, email_id, dumps(context), dumps(decision), dumps(evaluation),
                 outcome, dumps(feedback), now()),
            )
            return cur.lastrowid

    @staticmethod
    def recent(limit=50):
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM experiences ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            out = []
            for r in rows_to_dicts(rows):
                r["context"] = loads(r.pop("context_json"), {})
                r["decision"] = loads(r.pop("decision_json"), {})
                r["evaluation"] = loads(r.pop("evaluation_json"), {})
                r["feedback"] = loads(r.pop("feedback_json"), {})
                out.append(r)
            return out


class PatternRepository:
    @staticmethod
    def get(pattern_key):
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM learned_patterns WHERE pattern_key=?", (pattern_key,)
            ).fetchone()
            return row_to_dict(row)

    @staticmethod
    def get_or_create(pattern_key, description=""):
        existing = PatternRepository.get(pattern_key)
        if existing:
            return existing
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO learned_patterns (pattern_key, description, updated_at)
                   VALUES (?, ?, ?)""",
                (pattern_key, description, now()),
            )
        return PatternRepository.get(pattern_key)

    @staticmethod
    def update_score(pattern_key, rating=None, replied=False):
        pat = PatternRepository.get_or_create(pattern_key)
        pos = pat["positive_feedback"] + (1 if rating is not None and rating >= 4 else 0)
        neg = pat["negative_feedback"] + (1 if rating is not None and rating <= 2 else 0)
        replies = pat["reply_count"] + (1 if replied else 0)
        samples = pat["sample_count"] + 1
        smoothing = 2.0
        score = (pos + 2 * replies + smoothing * 0.5) / (pos + neg + 2 * replies + smoothing)
        with get_conn() as conn:
            conn.execute(
                """UPDATE learned_patterns
                   SET positive_feedback=?, negative_feedback=?, reply_count=?,
                       sample_count=?, score=?, updated_at=?
                   WHERE pattern_key=?""",
                (pos, neg, replies, samples, score, now(), pattern_key),
            )
        return PatternRepository.get(pattern_key)

    @staticmethod
    def all_for_prefix(prefix):
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM learned_patterns WHERE pattern_key LIKE ? ORDER BY score DESC",
                (f"{prefix}%",),
            ).fetchall()
            return rows_to_dicts(rows)


class PreferenceRepository:
    @staticmethod
    def upsert(preference_key, description, confidence_delta):
        with get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM learned_preferences WHERE preference_key=?", (preference_key,)
            ).fetchone()
            if row:
                new_conf = max(0.0, min(1.0, row["confidence"] + confidence_delta))
                conn.execute(
                    """UPDATE learned_preferences
                       SET confidence=?, evidence_count=evidence_count+1, updated_at=?
                       WHERE preference_key=?""",
                    (new_conf, now(), preference_key),
                )
            else:
                conn.execute(
                    """INSERT INTO learned_preferences
                       (preference_key, description, confidence, evidence_count, updated_at)
                       VALUES (?, ?, ?, 1, ?)""",
                    (preference_key, description, max(0.0, confidence_delta), now()),
                )

    @staticmethod
    def all():
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM learned_preferences ORDER BY confidence DESC"
            ).fetchall()
            return rows_to_dicts(rows)


class ToolCallRepository:
    @staticmethod
    def log(tool_name, parameters, result, status, duration_ms):
        with get_conn() as conn:
            conn.execute(
                """INSERT INTO tool_calls (tool_name, parameters_json, result_json, status, duration_ms, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (tool_name, dumps(parameters), dumps(result), status, duration_ms, now()),
            )


class MetricsRepository:
    @staticmethod
    def record(name, value, context=None):
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO metrics (metric_name, metric_value, context_json, created_at) VALUES (?, ?, ?, ?)",
                (name, value, dumps(context or {}), now()),
            )

    @staticmethod
    def history(name, limit=50):
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM metrics WHERE metric_name=? ORDER BY id DESC LIMIT ?",
                (name, limit),
            ).fetchall()
            return rows_to_dicts(rows)
