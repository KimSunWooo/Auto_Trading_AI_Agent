# AI Investment Judgment Agent

독립형 AI 투자 판단 Agent입니다. 책임 범위는 **Data → Analysis → Risk Assessment → Decision → TradeProposal**까지입니다.

`TradeProposal`은 나중에 외부 시스템이 소비할 수 있는 제안/판단 결과입니다. **주문이 아닙니다.**

## 이 프로젝트가 하지 않는 것

- Auto-Trading-system 코드 import, DB, API, Redis, Kafka 공유
- KIS 주문 API
- PAPER/REAL 주문
- OrderManager / Broker / 실제 주문 로직
- 실제 뉴스, DART, LLM, 시세 API 연결은 **Live Observation**에서만 (`AI_DATA_MODE=LIVE_OBSERVATION`). 기본은 Fixture/Mock
- KIS/Broker 주문 경로

수익률 최대화가 목표가 아닙니다. 우선순위는 다음과 같습니다.

1. Capital Preservation
2. Catastrophic Loss 방지
3. Risk-adjusted Return
4. 안정적인 판단
5. 수익 기회 탐색

`NO_TRADE`는 정상적이고 중요한 결과입니다.

## 현재 단계

- Phase 1~10 complete
- Pre-10.5 stabilization complete (Fail-Closed, Feature semantics, Runtime/Contract boundary, Persistence/CI baseline)
- **10.5 Live Intelligence Adapter complete**

| Capability | Status |
| --- | --- |
| Live Market Data | Connected (read-only JSON feed via `MARKET_DATA_*`) |
| Live Disclosure (OpenDART) | Connected (`DART_API_KEY`) |
| Live Macro | Connected (official JSON feed via `MACRO_*`) |
| Live News | Connected (wire/media JSON feed via `NEWS_*`) |
| Live LLM | Connected (OpenAI-compatible via `LLM_*`) |
| Live Observation | Supported (`AI_DATA_MODE=LIVE_OBSERVATION`) |
| Auto-Trading-system | NOT CONNECTED |
| Broker | NOT CONNECTED |
| PAPER Orders | DISABLED |
| REAL Orders | DISABLED |

Runtime / Data Mode: `FIXTURE` · `REPLAY` · `LIVE_OBSERVATION` · `LIVE_SHADOW`. 기본 실행은 `FIXTURE`입니다. Profile이 없으면 LIVE로 간주하지 않습니다. Fixture fallback은 `FIXTURE`에서만 허용됩니다.

Live Observation capital은 `source=observation_config`이며 실제 계좌가 아닙니다.

## Persistence

현재 Decision journal, Event store, Shadow book, Evaluation history는 **InMemory**입니다.

- 10.5 Live Observation → InMemory 가능
- 장시간 Live Shadow Soak 이전 → Durable Persistence 필수
- 권장 미래 구조: AI Agent 전용 PostgreSQL
- Auto-Trading-system DB와 절대 공유하지 않음

## 요구 사항

- Python 3.11+

## 설치 및 테스트

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
NO_NETWORK=1 pytest
ruff check src tests
python -m compileall src/ai_investment_agent
```

환경 변수 이름은 `.env.example`을 참고하세요. 실제 Secret 값은 커밋하지 마세요.

수동 Live Observation smoke (실자격증명 + 네트워크 필요, CI 금지):

```bash
export AI_DATA_MODE=LIVE_OBSERVATION
# export MARKET_DATA_BASE_URL=... DART_API_KEY=... MACRO_BASE_URL=... NEWS_BASE_URL=... LLM_API_KEY=...
python -m ai_investment_agent.cli.observation_smoke --ticker 005930
```

분석 API:

```bash
uvicorn ai_investment_agent.api.app:app --host 0.0.0.0 --port 43187
```

## 패키지 구조

Python 패키지명 충돌을 피하기 위해 루트는 `src/ai_investment_agent/`입니다. 그 안의 경계는 요청하신 monolith 내부 모듈과 같습니다.

```
src/ai_investment_agent/
  domain/        # 모델, 규칙, 직렬화. 바깥 계층을 import하지 않음
  ports/         # MarketData, Event, LLM, Repository, Publisher, Collectors
  adapters/      # Fixture / in-memory / live (Market·DART·Macro·News·LLM)
  collectors/    # Market Data vs External Intelligence (fixtures; explicit status)
  intelligence/  # Event Intelligence + fixture regime assessor
  features/      # deterministic Market Context / Feature Engine
  scanner/       # 이후 단계
  horizon/       # HorizonSelector + LONG/SHORT mapping
  agents/        # LongTermAgent, ShortTermAgent, InvestmentJudgmentAgent
  decision/      # 순수 DecisionEngine
  capital/       # CapitalContext 해석. 누락 시 0, 무한 자금 아님
  policy/        # 하드 게이트 + SafetyPolicyLayer (Proposal만 제한)
  journal/       # Decision journal (모든 action 저장)
  evaluation/    # Offline quality / health / promotion path
  replay/        # replay(decisionId) + as-of 접근성 필터
  health/        # process + component health (UNKNOWN ≠ HEALTHY)
  analysis/      # Market Data → TradeProposal 파이프라인
  shadow/        # AI 전용 가상 계좌 / 가상 체결. Broker entity 아님
  contracts/     # TradeProposalEnvelope v1. 전송/ATS 연결 없음
  api/           # FastAPI. 주문 라우트 없음
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
- `DecisionSnapshot`, `DecisionRecord`, `DecisionJournalEntry`
- `ShadowOrder`, `ShadowFill`, `ShadowPosition`, `ShadowPortfolio` (가상 장부. Broker Order/Fill/Position이 아님)
- `TradeProposalEnvelope` (`schemaVersion=ai.trade-proposal.v1`. 향후 Consumer용 계약. 주문이 아님)

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

