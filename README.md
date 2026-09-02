# AI Automated Agent — Self-Learning Email Agent (rebuilt from first principles)

## ⚠️ Security — do this before anything else

The audit of the original repo found:
- A live Gmail address and 16-character Gmail App Password hardcoded in plaintext in `core/outreach_pipeline.py`.
- A saved Playwright session (`playwright_auth.json`, committed at both the repo root and in `/auth`) containing live login cookies for the TruckerDB account.

**Treat both as compromised.** Rotate the Gmail App Password in your Google Account settings, re-authenticate TruckerDB to generate a fresh session file, and make sure the old commits are scrubbed from git history if this repo is or was ever public (`git filter-repo` or BFG Repo-Cleaner — a force-push alone doesn't remove them from anyone who already cloned it).

This rebuild reads credentials only from environment variables (`.env`, gitignored) — see `.env.example`.

---

## What this is

**Agent = this codebase.** The perception loop, state, memory, decision-making, planning, learning, and email intelligence are all implemented here in plain Python + SQLite. No LangChain, LangGraph, CrewAI, AutoGen, or OpenAI Agents SDK is used or required.

**NLP/ML model = optional tool.** `app/nlp/base.py` defines an `NLPProvider` interface. `app/nlp/optional_provider.py` gives one implementation (calls a local Ollama model) but the agent runs completely fine with no provider configured — `EmailGenerator`/`Composer` build emails from scored template components, not from a model call. You can swap in a rule-based provider, a small local classifier, or a model you train yourself later, and nothing in `app/agent`, `app/memory`, or `app/learning` needs to change.

## The loop

```
PERCEIVE -> UNDERSTAND -> RETRIEVE MEMORY -> DECIDE -> PLAN -> EXECUTE
   -> OBSERVE RESULT -> EVALUATE -> LEARN -> UPDATE MEMORY -> NEXT TASK
```

Implemented in `app/agent/agent.py::Agent`. Each stage is its own method; `run_for_lead()` chains them for one lead end to end.

## Architecture

```
app/
├── agent/            # Agent core: state, decision engine, planner, executor, evaluator
├── memory/            # short_term, long_term, episodic, semantic, retrieval — all SQLite-backed
├── learning/           # learning_engine, pattern_scorer, preference_learner, experience
├── email/             # analyzer, composer, generator, validator, sender
├── tools/             # Tool base class + registry, database/gmail/scraper tools
├── nlp/               # NLPProvider interface + optional local implementation
├── database/          # schema + repository (all persistence goes through here)
└── api/               # (placeholder for FastAPI routes — not yet built, see Roadmap)
```

### Decision engine (`app/agent/decision_engine.py`)
Deterministic, explainable rules — reject invalid leads, respect suppression list, skip recently-contacted leads, regenerate low-quality emails up to a cap, then require human review. Every `Decision` carries an `action` and a `reason` string, logged to `actions`/`agent_state` tables.

### Memory (`app/memory/`)
- **Short-term**: in-process scratchpad for the current lead/task (not persisted).
- **Long-term**: leads, emails, feedback, experiences — via the repository layer.
- **Episodic**: complete Lead→Email→Evaluation→Outcome→Feedback chains, retrieved by lightweight tag overlap (category/location/fleet-size buckets) — no vector DB needed at this scale.
- **Semantic**: statements *derived* at query time from `learned_patterns`/`learned_preferences` tables — never hardcoded conclusions.

### Learning engine (`app/learning/`)
This is real online learning, not "print a message":
- `pattern_scorer.py` — Laplace-smoothed scoring: `score = (positive + 2×replies + 1) / (positive + negative + 2×replies + 2)`. Starts at 0.5 (neutral prior), needs several consistent samples to move — explainable and auditable at every step.
- `preference_learner.py` — diffs the AI draft against the user's edited version (length delta, greeting removed, exclamation marks removed, aggressive CTA phrases removed) and records confidence-weighted preferences.
- `learning_engine.py` — orchestrates: persist experience → persist episode → update strategy/component scores → extract edit-based preferences.

These scores feed directly back into `EmailGenerator.select_strategy()` (weighted toward the best-scoring strategy, with forced exploration for under-sampled ones) and `Composer.generate_candidates()` (weighted random selection over component scores) — so behavior actually changes, verifiably, as feedback accumulates.

### Email intelligence (`app/email/`)
- `analyzer.py` — pure rule/statistics: word/sentence counts, an approximate Flesch readability score, personalization/company/location mention detection, CTA presence, spam-marker detection, placeholder detection, repeated-phrase detection, a weighted composite `quality_score`.
- `composer.py` — builds candidate emails from six independently-scored component slots (greeting/opening/value_prop/service/cta/signature), evolutionary-lite: generates several candidates per attempt, analyzer picks the best.
- `generator.py` — the full pipeline: select strategy → compose candidates → analyze → accept or regenerate (up to 3 attempts) → hand off to decision engine.
- `validator.py` / `sender.py` — pre-send sanity checks and the SMTP wrapper (credentials from env only, `dry_run=True` by default).

### Explainability
Every strategy/pattern score can be explained: `LearningEngine.explain_strategy_choice("VALUE_FIRST")` returns something like:
```
strategy:VALUE_FIRST: score=0.75 from 3 samples (2 positive, 0 negative, 0 replies).
```
`SemanticMemory.derive_statements()` renders the current learned state as plain-English sentences, generated fresh from the tables every time — never hardcoded.

## Preserved from the original repo, refactored into tools
- Playwright scraper → `app/tools/scraper.py` (`LeadScraperTool`) — same selectors, credentials/paths now from env, not committed.
- Gmail sending → `app/tools/gmail.py` + `app/email/sender.py` — credentials from env, `dry_run` flag so you can exercise the whole agent safely before connecting a real mailbox.
- The example emails in `examples.json` were style references for the old Ollama prompt; they're a good source of a few more seed `email_components` rows if you want to hand-add them to `composer.py`'s `SEED_COMPONENTS`.

## Try it

```bash
pip install -r requirements.txt --break-system-packages
python main.py --rounds 4
```

This runs the agent against 6 demo leads with **simulated, strategy-correlated feedback** (no real email sent — `dry_run=True` by default) so you can watch `learned_patterns` scores diverge across rounds and see the derived semantic-memory statements at the end. Use `python main.py --live` (after filling in `.env`) to actually send.

## Reply intelligence (Phase 1)

`app/email/reply_analyzer.py` turns a raw recipient reply into structured
data — `intent`, `sentiment`, `interest_level`, `objection`, `question`,
`requested_action`, `urgency`, `topic`, `outcome` — using the same
deterministic, regex-based philosophy as the rest of the agent (no black-box
classifier). Every field carries a `confidence` score derived from how
specific the matched pattern was.

`app/email/reply_matcher.py` matches an inbound reply back to the sent email
(and lead) that caused it, trying strategies in order of reliability:
1. `In-Reply-To` / `References` header → outgoing `Message-ID` (needs
   `GmailTool`/`EmailSender` to have recorded the Message-ID at send time —
   it now does, via `emails.outgoing_message_id`)
2. sender address → known lead → most recently sent email to that lead
3. falls through to "no match" rather than guessing when neither signal is present

Raw replies are stored once, permanently, in the `replies` table — the
original text is never mutated, only the matching/analysis columns are
filled in alongside it. Reprocessing the same inbox message (same
`mailbox_id`) is a no-op (`ReplyRepository.is_learned` / idempotent insert).

## Learning from replies (Phase 2) + confidence-gated learning (Phase 6)

`Agent.process_reply(raw_message)` runs the full pipeline: store raw reply →
match → analyze → **gate on confidence** → learn. `DecisionEngine.decide_on_reply_match`
and `decide_on_reply_analysis` implement the policy:

- high match + analysis confidence → `auto_learn`: the reply becomes a real
  `Experience` (via `Agent.learn`) with `replied=True` and the analyzed
  `outcome`, updating strategy/component/pattern scores exactly like a
  rating would.
- medium confidence → `require_human_review`: the reply is stored and
  flagged (`replies.requires_review=1`) but **not** learned from until a
  human confirms it (`ReplyRepository.pending_review()`).
- low/no match → `reject_match`: stored for audit, never learned from.

This closes the loop the spec asked for: *what the agent learns from
interaction N measurably changes interaction N+1* — see
`tests/test_reply_learning_integration.py::test_end_to_end_behavior_changes_from_reply`,
which forces one strategy through several positive-reply interactions and
proves both the strategy's learned score *and* future `select_strategy()`
calls shift in response, compared to an untouched competing strategy.

## Approval vs. feedback (Phase 5.2)

These are independent states, not the same thing:
- `Agent.approve_email(email_id)` / `reject_email(email_id)` — controls
  whether SEND happens. Carries no rating or comment.
- `Agent.record_feedback(lead, generated, rating=..., comment=..., user_edited_email=...)`
  — feeds the learning engine. Can be called with or without approval ever
  having happened.

## Safety (Phase 6)

- Every reply-pipeline decision carries an explicit confidence number and a
  human-readable reason (`Decision.reason`), so "why did the agent learn
  (or not learn) from this reply?" always has a concrete answer.
- `EmailSender.send()` and `Agent.process_reply()` fail safely: SMTP/IMAP/DB
  errors return a structured `{"status": "error", "error": "..."}` result
  instead of raising and crashing the loop; `run_for_lead`/`process_reply`
  record the failure and stop rather than guessing.
- Idempotency: `replies.mailbox_id` is unique, and `replies.learned` is only
  ever set once — the same inbound message can never be learned from twice.

## Testing (Phase 7)

`tests/test_reply_analyzer.py` — one test per intent (interested, not
interested, meeting request, price objection, unsubscribe, question,
neutral, unknown, follow-up) plus a full-field sanity check.

`tests/test_reply_matcher.py` — Message-ID match, References-header match,
sender-only match, "lead known but nothing sent" match, no-match, and a
false-positive guard (an unrelated header must not block a valid sender match).

`tests/test_reply_learning_integration.py` — idempotency (same reply
processed twice only learns once), low-confidence match rejection, strategy
pattern scores updating from a real reply, and the end-to-end test described
above that proves measurable behavioral change from experience.

Run everything: `pytest -q` (59 tests as of this rebuild).

## Repository cleanup and security (Phase 8)

This pass removed committed `.bak`/`.backup` files and stale SQLite backups,
replaced real personal email addresses that had been committed in
`your_leads.csv` and `tests/test_decision_engine.py` with `example.com`
placeholders, replaced a hardcoded look-real Gmail address that was used as
a fallback sender default in `composer.py` with an obvious placeholder, and
widened `.gitignore` to also exclude `*.bak`, `*.backup*`, `*.sqlite*`,
`.pytest_cache/`, `playwright_auth.json`, and `your_leads.csv` itself (use
`your_leads.example.csv`-style sample data instead of real lead lists going
forward). No live credentials were found in this pass, but if this repo was
ever public with real credentials in history, they should still be
considered compromised and rotated, and scrubbed from git history with
`git filter-repo` or the BFG Repo-Cleaner.

## Roadmap / what's not built yet

- **Phase 9** — wiring `LeadScraperTool` into a live end-to-end run against TruckerDB (untested here since it needs your live, rotated credentials).
- **Phase 10** — a dashboard (FastAPI routes exist as a placeholder package `app/api/`; nothing implemented yet). Would also be the natural place to surface `ReplyRepository.pending_review()` for human-in-the-loop confirmation.
- **Scheduler** — the internal scheduler for follow-ups/periodic learning-stat cleanup described in the spec isn't implemented; `main.py` is a manual/cron-triggerable entry point for now.
- **Real NLP provider wiring for reply text** — `LocalNLPProvider` is used for email *generation*; the reply analyzer is intentionally rule-based only (explainability), but a model-assisted second opinion on ambiguous replies (confidence < threshold) would be a reasonable Phase-9-adjacent addition instead of just queuing them for a human.
- **Gmail IMAP wiring for `process_reply`** — `GmailInbox.fetch_unread()` returns raw messages in the right shape for `Agent.process_reply`, but nothing in `main.py` polls the inbox and feeds them through yet; today `process_reply` is called directly (see the tests) rather than from a live loop.
