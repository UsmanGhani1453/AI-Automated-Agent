from app.email.analyzer import EmailAnalyzer

LEAD = {"officer": "James", "location": "Austin, TX", "company": "Redline Freight"}


def test_detects_placeholder():
    analyzer = EmailAnalyzer()
    report = analyzer.analyze("Hi [Your Name], please reply.", LEAD)
    assert report["placeholder_found"] is True
    assert report["quality_score"] < 0.5


def test_detects_spam_markers():
    analyzer = EmailAnalyzer()
    spammy = "ACT NOW!!! Limited time offer, don't miss this guaranteed deal, click here!"
    clean = "Hi James, we help small fleets near Austin reduce deadhead miles. Would you be open to a quick call this week? Best regards, Natasha"
    spam_report = analyzer.analyze(spammy, LEAD)
    clean_report = analyzer.analyze(clean, LEAD)
    assert spam_report["spam_risk"] > clean_report["spam_risk"]
    assert spam_report["quality_score"] < clean_report["quality_score"]


def test_personalization_detected_when_name_and_location_present():
    analyzer = EmailAnalyzer()
    body = "Dear James, I noticed your operation near Austin and wanted to reach out. Best regards, Natasha"
    report = analyzer.analyze(body, LEAD)
    assert report["personalization_score"] > 0


def test_personalization_zero_when_generic():
    analyzer = EmailAnalyzer()
    body = "Dear Sir or Madam, we offer freight services. Regards."
    report = analyzer.analyze(body, LEAD)
    assert report["personalization_score"] == 0


def test_cta_detected():
    analyzer = EmailAnalyzer()
    body = "Hi James, quick note about dispatching. Would you be open to a quick call this week? Regards, Natasha"
    report = analyzer.analyze(body, LEAD)
    assert report["cta_score"] == 1.0


def test_no_cta_scores_lower_than_with_cta():
    analyzer = EmailAnalyzer()
    with_cta = "Hi James, quick note. Would you be open to a quick call this week? Regards, Natasha"
    without_cta = "Hi James, quick note about our services. Regards, Natasha"
    r1 = analyzer.analyze(with_cta, LEAD)
    r2 = analyzer.analyze(without_cta, LEAD)
    assert r1["cta_score"] > r2["cta_score"]


def test_quality_score_in_valid_range():
    analyzer = EmailAnalyzer()
    report = analyzer.analyze("Dear James, thanks for your time near Austin. Best regards, Natasha", LEAD)
    assert 0.0 <= report["quality_score"] <= 1.0


def test_repeated_phrases_detected():
    analyzer = EmailAnalyzer()
    body = " ".join(["reach out to you today"] * 5)
    report = analyzer.analyze(body, LEAD)
    assert report["repeated_phrases"] > 0