## Decision Journal / Evaluation / Replay

모든 판단을 저장합니다. BUY만이 아니라 `SELL` · `HOLD` · `TACTICAL_WAIT` · `NO_TRADE` · `EXIT_REVIEW`도 동일하게 journal에 남습니다.

`DecisionRecord` 최소 필드: decisionId, timestamp, ticker, marketSnapshot, eventSnapshot, featureSnapshot, marketRegime, longAnalysis, shortAnalysis, selectedHorizon, action, rawConfidence, calibratedConfidence, expectedReturn, estimatedRisk, suggestedCapitalPct, reasonCodes, thesis, invalidationConditions, modelVersion, promptVersion, featureVersion, policyVersion.

Confidence: LLM `rawConfidence`는 확률이 아닙니다. `calibratedConfidence`는 오프라인 calibration table이 있을 때만 채웁니다. 데이터가 없으면 `null`이며 값을 지어내지 않습니다.

Counterfactual: 실제 주문이 없어도 나중에 `return1h` / `return1d` / `return5d` / `return20d` / MFE / MAE를 붙일 수 있습니다.

`ReplayService.replay(decisionId)`는 당시 snapshot과 version pin을 복원합니다. Live LLM/시세 호출을 다시 돌리지는 않습니다.

성능 축은 분리되어 있습니다.

- Alpha Quality
- Horizon Selection Quality
- Risk Assessment Quality
- Capital Allocation Quality

Execution Quality는 주문 시스템 결합 이후에 별도로 평가할 예정이며 현재는 구현하지 않습니다.

Model Health metric interface: Win Rate, Expected Value, Drawdown, Sharpe, Calibration Error, Decision Distribution, Trade/Proposal Frequency, Average Confidence.

상태: `HEALTHY` · `DEGRADED` · `UNHEALTHY` · `UNKNOWN`. `UNKNOWN`은 `HEALTHY`로 취급하지 않습니다.

온라인 자기학습은 금지입니다. 손실이 나면 바로 다음 판단의 전략을 바꾸지 않습니다.

```
Decision Logs → Offline Evaluation → Candidate Model → Backtest → Shadow → 승인 → New Version
```

## Analysis API

독립 서비스입니다. Auto-Trading-system과 연결하지 않습니다. 실제 주문 API는 없습니다.

| Method | Path | 역할 |
| --- | --- | --- |
| POST | `/analysis/evaluate` | 판단 파이프라인 실행 → TradeProposal 저장 (FIXTURE 또는 LIVE_OBSERVATION) |
| POST | `/observation/evaluate` | LIVE_OBSERVATION 전용 evaluate. 주문 없음 |
| GET | `/providers` | Provider 목록 (secret 미포함) |
| GET | `/providers/health` | Provider health 요약 |
| GET | `/decisions` | Journal에 저장된 판단 목록 |
| GET | `/decisions/{decisionId}` | 단건 조회 |
| POST | `/decisions/{decisionId}/replay` | 당시 snapshot과 version pin 복원 |
| GET | `/health` | 컴포넌트별 health + 종합 상태 |
| GET | `/contracts` | 지원 schemaVersion 목록. ATS 연결 아님 |
| GET | `/contracts/trade-proposal/v1` | `TradeProposalEnvelope` JSON Schema |
| GET | `/contracts/compatibility` | Compatibility Policy |
| GET | `/decisions/{decisionId}/envelope` | 저장된 판단의 v1 envelope |

만들지 않는 라우트: `POST /orders`, `/buy`, `/sell`, `/cancel`, `/broker/*`, `/live/order`. ATS로 push하는 POST도 없습니다.

1차 완성 흐름:

```
Market Data + External Event Data
    → Normalization
    → Event Intelligence
    → Market Context
    → Feature Engine
    → Long/Short Analysis
    → Horizon Selection
    → Capital/Policy Assessment
    → TradeProposal
    → Decision Journal
    → Replay/Evaluation
    → Shadow Execution
```

이 경로에서 실제 주문은 0건입니다. Shadow Execution은 가상 체결만 만들고 live order로 바뀌는 코드 경로가 없습니다.

## Shadow Trading

