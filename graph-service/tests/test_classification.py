from app.domain.classification import classify_text
from app.domain.routing import route_case
from app.domain.transitions import can_transition


def test_access_request_is_confident_and_does_not_skip_policy():
    result = classify_text(
        "Finance folder access request",
        "Resource: Finance Reporting library\nJustification: Monthly close pack.",
    )
    assert result.category_id == "access_request"
    assert result.confidence == "high"
    assert result.manual_triage is False


def test_ambiguous_text_is_not_given_a_pretend_category():
    result = classify_text(
        "Access and a laptop",
        "I need access to the facilities maintenance folder and a laptop for the night roster.",
    )
    assert result.category_id is None
    assert result.confidence == "low"
    assert result.manual_triage is True


def test_short_text_asks_for_detail():
    result = classify_text("Help", "Need help")
    assert result.manual_triage is True
    assert result.missing_information


def test_account_compromise_is_urgent_without_inventing_an_owner():
    result = classify_text("Account locked", "I am locked out after a phishing message and I cannot log in.")
    assert result.category_id == "it_support"
    assert result.priority == "urgent"
    assert result.security_escalation is True


def test_unknown_department_access_does_not_invent_a_team():
    decision = route_case(
        category_id="access_request",
        requester_department="Field Research",
        manual_triage=False,
        missing_information=False,
    )
    assert decision.team is None
    assert decision.outcome == "failed"


def test_closed_case_cannot_jump_to_approved():
    assert can_transition("closed", "approved") is False
    assert can_transition("closed", "in_progress") is True
    assert can_transition("rejected", "awaiting_fulfilment") is False
