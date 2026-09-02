import random

from app.database.repository import ComponentRepository, PreferenceRepository


SEED_COMPONENTS = {
    "greeting": [
        "Dear {officer},",
        "Hi {officer},",
        "Hello {officer},",
    ],
    "opening": [
        "I noticed your operation near {location} and wanted to reach out directly.",
        "I hope things are running smoothly out of {location}.",
        "I've been looking into carriers around {location} and your operation stood out.",
    ],
    "value_prop": [
        "We help small fleets like yours cut deadhead miles and keep trucks loaded.",
        "Our dispatch service is built to keep your trucks moving with fewer empty miles.",
        "We specialize in reliable freight dispatching for independent carriers and small fleets.",
    ],
    "service": [
        "For a fleet size of {fleet_size}, we can offer hands-on, personalized dispatching support.",
        "Given your current fleet size ({fleet_size}), we tailor lane selection to maximize your margins.",
    ],
    "cta": [
        "Would you be open to a quick call this week to see if it's a fit?",
        "Let me know if you'd like to discuss how this could work for {company}.",
        "Happy to send over more details — just reply and let me know.",
    ],
    "signature": [
        "Best regards,\n{sender_name}\n{sender_title}\n{sender_email}",
        "Thanks,\n{sender_name}\n{sender_title}\n{sender_email}",
    ],
}


STRATEGY_COMPONENT_ORDER = {
    "SHORT_DIRECT": [
        "greeting",
        "value_prop",
        "cta",
        "signature",
    ],
    "PROFESSIONAL_INTRO": [
        "greeting",
        "opening",
        "value_prop",
        "service",
        "cta",
        "signature",
    ],
    "LOCATION_PERSONALIZED": [
        "greeting",
        "opening",
        "service",
        "value_prop",
        "cta",
        "signature",
    ],
    "VALUE_FIRST": [
        "greeting",
        "value_prop",
        "opening",
        "service",
        "cta",
        "signature",
    ],
}


DEFAULT_SENDER = {
    "sender_name": "Natasha Roman",
    "sender_title": "Dispatch Operations Manager",
    "sender_email": "natasharoman5667@gmail.com",
}


