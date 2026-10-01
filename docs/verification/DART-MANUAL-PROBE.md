# DART 단독 수동 검증

이 문서는 10.5.8 인수 기록을 대체하지 않는다.
기존 판정과 6건 증거는 `docs/verification/10.5.8-ACCEPTANCE-CLOSEOUT.md`를 본다.

최종 판정: **DART 단독 수동 검증 도구 준비 완료 — 실제 연결 미검증**

실제 연결 성공, 실운영 준비 완료, ATS 연동 준비 완료로 확대하지 않는다.
아래 live 조회 명령은 작성만 한다. 이 저장소 작업에서는 실행하지 않는다.

Live news revision E2E와 uvicorn 실부하는 미검증으로 유지한다.

## Health 상태 조회

`GET /health`와 `GET /providers/health`는 관측 결과만 읽는다.
collector.collect / LLM / 외부 HTTP를 호출하지 않는다.

- 아직 관측하지 않은 공급자: UNKNOWN (HEALTHY로 추정하지 않음)
- scheduled 미설정: NOT_CONFIGURED
- `lastObservedAt`과 `observationStale`은 마지막 관측 시각과 오래됨을 구분한다
- `scopedToDecisionId`는 항상 null이다. 특정 판단은 `GET /decisions/{id}`
- 조회는 diagnostics / circuit / last_* 를 변경하지 않는다

실제 연결 확인은 아래 DART probe의 `--live`처럼 **명시적** 실행이다.
health에 숨겨진 probe는 없다.

## 설정 점검 (네트워크 없음)

```bash
python -m ai_investment_agent.cli.dart_probe --ticker 005930
```

또는 `ai-dart-probe --ticker 005930`.

기본 동작은 설정 점검이다. Market / Macro / News / LLM / AnalysisService는
생성하지 않는다.

필요한 환경 변수 **이름**:

- `DART_API_KEY` (값은 출력하지 않음, 설정 여부만)
- `DART_CORP_CODE` 또는 `DART_CORP_CODE_<TICKER>`
- `DART_BASE_URL` (기본 `https://opendart.fss.or.kr/api`)
- 선택: `DART_CONNECT_TIMEOUT`, `DART_READ_TIMEOUT`, `DART_TOTAL_TIMEOUT`,
  `DART_MAX_RETRIES`, `DART_RPS`

성공 시 outcome=`CONFIG_CHECK_ONLY`, 종료 코드 **3**.
이를 실제 연결 성공으로 보지 않는다.

## 사용자가 실행할 실제 DART 조회 (여기서 실행하지 않음)

```bash
python -m ai_investment_agent.cli.dart_probe --ticker 005930 --live
```

`NO_NETWORK=1`이면 `--live`여도 차단되고 종료 코드 **2**.

호출 상한 (collector 상한을 넘지 않음):

- page cap 10 (collector max 50)
- page size 100
- retry max 2
- total timeout 15s

## 종료 코드

| 코드 | outcome | 의미 |
| --- | --- | --- |
| 0 | `LIVE_OK` | 실제 응답 정상 수신 |
| 0 | `LIVE_NO_EVENT` | 정상 무공시 (013). 성공적인 조회 |
| 2 | `NETWORK_BLOCKED` | `NO_NETWORK=1` 차단 |
| 3 | `CONFIG_CHECK_ONLY` | 설정 점검만 완료. 연결 성공 아님 |
| 4 | `LIVE_DEGRADED` | 부분 수집. 완전 수집 성공 아님 |
| 5 | `FAILED` | 인증/네트워크/스키마/회사 매핑/설정 누락 |

단독 probe 성공을 전체 판단 파이프라인 성공으로 확대하지 않는다.
`judgmentPipelineRun`은 항상 false이다.

## 증거 저장

```bash
python -m ai_investment_agent.cli.dart_probe --ticker 005930 --live \
  --write-evidence docs/verification/redacted-evidence/dart-probe-005930.json
```

기존 파일이 있으면 덮어쓰지 않고 종료 코드 5.
원문 응답, 인증 헤더, `crtfc_key`가 들어간 URL은 출력·저장하지 않는다.

JSON 필드: commitSha, provider, collector, ticker, corpCode,
requestedAt, receivedAt, status, errorCode, attemptCount,
pagesFetched, paginationComplete, rawRowCount, uniqueRowCount,
accessibleCount, networkExecuted.

## 정상 무공시와 장애

- `LIVE_NO_EVENT` / status `NO_EVENT`: 인증·스키마·회사 매핑이 통과하고
  해당 기간 공시가 없음. 조회 성공.
- `FAILED` + `MISSING_CREDENTIAL` / `HTTP_401` / `TIMEOUT` /
  `INVALID_JSON` / `COMPANY_MISMATCH` / `MISSING_CORP_CODE`: 장애.
- `LIVE_DEGRADED`: 일부 페이지 실패. 완전 성공이 아님.

## 다음 단계에서 확인할 실제 인증·응답 항목

이 단계에서는 실행하지 않는다.

- `DART_API_KEY`가 OpenDART에서 유효한지
- `DART_CORP_CODE_005930` (또는 대상 ticker)가 응답 `corp_code`/`stock_code`와 일치하는지
- `rcept_dt` 날짜 정밀도와 `sourceReceivedAt` 실제 수신 시각이 구분되는지
- 다중 페이지 `total_page` 완결 및 `rcept_no` 중복 없음
- 013 무공시가 DATA_UNAVAILABLE으로 위장되지 않는지