AI 판단을 **가상 계좌**에서 평가하는 계층입니다. 실제 Broker / KIS / Auto-Trading-system을 사용하지 않습니다.

### Shadow Portfolio

AI 전용 가상 계좌입니다. 시작 현금은 `totalCapital`이 아니라 `aiCapitalLimit`입니다.

- Initial Capital = AI Shadow Sleeve initial capital (`aiCapitalLimit`)
- Reference Total Capital = 전체 계좌 참고값 (`totalCapital`). Shadow 성과의 분모가 아님
- Cash
- Positions (`ShadowPosition`)
- Realized PnL
- Unrealized PnL
- Drawdown

### Shadow Execution

과거 또는 fixture Market Data로 가상 체결을 만듭니다. mid/current price만으로 체결하지 않습니다.

반영하는 마찰:

- spread (없으면 보수적 기본값 10bps. 0으로 두지 않음)
- slippage (유동성이 낮으면 가산)
- fees
- tax (매도)
- liquidity (점수 0.20 미만은 거부. 미지값은 1.0이 아니라 0.35)

BUY 체결가는 mid보다 높고, SELL 체결가는 mid보다 낮습니다. `fillPrice == mid`인 `ShadowFill`은 만들 수 없습니다.

`NO_TRADE` · `TACTICAL_WAIT` · `HOLD` · `EXIT_REVIEW`는 포지션을 열거나 강제 청산하지 않고 skip합니다. `EXIT_REVIEW`는 `FORCE_SELL`이 아닙니다.

### 성과 축

AI 판단과 Shadow 결과를 비교합니다.

- Decision Quality
- Capital Allocation
- Drawdown / max drawdown
- Risk-adjusted Return
- NO_TRADE Performance (건너뛴 뒤 가격이 내리면 양수: 손실 회피)
- Long vs Short Performance
- Market Regime별 Performance

`liveOrdersPlaced`는 항상 0입니다.

### Broker 분리

`ShadowOrder` / `ShadowFill` / `ShadowPosition`은 실제 주문 엔티티와 완전히 분리됩니다.

- id prefix: `sho_` / `shf_` (broker id 아님)
- `convertibleToBroker`는 항상 `false`이며 `true`로 설정할 수 없음
- `to_broker` / `place_order` / `submit` 변환 메서드 없음

조회 전용 HTTP:

| Method | Path | 역할 |
| --- | --- | --- |
| GET | `/shadow/portfolio` | 가상 계좌 스냅샷 |
| GET | `/shadow/performance` | 판단 vs Shadow 성과 |

`POST /shadow/*` 주문 라우트는 없습니다.

## Health

`GET /health`는 다음을 구분합니다.

- MarketDataHealth
- DisclosureHealth
- MacroHealth
- NewsHealth
- LlmHealth
- ExternalDataHealth
- ModelHealth
- DatabaseHealth / PersistenceHealth
- EventPipelineHealth

종합 상태: `HEALTHY` · `DEGRADED` · `UNHEALTHY` · `UNKNOWN`. `UNKNOWN`은 `HEALTHY`로 간주하지 않습니다. 컴포넌트 하나가 UNKNOWN이면 종합도 HEALTHY가 될 수 없습니다.

`GET /`와 `GET /health`는 `runtimeProfile`, `dataMode`, `ordersEnabled=false`, `brokerConnected=false`, `autoTradingSystemConnected=false`를 노출합니다.

DecisionReadiness (`READY` / `DEGRADED` / `BLOCKED` / `UNKNOWN`)는 TradeProposal 생성 전 게이트입니다. 필수 Market Data unavailable/stale이면 신규 BUY가 금지됩니다. External provider 부분 장애는 overall HEALTHY로 숨기지 않고 `DEGRADED`로 남깁니다.

## Fail-Closed 원칙

- Entry 정보 없음 ≠ 좋은 진입 시점 (`TACTICAL_WAIT`)
- CapitalContext 없음 → `missing_conservative()` → deployable capital 0 → 신규 BUY 금지
- Live-compatible profile에서 Portfolio/Risk unknown → UNKNOWN → 신규 BUY 금지
- Missing Data is not Zero. Missing Context is not Unlimited.
- `NO_EVENT` ≠ `DATA_UNAVAILABLE`
- `NO_TRADE` is a valid successful outcome
- AI는 주문 권한을 갖지 않습니다

## 향후 통합 Contract

AI Agent는 **TradeProposal Producer**, 자동매매 시스템은 향후 **TradeProposal Consumer**입니다. 지금은 계약만 고정하며 Auto-Trading-system과 연결하지 않습니다.

- Schema: `ai.trade-proposal.v1`
- 문서: `docs/INTEGRATION_CONTRACT.md` (Versioning, Compatibility, REST vs Broker vs Shared Package, Sequence, Migration)
- Encoder: `envelope_from_proposal` — 로컬 JSON만 만들고 전송하지 않음
- `isOrder`는 항상 `false`. PAPER/REAL 주문 경로 없음



