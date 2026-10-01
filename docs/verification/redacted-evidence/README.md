# Redacted evidence (no secrets)

Store operator-captured screenshots or JSON dumps from a **manual**
provider run here. This directory is a placeholder; do not commit API
keys, bearer tokens, `crtfc_key` values, or raw `.env` files.

Suggested filenames after a manual run (values redacted):

- `evaluate-<ticker>-<utc>.json` — response with `decisionId`, `dataMode`,
  `isOrder`, `analysisAsOf`, `providerHealth`, `readiness`
- `providers-health-<utc>.json` — `GET /providers/health`
- `smoke-<ticker>-<utc>.txt` — stdout of `ai-observation-smoke` after
  secret masking

Never paste `DART_API_KEY`, `LLM_API_KEY`, `MARKET_DATA_API_KEY`,
`NEWS_API_KEY`, or `MACRO_API_KEY` values into these files.
