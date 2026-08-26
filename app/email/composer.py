"""
Composer: builds emails from discrete, independently-scored components
(greeting / opening / value proposition / service / CTA / signature), per
the "template + learned composition" and "evolutionary optimization" spec.

Component pools start with a handful of hand-written seed variants (cold
start needs *something* to try) and their scores adapt via ComponentRepository
as feedback comes in. New component text can also be registered at runtime
(e.g. if an NLP provider is plugged in later to generate fresh variants).
"""
import random
from app.database.repository import ComponentRepository

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

DEFAULT_SENDER = {
    "sender_name": "Natasha Roman",
    "sender_title": "Dispatch Operations Manager",
    "sender_email": "you@example.com",
}


class Composer:
    def ensure_seeded(self):
        for comp_type, variants in SEED_COMPONENTS.items():
            for text in variants:
                ComponentRepository.upsert(comp_type, text)

    def _fill(self, template, lead, sender):
        ctx = {**DEFAULT_SENDER, **sender, **lead}
        try:
            return template.format(**ctx)
        except KeyError:
            return template

    def top_candidates(self, component_type, k=3):
        rows = ComponentRepository.top_for_type(component_type, limit=max(k, 3))
        if not rows:
            self.ensure_seeded()
            rows = ComponentRepository.top_for_type(component_type, limit=max(k, 3))
        return rows

    def generate_candidates(self, lead, sender=None, n_candidates=3):
        """
        Evolutionary-lite: build several candidate emails by combining top-scoring
        components (with a little randomness so exploration doesn't fully stop
        once one component pulls ahead), then let the caller score/select.
        """
        sender = sender or {}
        candidates = []
        pools = {ct: self.top_candidates(ct, k=3) for ct in SEED_COMPONENTS}

        for _ in range(n_candidates):
            chosen = {}
            for comp_type, rows in pools.items():
                # weighted random choice favoring higher positive_score, so learning
                # actually shifts which components get picked over time
                weights = [max(r["positive_score"], 0.05) for r in rows]
                chosen[comp_type] = random.choices(rows, weights=weights, k=1)[0]

            body_parts = [
                self._fill(chosen["greeting"]["text"], lead, sender),
                "",
                self._fill(chosen["opening"]["text"], lead, sender),
                self._fill(chosen["value_prop"]["text"], lead, sender),
                self._fill(chosen["service"]["text"], lead, sender),
                self._fill(chosen["cta"]["text"], lead, sender),
                "",
                self._fill(chosen["signature"]["text"], lead, sender),
            ]
            body = "\n".join([p for p in body_parts if p != "" or True]).strip()
            # collapse accidental blank-line stacking
            body = "\n".join(body.splitlines())

            component_ids = {ct: row["id"] for ct, row in chosen.items()}
            candidates.append({"body": body, "component_ids": component_ids, "components": chosen})

        return candidates
