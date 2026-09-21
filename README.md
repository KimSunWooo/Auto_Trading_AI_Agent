# AI Investment Judgment Agent

독립형 AI 투자 판단 Agent입니다. 책임 범위는 **Data → Analysis → Risk Assessment → Decision → TradeProposal**까지입니다.

`TradeProposal`은 나중에 외부 시스템이 소비할 수 있는 제안/판단 결과입니다. **주문이 아닙니다.**

## 이 프로젝트가 하지 않는 것

- Auto-Trading-system 코드 import, DB, API, Redis, Kafka 공유
- KIS 주문 API
- PAPER/REAL 주문
- OrderManager / Broker / 실제 주문 로직
- 실제 뉴스, DART, LLM, 시세 API 연결 (이번 단계는 Fixture/Mock)

수익률 최대화가 목표가 아닙니다. 우선순위는 다음과 같습니다.

1. Capital Preservation
2. Catastrophic Loss 방지
3. Risk-adjusted Return
4. 안정적인 판단
5. 수익 기회 탐색

`NO_TRADE`는 정상적이고 중요한 결과입니다.

## 요구 사항

- Python 3.11+

## 설치 및 테스트

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## 패키지 구조

Python 패키지명 충돌을 피하기 위해 루트는 `src/ai_investment_agent/`입니다. 그 안의 경계는 요청하신 monolith 내부 모듈과 같습니다.

```
src/ai_investment_agent/
  domain/        # 모델, 규칙, 직렬화. 바깥 계층을 import하지 않음
  ports/         # MarketData, Event, LLM, Repository, Publisher, Collectors
  adapters/      # Fixture / in-memory 구현만 존재
  collectors/    # Market Data vs External Intelligence (fixtures; explicit status)
  intelligence/  # Event Intelligence + fixture regime assessor
  features/      # deterministic Market Context / Feature Engine
  scanner/       # 이후 단계
  horizon/       # HorizonSelector + LONG/SHORT mapping
  agents/        # LongTermAgent, ShortTermAgent, InvestmentJudgmentAgent
  decision/      # 순수 DecisionEngine
  capital/       # CapitalContext 해석. 누락 시 0, 무한 자금 아님
  policy/        # 하드 게이트 + SafetyPolicyLayer (Proposal만 제한)
  journal/       # Decision journal
  evaluation/    # 이후 단계
  replay/        # as-of 접근성 필터 (look-ahead 방지)
  health/        # 판단 전용 모드 상태
  api/           # HTTP는 이번 단계 미구현
```

## Domain 의존 방향

```
adapters → ports → (구현 계약)
agents → ports, decision, capital, policy, journal, intelligence
decision / capital / policy / horizon → domain
domain → 표준 라이브러리 + pydantic  (adapter/SDK 금지)
```

안쪽 화살표는 없습니다. Domain은 LLM SDK, 브로커, 자동매매 프로젝트를 모릅니다.

## 핵심 모델

- `MarketSnapshot`, `MarketEvent`, `MarketRegime` (판단 계층; 수집 계층과 분리)
- `MarketDataRecord` / `IntelligenceRecord` / `CorporateAction` (수집 계층)
- `CapitalContext` (AI 한도 뷰. 전체 계좌 제어 아님)
- `InvestmentThesis`, `TradeProposal`
- `DecisionSnapshot`, `DecisionJournalEntry`

지원 Decision:

`LONG_TERM_BUY` · `SHORT_TERM_BUY` · `HOLD` · `SELL` · `NO_TRADE` · `TACTICAL_WAIT` · `EXIT_REVIEW`

`suggestedCapitalPct`는 주문 금액이 아닙니다. AI 할당 가능 자본 대비 권고 비율(0–100)입니다.

`CapitalContext`가 없으면 자금이 무한하다고 보지 않습니다. 모든 한도를 0으로 두는 conservative default를 쓰고, 신규 BUY는 `NO_TRADE`가 됩니다.

UNKNOWN 레짐은 `NO_TRADE`입니다.

## Capital / Policy / Safety Decision Layer

AI가 만든 `TradeProposal`을 **허용 / 축소 / 보류 / 거절**하는 AI-side Policy Layer입니다. Broker RiskManager가 아니며, 실제 주문을 막거나 거래 시스템을 멈추지 않습니다. 결과는 Proposal의 `policyResult`로만 남습니다.

자금 계층:

```
Total Capital
    ↓
AI Capital Limit     ← AI는 이 밖을 쓸 수 없음
    ↓
Long Budget / Short Budget / Reserve Cash
```

Capital Limit(투입 가능 최대 자금)과 Risk Budget(허용 손실 규모)은 분리되어 있습니다. Risk 버킷 구조: AI Drawdown, Daily Loss, Per-position, Sector, Theme, Country, Currency, Correlation, Stress Correlation, Tail, Liquidity.

현재 단계는 실제 자동매매 Portfolio를 읽지 않습니다. `PortfolioContext.source`는 `fixture`만 허용합니다.

Policy 상태: `NORMAL` · `REDUCED_EXPOSURE` · `NO_NEW_BUY` · `AI_DISABLED` · `UNKNOWN`.

Kill switch (Proposal 결과 전용):

| Level | 의미 | Proposal |
| --- | --- | --- |
| 0 | NORMAL | 그대로 평가 |
| 1 | NO_NEW_BUY | 신규 BUY 거절 |
| 2 | REDUCE_EXPOSURE | 노출 축소 |
| 3 | AI_DISABLED | `NO_TRADE` |
| 4 | ALL_TRADING_DISABLED | `NO_TRADE` |

