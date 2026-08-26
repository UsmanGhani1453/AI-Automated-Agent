"""
Agent: the core loop.

PERCEIVE -> UNDERSTAND -> RETRIEVE MEMORY -> DECIDE -> PLAN -> EXECUTE ->
OBSERVE RESULT -> EVALUATE -> LEARN -> UPDATE MEMORY -> NEXT TASK

Every method below corresponds to one stage. Nothing here is a call into
an external agent framework — this class *is* the agent architecture.
"""
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
from app.database.repository import LeadRepository, EmailRepository


class Agent:
    def __init__(self, sender_info, dry_run=True, nlp_provider=None):
        self.sender_info = sender_info
        self.dry_run = dry_run

        self.stm = ShortTermMemory()
        self.retrieval = MemoryRetrieval()
        self.long_term = LongTermMemory()
        self.decision_engine = DecisionEngine()
        self.planner = Planner()
        self.executor = Executor()
        self.evaluator = Evaluator()
        self.learning_engine = LearningEngine()
        self.generator = EmailGenerator(nlp_provider=nlp_provider)
        self.validator = EmailValidator()

        self.tools = ToolRegistry()
        self.tools.register(DatabaseTool())
        self.tools.register(GmailTool(dry_run=dry_run))

        self.last_decision_trace = []

    # ---- PERCEIVE ----
    def perceive(self, raw_lead: dict):
        self.stm.reset()
        lead_row = self.long_term.record_lead(raw_lead)
        self.stm.set("current_lead", lead_row)
        return lead_row

    # ---- UNDERSTAND / RETRIEVE MEMORY ----
    def understand_and_retrieve(self, lead: dict):
        context = self.retrieval.retrieve_context(lead)
        self.stm.set("memory_context", context)
        return context

    # ---- DECIDE ----
    def decide(self, lead: dict, memory_context: dict):
        trace = []
        lead_decision = self.decision_engine.decide_on_lead(lead)
        trace.append(lead_decision.to_dict())
        if lead_decision.action != "proceed":
            self.last_decision_trace = trace
            return lead_decision, trace

        memory_decision = self.decision_engine.decide_on_memory(memory_context)
        trace.append(memory_decision.to_dict())

        self.last_decision_trace = trace
        return lead_decision, trace

    # ---- PLAN ----
    def plan(self, goal: str, task_id=None):
        steps = self.planner.build_plan(goal, task_id=task_id)
        self.stm.set("current_plan", steps)
        return steps

    # ---- EXECUTE (generate -> analyze -> accept/regenerate loop) ----
    def execute_generate_email(self, lead: dict):
        result = self.generator.generate(lead, self.sender_info)
        self.stm.set("current_email", result)
        return result

    # ---- EVALUATE ----
    def evaluate(self, analyzer_report: dict):
        evaluation = self.evaluator.evaluate_email(analyzer_report)
        self.stm.set("current_evaluation", evaluation)
        return evaluation

    # ---- decide on regenerate/approve, given evaluation ----
    def decide_on_email(self, analyzer_report, attempt=1, max_attempts=3):
        decision = self.decision_engine.decide_on_email(analyzer_report, attempt, max_attempts)
        self.last_decision_trace.append(decision.to_dict())
        return decision

    def send(self, lead: dict, body: str, subject: str = None):
        subject = subject or f"Freight Dispatching Services near {lead.get('location', '')}"
        result = self.tools.call("gmail", recipient_email=lead["email"], subject=subject, body=body)
        if result.get("status") in ("sent", "dry_run"):
            LeadRepository.mark_contacted(lead["id"])
        return result

    # ---- LEARN ----
    def learn(self, lead, generated, user_action, rating=None, replied=False,
              comment="", user_edited_email=None, outcome="sent"):
        experience = Experience(
            lead=lead,
            strategy=generated["strategy"],
            components=generated["components"],
            generated_email=generated["body"],
            analyzer_report=generated["analyzer_report"],
            decision={"trace": self.last_decision_trace},
            user_action=user_action,
            user_edited_email=user_edited_email,
            rating=rating,
            replied=replied,
            comment=comment,
            outcome=outcome,
        )
        return self.learning_engine.learn(
            experience, email_id=generated.get("email_id"), component_ids=generated.get("component_ids")
        )

    # ---- Full loop for one lead, used by main.py / scheduler ----
    def run_for_lead(self, raw_lead: dict, auto_approve=False, simulated_feedback=None):
        """
        Runs the whole PERCEIVE..LEARN cycle for a single lead.
        simulated_feedback: optional dict {rating, replied, edited_email} for
        offline demonstration/testing without a human in the loop.
        """
        log = {"steps": []}

        lead = self.perceive(raw_lead)
        log["steps"].append(("perceive", lead["email"]))

        memory_context = self.understand_and_retrieve(lead)
        log["steps"].append(("retrieve_memory", f"{len(memory_context['similar_episodes'])} similar episodes"))

        lead_decision, trace = self.decide(lead, memory_context)
        log["decision"] = lead_decision.to_dict()
        if lead_decision.action != "proceed":
            log["outcome"] = lead_decision.action
            return log

        self.plan("Contact new qualified lead.")
        log["steps"].append(("plan", "built"))

        generated = self.execute_generate_email(lead)
        log["steps"].append(("generate_email", generated["strategy"]))

        evaluation = self.evaluate(generated["analyzer_report"])
        log["evaluation"] = evaluation

        email_decision = self.decide_on_email(generated["analyzer_report"])
        log["email_decision"] = email_decision.to_dict()

        email_id = EmailRepository.create(
            lead_id=lead["id"], strategy=generated["strategy"],
            components=generated["components"], body=generated["body"],
            quality_score=generated["analyzer_report"]["quality_score"],
            analyzer_report=generated["analyzer_report"],
        )
        generated["email_id"] = email_id

        if email_decision.action == "require_human_review":
            log["outcome"] = "pending_human_review"
            return log

        approved = auto_approve or (simulated_feedback is not None)
        approval_decision = self.decision_engine.decide_after_approval(approved)
        log["approval_decision"] = approval_decision.to_dict()

        if approval_decision.action != "send":
            log["outcome"] = "held_for_approval"
            return log

        EmailRepository.approve(email_id)

        final_body = generated["body"]
        rating, replied, comment, edited = None, False, "", None
        if simulated_feedback:
            rating = simulated_feedback.get("rating")
            replied = simulated_feedback.get("replied", False)
            comment = simulated_feedback.get("comment", "")
            edited = simulated_feedback.get("edited_email")
            if edited:
                final_body = edited
                EmailRepository.set_user_edit(email_id, edited)

        send_result = self.send(lead, final_body)
        EmailRepository.mark_sent(email_id)
        log["send_result"] = send_result

        learn_result = self.learn(
            lead, generated, user_action="edit" if edited else "approve",
            rating=rating, replied=replied, comment=comment,
            user_edited_email=edited, outcome="sent",
        )
        log["learn_result"] = learn_result
        log["outcome"] = "sent"
        return log
