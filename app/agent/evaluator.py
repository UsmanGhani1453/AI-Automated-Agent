"""
Evaluator: wraps the analyzer's per-email score into a task-level evaluation
(did this attempt succeed against the plan's goal), separate from the
low-level EmailAnalyzer so the agent core has one place to ask "did that go well?"
"""


class Evaluator:
    def evaluate_email(self, analyzer_report: dict, threshold: float = 0.55) -> dict:
        passed = analyzer_report.get("quality_score", 0) >= threshold and not analyzer_report.get("placeholder_found")
        return {
            "passed": passed,
            "quality_score": analyzer_report.get("quality_score"),
            "threshold": threshold,
            "reasons": self._reasons(analyzer_report, threshold),
        }

    def _reasons(self, report, threshold):
        reasons = []
        if report.get("placeholder_found"):
            reasons.append("unresolved placeholder present")
        if report.get("quality_score", 0) < threshold:
            reasons.append(f"quality {report.get('quality_score', 0):.2f} below threshold {threshold}")
        if report.get("spam_risk", 0) > 0.3:
            reasons.append(f"elevated spam risk ({report['spam_risk']:.2f})")
        if not reasons:
            reasons.append("met all quality checks")
        return reasons

    def evaluate_outcome(self, sent: bool, replied: bool, rating: int = None) -> dict:
        score = 0.0
        if sent:
            score += 0.3
        if rating:
            score += (rating / 5) * 0.4
        if replied:
            score += 0.3
        return {"sent": sent, "replied": replied, "rating": rating, "outcome_score": round(score, 2)}