`ALL_TRADING_DISABLED`는 `FORCE_SELL_ALL`이 아닙니다. Level 4는 청산 지시가 아니라 거래 제안 중단입니다. `PolicyResult.forceSellAll`은 항상 `false`입니다.

Human Override는 외부에서만 주입합니다. AI가 변경할 API가 없고 `HumanOverride`는 frozen입니다.

- `AI_ENABLED`
- `LONG_AGENT_ENABLED`
- `SHORT_AGENT_ENABLED`
- `SYMBOL_BLACKLIST`
- `SECTOR_BLACKLIST`

UNKNOWN Policy는 신규 BUY를 불허하고 `TACTICAL_WAIT`(보류)로 바꿉니다.

## Collection layer

Market Data and External Intelligence are collected independently. They are never mixed in one collector.

- Market Data: OHLCV, Current Price, Volume, Index, FX, Rates, Commodity, Volatility, Liquidity
- External Intelligence: corporate disclosure, domestic/foreign news, central bank, government policy, economic indicators, geopolitics, industry events, corporate events
- Corporate actions are fixture-only (no live feed)

Every collected record carries `eventOccurredAt`, `publishedAt`, `sourceReceivedAt`, `collectedAt`, `normalizedAt`, `analyzedAt`, `tradableAt`. Replay/backtest may use a record only when `tradableAt` and `sourceReceivedAt` are ≤ `as_of`.

Collectors return an explicit `CollectionStatus`. `NO_EVENT` (successful empty feed) is not `DATA_UNAVAILABLE` (API/feed failure). Empty arrays are never implied success.

Freshness classes: `ULTRA_FAST`, `INTRADAY`, `DAILY`, `LONG_HORIZON`.

## Event Intelligence

수집된 뉴스/공시/거시 문서는 감성점수가 아니라 **시장 사건**으로 변환됩니다. 이 단계는 매수/매도 결정을 하지 않습니다.

```
Raw Event → Parser → Sanitizer → Normalizer → Deduplication
  → Entity Extraction → Source Trust → Verification → Impact Analysis
  → AnalyzedMarketEvent
```

- 기사 수 ≠ 사건 수. 같은 사건은 `EventCluster`로 묶습니다.
- Embedding은 `EmbeddingProvider` 포트로 추상화되어 있고, 현재는 hashed bag fixture입니다.
- Source trust 티어 S–D는 `policy/source_trust.py`에 하드코딩되어 있습니다.
- 정정보도는 이벤트를 삭제하지 않고 `verificationStatus=RETRACTED`로 바꿉니다.
- 외부 문서는 항상 untrusted data입니다. Raw 텍스트를 LLM instruction에 붙이지 않습니다.
- 방향 증거가 없으면 `UNKNOWN`이며 POSITIVE/NEGATIVE로 강제하지 않습니다.

## Market Context / Features

Market Data와 Event Intelligence를 **판단 입력**으로 바꿉니다. 이 단계는 BUY/SELL Proposal을 만들지 않습니다.

정량 지표(Return, MA, Momentum, Volatility, Drawdown, Volume Ratio, Liquidity, Trend, Relative Strength, Time Decay)는 LLM이 아니라 deterministic code로 계산합니다.

Event effectiveImpact:

`rawImpact × sourceTrust × relevance × novelty × confidence × timeDecay`

계수는 `policy/feature_config.py`의 `EventImpactWeights`로 바꿉니다. 기본 지수는 모두 1이라 위 곱과 같습니다.

- UNKNOWN 레짐은 정상/안전으로 보지 않습니다.
- Macro surprise는 actual과 consensus가 있을 때만 계산하며, 빈 값을 추측하지 않습니다.
- Priced-in은 `PricedInAnalyzer` 포트로 교체 가능한 heuristic입니다.
- Positive event + 강한 음수 시장 반응이면 `EVENT_MARKET_DIVERGENCE`를 만들고 event confidence를 낮춥니다.

## Long / Short Agents

Long-Term Agent와 Short-Term Agent는 **독립적으로** 판단합니다. 점수를 평균 내지 않습니다.

Long 예: Daily/Weekly Trend, MA20/60/120, Momentum, Drawdown, Fundamentals, Valuation, Sector Strength, Macro Risk, Long Horizon Events. 없는 값은 추측하지 않습니다.

Short 예: Intraday trend, 1m/5m/15m OHLCV, VWAP, Volume Spike, Momentum, Breakout, Volatility, Liquidity, Spread, Short-lived Event. 아직 없는 피처는 optional입니다.

Horizon Selector 반환값: `LONG_TERM` / `SHORT_TERM` / `TACTICAL_WAIT` / `NO_TRADE`. 억지로 하나를 고르지 않습니다. Long bullish + Short bearish 이면 `LONG_THESIS_VALID` + `TACTICAL_WAIT`가 가능합니다.

Net Edge = Expected Return − Risk Penalty − Transaction Cost − Slippage − Drawdown Penalty − Tail Risk − Uncertainty Penalty. 부족하면 `NO_TRADE`.

BUY/HOLD thesis에는 `drivers`와 `invalidations`를 남깁니다. `EntryAnalyzer`와 `PositionThesisMonitor`는 분리되어 있고, Position은 fixture만 사용합니다. 결과는 여전히 TradeProposal까지입니다.

