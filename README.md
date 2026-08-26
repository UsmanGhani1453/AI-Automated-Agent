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

## Roadmap / what's not built yet

This delivers Phases 1–8 of the original plan (audit, agent core, memory, decision engine, planning, email composition/analysis, feedback plumbing, online learning) as a working, tested foundation. Not yet built:
- **Phase 9** — wiring `LeadScraperTool` into a live end-to-end run against TruckerDB (untested here since it needs your live, rotated credentials).
- **Phase 10** — a dashboard (FastAPI routes exist as a placeholder package `app/api/`; nothing implemented yet).
- **Phase 11** — automated tests (pytest) over the decision engine, analyzer, and learning engine — these are the modules most worth locking down with tests before you build on top.
- **Scheduler** — the internal scheduler for follow-ups/periodic learning-stat cleanup described in the spec isn't implemented; `main.py` is a manual/cron-triggerable entry point for now.
- **Real NLP provider wiring** — `LocalNLPProvider` exists but nothing calls it yet; it's meant to be invoked from `Composer` to propose *new* candidate component text when you want the pool to grow beyond the seed set.

I'd suggest tackling the dashboard and tests next, in that order — the dashboard gives you visibility into what the agent is actually learning, and tests protect the decision/learning logic before you extend it further.
