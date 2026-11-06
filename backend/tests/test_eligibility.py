from app.eligibility import check_eligibility


def test_eligible_when_all_rules_pass():
    result = check_eligibility(registered=True, fees_cleared=True, suspended=False)
    assert result.eligible
    assert result.reasons == []


def test_every_failed_rule_is_reported():
    result = check_eligibility(registered=False, fees_cleared=False, suspended=True)
    assert not result.eligible
    assert len(result.reasons) == 3


def test_unfulfilled_fees_block_entry():
    result = check_eligibility(registered=True, fees_cleared=False, suspended=False)
    assert not result.eligible
    assert result.reasons == ["Fees not cleared"]
