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
  intelligence/  # 이번 단계는 fixture regime assessor
  features/      # 이후 단계
  scanner/       # 이후 단계
  agents/        # JudgmentAgent 오케스트레이션
  horizon/       # LONG_TERM / SHORT_TERM 매핑
  decision/      # 순수 DecisionEngine
  capital/       # CapitalContext 해석. 누락 시 0, 무한 자금 아님
  policy/        # 하드 게이트 (UNKNOWN → NO_TRADE)
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

## Collection layer

Market Data and External Intelligence are collected independently. They are never mixed in one collector.

- Market Data: OHLCV, Current Price, Volume, Index, FX, Rates, Commodity, Volatility, Liquidity
- External Intelligence: corporate disclosure, domestic/foreign news, central bank, government policy, economic indicators, geopolitics, industry events, corporate events
- Corporate actions are fixture-only (no live feed)

Every collected record carries `eventOccurredAt`, `publishedAt`, `sourceReceivedAt`, `collectedAt`, `normalizedAt`, `analyzedAt`, `tradableAt`. Replay/backtest may use a record only when `tradableAt` and `sourceReceivedAt` are ≤ `as_of`.

Collectors return an explicit `CollectionStatus`. `NO_EVENT` (successful empty feed) is not `DATA_UNAVAILABLE` (API/feed failure). Empty arrays are never implied success.

Freshness classes: `ULTRA_FAST`, `INTRADAY`, `DAILY`, `LONG_HORIZON`.

