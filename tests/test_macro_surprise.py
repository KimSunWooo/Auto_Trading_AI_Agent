from decimal import Decimal

from ai_investment_agent.features.macro import MacroSurpriseCalculator


def test_macro_surprise_is_not_invented_when_inputs_are_missing():
    calc = MacroSurpriseCalculator()
    incomplete = calc.compute(series_id="CPI", previous=Decimal("3.1"))
    assert incomplete.actual is None
    assert incomplete.consensus is None
    assert incomplete.surprise is None
    assert incomplete.surprise_z_score is None
    assert "actual" in incomplete.missing_fields
    assert "consensus" in incomplete.missing_fields

    complete = calc.compute(
        series_id="CPI",
        actual=Decimal("3.4"),
        consensus=Decimal("3.1"),
        previous=Decimal("3.0"),
        historical_std=Decimal("0.2"),
    )
    assert complete.surprise == Decimal("0.3")
    assert complete.surprise_z_score == Decimal("0.3") / Decimal("0.2")
    assert complete.missing_fields == []
