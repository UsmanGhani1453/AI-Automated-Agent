"""
EmailAnalyzer: rule-based / statistical email quality scoring.
No LLM call here — this is deterministic text analysis so it's fast, free,
and explainable. This is the piece that feeds "quality_score" into the
decision engine's regenerate/accept threshold.
"""
import re

SPAM_MARKERS = [
    "act now", "limited time", "don't miss", "click here", "free money",
    "guaranteed", "risk free", "100% free", "urgent", "hurry", "!!!",
]
PLACEHOLDER_MARKERS = ["[your name]", "[company]", "[email]", "{{", "}}", "<insert", "[insert"]
CTA_MARKERS = ["let's discuss", "reply to", "schedule a call", "reach out", "would love to",
               "let me know", "book a", "set up a", "connect this week", "would you be open to",
               "quick call", "happy to send", "just reply"]


def _sentences(text):
    return [s for s in re.split(r"[.!?]+", text) if s.strip()]


def _words(text):
    return re.findall(r"[A-Za-z']+", text)


class EmailAnalyzer:
    def analyze(self, email: str, lead: dict) -> dict:
        text = email.strip()
        lower = text.lower()
        words = _words(text)
        sentences = _sentences(text)
        word_count = len(words)
        sentence_count = max(len(sentences), 1)
        avg_words_per_sentence = word_count / sentence_count

        # Readability: a lightweight Flesch-style approximation (no syllable dict needed,
        # approximate syllables by vowel-group count).
        def syllables(word):
            return max(1, len(re.findall(r"[aeiouyAEIOUY]+", word)))
        total_syllables = sum(syllables(w) for w in words) or 1
        flesch = 206.835 - 1.015 * avg_words_per_sentence - 84.6 * (total_syllables / max(word_count, 1))
        readability = max(0.0, min(100.0, flesch))

        greeting = bool(re.match(r"^\s*(dear|hi|hello|hey)\b", lower))
        signature = any(m in lower for m in ["regards", "best,", "sincerely", "thanks,", "thank you,"])

        officer = (lead.get("officer") or "").lower()
        location = (lead.get("location") or "").lower()
        company = (lead.get("company") or "").lower()

        personalization_hits = sum([
            bool(officer) and officer.split()[0] in lower if officer else False,
            bool(location) and location.split(",")[0].strip() in lower if location else False,
        ])
        personalization_score = min(1.0, personalization_hits / 2)
        company_mention = bool(company) and company in lower
        location_mention = bool(location) and location.split(",")[0].strip() in lower

        cta_score = 1.0 if any(m in lower for m in CTA_MARKERS) else 0.0
        spam_hits = sum(1 for m in SPAM_MARKERS if m in lower)
        spam_risk = min(1.0, spam_hits / 3)
        placeholder_found = any(m in lower for m in PLACEHOLDER_MARKERS)

        # repeated phrases: any 4-gram appearing more than once
        tokens = [w.lower() for w in words]
        fourgrams = [" ".join(tokens[i:i + 4]) for i in range(len(tokens) - 3)]
        repeated_phrases = len(fourgrams) - len(set(fourgrams)) if fourgrams else 0

        unnecessary_phrases = sum(1 for p in ["just wanted to", "i hope this email finds you well",
                                               "to whom it may concern"] if p in lower)

        professionalism_score = 1.0
        professionalism_score -= 0.3 if spam_risk > 0 else 0
        professionalism_score -= 0.2 if placeholder_found else 0
        professionalism_score -= 0.1 * min(unnecessary_phrases, 2)
        professionalism_score -= 0.15 if not signature else 0
        professionalism_score = max(0.0, professionalism_score)

        relevance_score = 0.5 + 0.25 * personalization_score + (0.25 if company_mention else 0)

        # Composite quality score (weighted average of sub-scores, all 0-1)
        quality_components = {
            "personalization": personalization_score,
            "professionalism": professionalism_score,
            "relevance": min(1.0, relevance_score),
            "cta": cta_score,
            "spam_safety": 1.0 - spam_risk,
            "length_fit": 1.0 if 40 <= word_count <= 160 else max(0.0, 1 - abs(word_count - 100) / 200),
        }
        weights = {
            "personalization": 0.25, "professionalism": 0.2, "relevance": 0.15,
            "cta": 0.15, "spam_safety": 0.15, "length_fit": 0.10,
        }
        quality_score = sum(quality_components[k] * weights[k] for k in weights)
        # penalize placeholders and repeated phrases hard regardless of weighted score
        if placeholder_found:
            quality_score *= 0.4
        if repeated_phrases > 2:
            quality_score *= 0.85

        return {
            "word_count": word_count,
            "sentence_count": sentence_count,
            "avg_words_per_sentence": round(avg_words_per_sentence, 1),
            "readability": round(readability, 1),
            "greeting": greeting,
            "signature": signature,
            "personalization_score": round(personalization_score, 2),
            "company_mention": company_mention,
            "location_mention": location_mention,
            "cta_score": cta_score,
            "spam_risk": round(spam_risk, 2),
            "placeholder_found": placeholder_found,
            "repeated_phrases": repeated_phrases,
            "unnecessary_phrases": unnecessary_phrases,
            "professionalism_score": round(professionalism_score, 2),
            "relevance_score": round(min(1.0, relevance_score), 2),
            "quality_score": round(quality_score, 3),
        }
