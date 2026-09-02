"""
Agent: the core loop.

PERCEIVE -> UNDERSTAND -> RETRIEVE MEMORY -> DECIDE -> PLAN -> EXECUTE ->
OBSERVE RESULT -> EVALUATE -> LEARN -> UPDATE MEMORY -> NEXT TASK

Every method below corresponds to one stage. Nothing here is a call into
an external agent framework — this class *is* the agent architecture.
"""

import os

from app.agent.state import AgentState
from app.agent.decision_engine import DecisionEngine
from app.agent.planner import Planner
from app.agent.executor import Executor, StepFailure
from app.agent.evaluator import Evaluator

from app.memory.short_term import ShortTermMemory
from app.memory.retrieval import MemoryRetrieval
from app.memory.long_term import LongTermMemory

from app.learning.learning_engine import LearningEngine
from app.learning.experience import Experience

from app.email.generator import EmailGenerator
from app.email.validator import EmailValidator

from app.tools.base import ToolRegistry
from app.tools.database import DatabaseTool
from app.tools.gmail import GmailTool

from app.database.database import get_conn, now
from app.database.repository import LeadRepository, EmailRepository, ReplyRepository

from app.email.reply_analyzer import ReplyAnalyzer
from app.email.reply_matcher import ReplyMatcher


