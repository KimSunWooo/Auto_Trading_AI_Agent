from ai_investment_agent.domain.enums import MarketRegimeType
from tests.context_support import AS_OF, engine


def test_unknown_regime_is_not_treated_as_safe():
    context = engine().build(ticker="005930", as_of=AS_OF)

    assert context.regime.regime is MarketRegimeType.UNKNOWN
    assert context.regime.treated_as_safe is False
    assert context.regime_is_actionable is False
    assert context.unknown_treated_as_safe is False
    assert context.regime.is_unknown is True
    assert context.regime.is_known is False
    assert "safe" in context.regime.explanation.lower()
    assert "action" not in context.model_dump()
    assert "decision" not in context.model_dump()