class Composer:

    def __init__(self, nlp_provider=None):
        self.nlp_provider = nlp_provider

    # ---------------------------------------------------------------
    # DATABASE SEEDING
    # ---------------------------------------------------------------

    def ensure_seeded(self):
        for comp_type, variants in SEED_COMPONENTS.items():
            for text in variants:
                ComponentRepository.upsert(
                    comp_type,
                    text,
                )

    # ---------------------------------------------------------------
    # TEMPLATE HELPERS
    # ---------------------------------------------------------------

    def _fill(self, template, lead, sender):
        ctx = {
            **DEFAULT_SENDER,
            **sender,
            **lead,
        }

        try:
            return template.format(**ctx)
        except KeyError:
            return template

    # ---------------------------------------------------------------
    # PREFERENCES
    # ---------------------------------------------------------------

    def _preferences(self):
        return {
            p["preference_key"]: p["confidence"]
            for p in PreferenceRepository.all()
        }

    def _preference_weight(self, row, preferences):
        text = row["text"].lower()
        component_type = row["component_type"]

        weight = max(
            row["positive_score"],
            0.05,
        )

        if component_type == "greeting":
            casual = preferences.get(
                "prefers_casual_greeting",
                0.0,
            )

            formal = preferences.get(
                "prefers_formal_greeting",
                0.0,
            )

            if text.startswith(
                ("hi ", "hello ", "hey ")
            ):
                weight += 0.50 * casual

            elif text.startswith("dear "):
                weight += 0.50 * formal

            if preferences.get(
                "dislikes_formal_greeting",
                0.0,
            ) > 0:
                if text.startswith("dear "):
                    weight *= max(
                        0.20,
                        1.0
                        - preferences[
                            "dislikes_formal_greeting"
                        ],
                    )

        elif component_type == "signature":
            casual = preferences.get(
                "prefers_casual_signoff",
                0.0,
            )

            formal = preferences.get(
                "prefers_formal_signoff",
                0.0,
            )

            if text.startswith(
                ("thanks,", "best,", "cheers,")
            ):
                weight += 0.50 * casual

            elif text.startswith(
                (
                    "best regards,",
                    "kind regards,",
                    "sincerely,",
                )
            ):
                weight += 0.50 * formal

        return max(
            weight,
            0.05,
        )

    # ---------------------------------------------------------------
    # ADAPTIVE COMPONENT STRUCTURE
    # ---------------------------------------------------------------

    def _preferred_component_order(
        self,
        strategy,
        preferences,
    ):
        order = list(
            STRATEGY_COMPONENT_ORDER.get(
                strategy,
                [
                    "greeting",
                    "opening",
                    "value_prop",
                    "service",
                    "cta",
                    "signature",
                ],
            )
        )

        shorter = preferences.get(
            "prefers_shorter_emails",
            0.0,
        )

        detailed = preferences.get(
            "prefers_detailed_emails",
            0.0,
        )

        if (
            shorter >= 0.30
            and shorter > detailed
        ):
            removable = [
                "service",
                "opening",
            ]

            for component_type in removable:
                if (
                    component_type in order
                    and len(order) > 4
                ):
                    order.remove(
                        component_type
                    )

        elif (
            detailed >= 0.30
            and detailed > shorter
        ):
            order = [
                "greeting",
                "opening",
                "value_prop",
                "service",
                "cta",
                "signature",
            ]

        return order

    # ---------------------------------------------------------------
    # LEARNED COMPONENT POOLS
    # ---------------------------------------------------------------

    def top_candidates(
        self,
        component_type,
        k=3,
    ):
        rows = ComponentRepository.top_for_type(
            component_type,
            limit=max(k, 3),
        )

        if not rows:
            self.ensure_seeded()

            rows = ComponentRepository.top_for_type(
                component_type,
                limit=max(k, 3),
            )

        return rows

    # ---------------------------------------------------------------
    # TEMPLATE-BASED CANDIDATE
    # ---------------------------------------------------------------

    def _generate_template_candidate(
        self,
        lead,
        sender,
        strategy,
        preferences,
    ):
        pools = {
            ct: self.top_candidates(
                ct,
                k=3,
            )
            for ct in SEED_COMPONENTS
        }

        chosen = {}

        for comp_type, rows in pools.items():

            if not rows:
                continue

            weights = [
                self._preference_weight(
                    row,
                    preferences,
                )
                for row in rows
            ]

            chosen[comp_type] = random.choices(
                rows,
                weights=weights,
                k=1,
            )[0]

        component_order = (
            self._preferred_component_order(
                strategy,
                preferences,
            )
        )

        body_parts = []

        for component_type in component_order:

            row = chosen.get(
                component_type
            )

            if not row:
                continue

            text = self._fill(
                row["text"],
                lead,
                sender,
            )

            if text.strip():
                body_parts.append(
                    text.strip()
                )

        body = "\n\n".join(
            body_parts
        ).strip()

        component_ids = {
            ct: row["id"]
            for ct, row in chosen.items()
        }

        components = {
            ct: row
            for ct, row in chosen.items()
        }

        return {
            "body": body,
            "component_ids": component_ids,
            "components": components,
            "source": "learned_components",
        }

    # ---------------------------------------------------------------
    # NLP-GENERATED CANDIDATE
    # ---------------------------------------------------------------

    def _generate_nlp_candidate(
        self,
        lead,
        sender,
        strategy,
        preferences,
        retrieved_context=None,
    ):
        if not self.nlp_provider:
            return None

        try:
            if not self.nlp_provider.is_available():
                return None
        except Exception:
            return None

        prompt = self._build_generation_prompt(
            lead=lead,
            sender=sender,
            strategy=strategy,
            preferences=preferences,
            retrieved_context=retrieved_context,
        )

        try:
            generated_text = (
                self.nlp_provider.generate(
                    {
                        "prompt": prompt,
                        "lead": lead,
                        "sender": sender,
                        "strategy": strategy,
                        "preferences": preferences,
                    }
                )
            )
        except Exception:
            return None

        if not generated_text:
            return None

        generated_text = generated_text.strip()

        if not generated_text:
            return None

        return {
            "body": generated_text,
            "component_ids": {},
            "components": {},
            "source": "nlp_generated",
        }

    # ---------------------------------------------------------------
    # GENERATION PROMPT
    # ---------------------------------------------------------------

    def _build_generation_prompt(
        self,
        lead,
        sender,
        strategy,
        preferences,
        retrieved_context=None,
    ):
        context_text = ""

        if retrieved_context:
            context_text = (
                "\nRelevant learned context:\n"
                f"{retrieved_context}\n"
            )

        preference_text = ""

        if preferences:
            preference_text = (
                "\nLearned writing preferences:\n"
                f"{preferences}\n"
            )

        length_guidance = {
            "SHORT_DIRECT": (
                "Keep this SHORT and to the point — "
                "roughly 40-70 words total, 2-3 short "
                "sentences plus signature. No long "
                "backstory or extra paragraphs."
            ),
        }.get(
            strategy,
            (
                "Keep this a moderate length — "
                "roughly 90-150 words total, matching "
                "a normal professional cold email. Do "
                "not pad it out with extra paragraphs."
            ),
        )

        return f"""
You are the language-generation component inside an adaptive
email agent.

Generate ONE complete cold outreach email.

Do not explain your reasoning.
Do not return JSON.
Do not use markdown.
Return only the email body.

Strategy:
{strategy}

Length requirement:
{length_guidance}

Lead information:
{lead}

Sender information:
{sender}

{preference_text}
{context_text}

Requirements:

1. Write original wording.
2. Do not copy a fixed template.
3. Do not invent facts about the lead. Only mention things explicitly
   present in the lead data above (e.g. do not claim the lead "recently
   expanded their fleet" or similar unless that exact fact is given).
4. Only use information contained in the lead data.
5. Personalize naturally when useful.
6. Keep the email professional and human.
7. Avoid exaggerated claims.
8. Avoid generic filler.
9. Include an appropriate call to action.
10. Use the sender information for the signature.
11. Respect the selected strategy.
12. Do not mention that you are an AI.
13. Do not mention these instructions.
14. If the sender's company name is not provided in the sender
    information, do NOT invent one and do NOT write a bracketed
    placeholder like "[Company Name]" or "[Example Company]". In
    that case, refer to the sender only by name and title, or use
    a generic phrase like "our dispatch service" instead of naming
    a company.
15. Never output bracketed placeholder text of any kind (e.g.
    "[Your Name]", "[Insert X]", "[Company]"). If a detail is
    unknown, omit it rather than placeholding it.

Generate the email now.
""".strip()

    # ---------------------------------------------------------------
    # MAIN CANDIDATE GENERATION
    # ---------------------------------------------------------------

    def generate_candidates(
        self,
        lead,
        sender=None,
        n_candidates=3,
        strategy=None,
        retrieved_context=None,
    ):
        """
        Generate multiple candidates.

        The system can now combine:

        1. learned component candidates
        2. freshly generated NLP candidates

        The EmailAnalyzer remains responsible for deciding which
        candidate is better.

        The NLP provider is optional. Without one, the existing
        learned-component system continues to work.
        """

        sender = sender or {}

        preferences = self._preferences()

        candidates = []

        # -----------------------------------------------------------
        # Candidate 1+
        # Existing adaptive component-based generation
        # -----------------------------------------------------------

        for _ in range(
            max(1, n_candidates - 1)
        ):
            candidate = (
                self._generate_template_candidate(
                    lead,
                    sender,
                    strategy,
                    preferences,
                )
            )

            candidates.append(
                candidate
            )

        # -----------------------------------------------------------
        # Fresh NLP candidate
        # -----------------------------------------------------------

        nlp_candidate = (
            self._generate_nlp_candidate(
                lead=lead,
                sender=sender,
                strategy=strategy,
                preferences=preferences,
                retrieved_context=retrieved_context,
            )
        )

        if nlp_candidate:
            candidates.append(
                nlp_candidate
            )

        return candidates