class Agent:
    def __init__(self, sender_info, dry_run=None, nlp_provider=None):
        self.sender_info = sender_info

        # Safe default:
        # If EMAIL_DRY_RUN is not explicitly configured, the agent will NOT
        # send real emails.
        self.dry_run = (
            os.environ.get("EMAIL_DRY_RUN", "true").lower() == "true"
            if dry_run is None
            else dry_run
        )

        # -------------------------
        # MEMORY
        # -------------------------
        self.stm = ShortTermMemory()
        self.retrieval = MemoryRetrieval()
        self.long_term = LongTermMemory()

        # -------------------------
        # AGENT REASONING
        # -------------------------
        self.decision_engine = DecisionEngine()
        self.planner = Planner()
        self.executor = Executor()
        self.evaluator = Evaluator()

        # -------------------------
        # LEARNING
        # -------------------------
        self.learning_engine = LearningEngine()

        # -------------------------
        # EMAIL
        # -------------------------
        self.generator = EmailGenerator(nlp_provider=nlp_provider)
        self.validator = EmailValidator()

        # -------------------------
        # REPLY INTELLIGENCE (Phase 1)
        # -------------------------
        self.reply_analyzer = ReplyAnalyzer()
        self.reply_matcher = ReplyMatcher()

        # -------------------------
        # TOOLS
        # -------------------------
        self.tools = ToolRegistry()
        self.tools.register(DatabaseTool())

        # GmailTool itself also receives the dry-run state.
        self.tools.register(
            GmailTool(dry_run=self.dry_run)
        )

        # Used to preserve the complete decision history for learning/debugging.
        self.last_decision_trace = []

    # ============================================================
    # PERCEIVE
    # ============================================================

    def perceive(self, raw_lead: dict):
        self.stm.reset()

        lead_row = self.long_term.record_lead(raw_lead)

        self.stm.set("current_lead", lead_row)

        return lead_row

    # ============================================================
    # UNDERSTAND / RETRIEVE MEMORY
    # ============================================================

    def understand_and_retrieve(self, lead: dict):
        context = self.retrieval.retrieve_context(lead)

        self.stm.set("memory_context", context)

        return context

    # ============================================================
    # DECIDE
    # ============================================================

    def decide(self, lead: dict, memory_context: dict):
        trace = []

        # Decide whether the lead should be contacted.
        lead_decision = self.decision_engine.decide_on_lead(lead)

        trace.append(lead_decision.to_dict())

        if lead_decision.action != "proceed":
            self.last_decision_trace = trace

            return lead_decision, trace

        # Decide whether retrieved memory is useful.
        memory_decision = self.decision_engine.decide_on_memory(
            memory_context
        )

        trace.append(memory_decision.to_dict())

        self.last_decision_trace = trace

        return lead_decision, trace

    # ============================================================
    # PLAN
    # ============================================================

    def plan(self, goal: str, task_id=None):
        steps = self.planner.build_plan(
            goal,
            task_id=task_id,
        )

        self.stm.set("current_plan", steps)

        return steps

    # ============================================================
    # EXECUTE
    # Generate -> Analyze -> Evaluate -> Decide
    # ============================================================

    def execute_generate_email(self, lead: dict, forced_strategy=None):
        result = self.generator.generate(
            lead,
            self.sender_info,
            forced_strategy=forced_strategy,
        )

        self.stm.set(
            "current_email",
            result,
        )

        return result

    # ============================================================
    # EVALUATE
    # ============================================================

    def evaluate(self, analyzer_report: dict):
        evaluation = self.evaluator.evaluate_email(
            analyzer_report
        )

        self.stm.set(
            "current_evaluation",
            evaluation,
        )

        return evaluation

    # ============================================================
    # DECIDE ON EMAIL
    # ============================================================

    def decide_on_email(
        self,
        analyzer_report,
        attempt=1,
        max_attempts=3,
    ):
        decision = self.decision_engine.decide_on_email(
            analyzer_report,
            attempt,
            max_attempts,
        )

        self.last_decision_trace.append(
            decision.to_dict()
        )

        return decision

    # ============================================================
    # SEND
    # ============================================================

    def send(
        self,
        lead: dict,
        body: str,
        subject: str = None,
    ):
        """
        Send an email through the Gmail tool.

        In dry-run mode:
        - GmailTool simulates the operation.
        - The lead is NOT marked as contacted.
        - No real external email is sent.

        In live mode:
        - The email is actually sent.
        - The lead is marked as contacted only after a successful send.
        """

        subject = (
            subject
            or f"Freight Dispatching Services near "
               f"{lead.get('location', '')}"
        )

        result = self.tools.call(
            "gmail",
            recipient_email=lead["email"],
            subject=subject,
            body=body,
        )

        # IMPORTANT:
        # A dry run must never modify real contact state.
        if (
            not self.dry_run
            and result.get("status") == "sent"
        ):
            LeadRepository.mark_contacted(
                lead["id"]
            )

        return result

    def _record_sent_message_id(self, email_id, send_result):
        """Persist the outgoing Message-ID (Phase 1.3) so a future reply's
        In-Reply-To/References header can be matched deterministically."""
        message_id = send_result.get("message_id")
        if email_id and message_id:
            EmailRepository.set_outgoing_message_id(email_id, message_id)

    # ============================================================
    # LEARN
    # ============================================================

    def learn(
        self,
        lead,
        generated,
        user_action,
        rating=None,
        replied=False,
        comment="",
        user_edited_email=None,
        outcome="sent",
    ):
        experience = Experience(
            lead=lead,
            strategy=generated["strategy"],
            components=generated["components"],
            generated_email=generated["body"],
            analyzer_report=generated["analyzer_report"],
            decision={
                "trace": self.last_decision_trace
            },
            user_action=user_action,
            user_edited_email=user_edited_email,
            rating=rating,
            replied=replied,
            comment=comment,
            outcome=outcome,
        )

        return self.learning_engine.learn(
            experience,
            email_id=generated.get("email_id"),
            component_ids=generated.get("component_ids"),
        )

    # ============================================================
    # PHASE 5.2: APPROVAL vs FEEDBACK are independent states
    # ============================================================

    def approve_email(self, email_id):
        """Mark an email approved for sending. Independent of feedback —
        approving does not imply a rating/comment was given."""
        EmailRepository.approve(email_id)
        return {"email_id": email_id, "approved": True}

    def reject_email(self, email_id, reason=""):
        """Explicitly hold an email back from sending. Distinct from
        negative feedback: a reject with no rating/comment records no
        feedback at all, just a decision not to send."""
        return {"email_id": email_id, "approved": False, "reason": reason}

    def record_feedback(self, lead, generated, rating=None, comment="",
                         user_edited_email=None, replied=False):
        """Record human feedback (rating/comment/edit) and trigger learning.

        This is deliberately separate from approve_email/reject_email:
        a user may approve an email with no feedback, or leave feedback
        without approving it. Feedback always flows into the learning
        engine when present; approval only controls whether SEND happens.
        """
        return self.learn(
            lead, generated,
            user_action="edit" if user_edited_email else "feedback",
            rating=rating, replied=replied, comment=comment,
            user_edited_email=user_edited_email,
            outcome="feedback_recorded",
        )

    # ============================================================
    # PHASE 1/2/6: REPLY INTELLIGENCE + LEARNING FROM REPLIES
    # ============================================================

    def process_reply(self, raw_message: dict):
        """
        Full reply pipeline for one inbound message believed to be a reply
        to outreach we sent:

            store raw reply (idempotent)
              -> match to sent email / lead (explainable, confidence-scored)
              -> analyze intent/sentiment/outcome (explainable, confidence-scored)
              -> gate learning on both confidences (Phase 6 decision policy)
              -> learn (updates strategy/component/pattern scores) if trusted
              -> otherwise queue for human review, never silently guess

        raw_message: {
            "id": mailbox/IMAP id (required, used as idempotency key),
            "message_id": RFC822 Message-ID,
            "in_reply_to": header value,
            "references": header value,
            "from_email": sender address,
            "to": recipient address (our mailbox),
            "subject": subject line,
            "body": raw reply text,
            "date": received date (optional),
        }
        """
        result = {"steps": []}

        mailbox_id = raw_message.get("id")
        if not mailbox_id:
            result["outcome"] = "error"
            result["error"] = "raw_message missing 'id' (mailbox identifier); cannot guarantee idempotency"
            return result

        # ---- 1. Idempotency: never process/learn from the same reply twice ----
        if ReplyRepository.is_learned(mailbox_id):
            result["outcome"] = "already_learned"
            result["steps"].append(("idempotency_check", "already learned, skipped"))
            return result

        # ---- 2. Store raw reply (never destroyed/overwritten) ----
        raw_fields = {
            "message_id": raw_message.get("message_id", ""),
            "in_reply_to": raw_message.get("in_reply_to", ""),
            "references": raw_message.get("references", ""),
            "thread_key": raw_message.get("thread_key", ""),
            "sender_email": (raw_message.get("from_email") or "").lower().strip(),
            "recipient_email": raw_message.get("to", ""),
            "subject": raw_message.get("subject", ""),
            "raw_reply": raw_message.get("body", ""),
            "received_at": raw_message.get("date", now()),
        }

        try:
            reply_row, created = ReplyRepository.create_or_get(mailbox_id, raw_fields)
        except Exception as exc:
            # Phase 6.3: database failure must not crash the agent.
            result["outcome"] = "error"
            result["error"] = f"failed to persist raw reply: {exc}"
            return result

        result["steps"].append(("store_raw_reply", "created" if created else "already stored"))
        result["reply_mailbox_id"] = mailbox_id

        # ---- 3. Match reply -> sent email / lead ----
        try:
            match = self.reply_matcher.match({
                "sender_email": raw_fields["sender_email"],
                "subject": raw_fields["subject"],
                "in_reply_to": raw_fields["in_reply_to"],
                "references": raw_fields["references"],
            })
        except Exception as exc:
            result["outcome"] = "error"
            result["error"] = f"reply matching failed: {exc}"
            return result

        ReplyRepository.set_match(
            mailbox_id, match["lead_id"], match["email_id"], match["method"], match["confidence"],
        )
        result["match"] = match
        result["steps"].append(("match_reply", match["method"]))

        match_decision = self.decision_engine.decide_on_reply_match(match)
        result["match_decision"] = match_decision.to_dict()

        if match_decision.action == "reject_match":
            result["outcome"] = "match_rejected"
            return result

        # ---- 4. Analyze reply content ----
        try:
            analysis = self.reply_analyzer.analyze(raw_fields["raw_reply"], raw_fields["subject"])
        except Exception as exc:
            result["outcome"] = "error"
            result["error"] = f"reply analysis failed: {exc}"
            return result

        ReplyRepository.set_analysis(mailbox_id, analysis)
        result["analysis"] = analysis
        result["steps"].append(("analyze_reply", analysis["intent"]))

        analysis_decision = self.decision_engine.decide_on_reply_analysis(analysis)
        result["analysis_decision"] = analysis_decision.to_dict()

        needs_review = (
            match_decision.action == "require_human_review"
            or analysis_decision.action == "require_human_review"
        )
        if needs_review:
            ReplyRepository.set_requires_review(mailbox_id, True)
            result["outcome"] = "pending_human_review"
            return result

        # ---- 5. Learn from this reply (high-confidence match + analysis) ----
        email = EmailRepository.get(match["email_id"])
        if not email:
            result["outcome"] = "error"
            result["error"] = "matched email_id no longer exists"
            return result

        lead = LeadRepository.get(email["lead_id"])
        if not lead:
            result["outcome"] = "error"
            result["error"] = "matched lead no longer exists"
            return result

        learn_result = self.learn(
            lead=lead,
            generated={
                "strategy": email["strategy"],
                "components": email["components"],
                "body": email["body"],
                "analyzer_report": email["analyzer_report"],
                "component_ids": {},  # component ids for this historical email aren't retained separately
                "email_id": email["id"],
            },
            user_action="reply_received",
            replied=True,
            outcome=analysis["outcome"],
        )

        ReplyRepository.mark_learned(mailbox_id)
        LeadRepository.set_status(lead["id"], "replied")

        result["outcome"] = "learned"
        result["learn_result"] = learn_result
        result["steps"].append(("learn", analysis["outcome"]))
        return result

    # ============================================================
    # FULL AGENT LOOP
    # ============================================================

    def run_for_lead(
        self,
        raw_lead: dict,
        auto_approve=False,
        simulated_feedback=None,
    ):
        """
        Runs the complete:

        PERCEIVE
          ->
        UNDERSTAND
          ->
        RETRIEVE MEMORY
          ->
        DECIDE
          ->
        PLAN
          ->
        GENERATE
          ->
        EVALUATE
          ->
        APPROVE
          ->
        EXECUTE
          ->
        OBSERVE RESULT
          ->
        LEARN

        dry_run=True:
            The complete reasoning/generation/learning pipeline runs,
            but no real email is sent and no real sent/contacted state
            is recorded.

        simulated_feedback:
            Optional dictionary:

            {
                "rating": 5,
                "replied": True,
                "comment": "...",
                "edited_email": "..."
            }

            This is useful for offline demonstrations and testing.
        """

        log = {
            "steps": [],
            "dry_run": self.dry_run,
        }

        # ========================================================
        # 1. PERCEIVE
        # ========================================================

        lead = self.perceive(raw_lead)

        log["steps"].append(
            (
                "perceive",
                lead["email"],
            )
        )

        # ========================================================
        # 2. UNDERSTAND + RETRIEVE MEMORY
        # ========================================================

        memory_context = self.understand_and_retrieve(
            lead
        )

        log["steps"].append(
            (
                "retrieve_memory",
                f"{len(memory_context['similar_episodes'])} "
                f"similar episodes",
            )
        )

        # ========================================================
        # 3. DECIDE ON LEAD
        # ========================================================

        lead_decision, trace = self.decide(
            lead,
            memory_context,
        )

        log["decision"] = lead_decision.to_dict()

        if lead_decision.action != "proceed":
            log["outcome"] = lead_decision.action

            return log

        # ========================================================
        # 4. PLAN
        # ========================================================

        self.plan(
            "Contact new qualified lead."
        )

        log["steps"].append(
            (
                "plan",
                "built",
            )
        )

        # ========================================================
        # 5. GENERATE EMAIL
        # ========================================================

        generated = self.execute_generate_email(
            lead
        )

        log["steps"].append(
            (
                "generate_email",
                generated["strategy"],
            )
        )

        # ========================================================
        # 6. EVALUATE EMAIL
        # ========================================================

        evaluation = self.evaluate(
            generated["analyzer_report"]
        )

        log["evaluation"] = evaluation

        # ========================================================
        # 7. DECIDE WHETHER EMAIL IS ACCEPTABLE
        # ========================================================

        email_decision = self.decide_on_email(
            generated["analyzer_report"]
        )

        log["email_decision"] = (
            email_decision.to_dict()
        )

        # ========================================================
        # 8. SAVE GENERATED EMAIL
        # ========================================================

        email_id = EmailRepository.create(
            lead_id=lead["id"],
            strategy=generated["strategy"],
            components=generated["components"],
            body=generated["body"],
            quality_score=generated["analyzer_report"][
                "quality_score"
            ],
            analyzer_report=generated["analyzer_report"],
        )

        generated["email_id"] = email_id

        # ========================================================
        # 9. HUMAN REVIEW
        # ========================================================

        if email_decision.action == "require_human_review":
            log["outcome"] = (
                "pending_human_review"
            )

            return log

        # ========================================================
        # 10. APPROVAL
        # ========================================================

        approved = (
            auto_approve
            or simulated_feedback is not None
        )

        approval_decision = (
            self.decision_engine.decide_after_approval(
                approved
            )
        )

        log["approval_decision"] = (
            approval_decision.to_dict()
        )

        if approval_decision.action != "send":
            log["outcome"] = (
                "held_for_approval"
            )

            return log

        # ========================================================
        # 11. APPROVE EMAIL IN DATABASE
        # ========================================================

        EmailRepository.approve(
            email_id
        )

        # ========================================================
        # 12. APPLY SIMULATED FEEDBACK
        # ========================================================

        final_body = generated["body"]

        rating = None
        replied = False
        comment = ""
        edited = None

        if simulated_feedback:
            rating = simulated_feedback.get(
                "rating"
            )

            replied = simulated_feedback.get(
                "replied",
                False,
            )

            comment = simulated_feedback.get(
                "comment",
                "",
            )

            edited = simulated_feedback.get(
                "edited_email"
            )

            if edited:
                final_body = edited

                EmailRepository.set_user_edit(
                    email_id,
                    edited,
                )

        # ========================================================
        # 13. EXECUTE SEND
        # ========================================================

        send_result = self.send(
            lead,
            final_body,
        )

        log["send_result"] = send_result

        # ========================================================
        # 14. DETERMINE REAL OUTCOME
        # ========================================================

        if self.dry_run:
            # ----------------------------------------------------
            # DRY RUN
            # ----------------------------------------------------
            #
            # The email was only simulated.
            #
            # DO NOT:
            #   - mark email as sent
            #   - mark lead as contacted
            #
            log["outcome"] = "dry_run"

            learn_outcome = "dry_run"

        else:
            # ----------------------------------------------------
            # LIVE SEND
            # ----------------------------------------------------

            if send_result.get("status") == "sent":
                EmailRepository.mark_sent(
                    email_id
                )
                self._record_sent_message_id(email_id, send_result)

                log["outcome"] = "sent"
                learn_outcome = "sent"

            else:
                # Gmail/tool reported a failure (status: "error" or
                # anything unrecognized) — fail safely, do not raise.
                log["outcome"] = "send_failed"
                log["send_error"] = send_result.get("error", "unknown send failure")
                learn_outcome = "send_failed"

        # ========================================================
        # 15. LEARN
        # ========================================================

        learn_result = self.learn(
            lead,
            generated,
            user_action=(
                "edit"
                if edited
                else "approve"
            ),
            rating=rating,
            replied=replied,
            comment=comment,
            user_edited_email=edited,
            outcome=learn_outcome,
        )

        log["learn_result"] = learn_result

        # IMPORTANT:
        # Do not overwrite the outcome here.
        #
        # For example:
        #   dry_run      -> remains dry_run
        #   sent         -> remains sent
        #   send_failed  -> remains send_failed

        return log
