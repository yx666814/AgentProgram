# Backend Stage 4 Traceability

> Status: completed and verified on 2026-07-15. This is the requirement-to-code-to-test index for Stage 4.

## Delivery

| Requirement | Implementation | Verification |
| --- | --- | --- |
| ModelProfile and room assignment | `domain/model_runtime/models.py`, configuration service, authenticated REST, `0008_model_runtime.py` | profile/assignment API path and migration tests |
| SecretStore boundary | `ports/secrets.py`, unavailable production default, in-memory test implementation | independent credential refs and byte-level database/output secret scan |
| Provider adapters | cancellation-aware OpenAI-compatible and Anthropic SSE parsers using `httpx` | deterministic MockTransport protocol and usage tests |
| Durable output and usage | SHA-256 `ModelOutputStore`, ModelCall and UsageRecord repository | deduplication, tamper detection, token totals, restart recovery tests |
| Prompt composition | frozen global policy, RoleCard, StageContract, subrole, project instructions, runtime, user precedence | Fake Model captured invocation and independent reviewer prompt tests |
| Context isolation and summaries | room-checked ContextBuilder and bounded RollingSummaryBuilder | cross-room rejection and recent-message preservation tests |
| P0/P1/P2R | primary P0, independent Reviewer A/B P1, primary P2R reconciliation | four-call formal run, dual-review gate, final output and usage assertions |
| Partial failure and idempotency | structured partial terminal state and unique `(room_id, request_key)` | reviewer failure, duplicate request and parameter mismatch behavior |
| Streaming and cancellation | authenticated NDJSON frames, active-run registry, adapter cancellation event | REST stream contract, cancellation propagation, terminal call/run state tests |
| Runtime closure | lifecycle services, content-addressed output, SQLite restart reconstruction | restart query/output test and complete Stage 1-3 regression |

## Invariants

- Database rows and events never contain API-key values; model profiles contain only `credential_ref` and `masked_hint`.
- Each room permits one active AgentRun. Stage transition and reopen are blocked until it reaches a terminal state.
- Formal runs require exactly one Primary and two distinct Reviewer profiles. Reviewer prompts are independent and P2R receives both results only after P1 completes.
- A request key cannot trigger duplicate model calls. Reuse with changed formal parameters is rejected.
- Provider calls run outside SQLite transactions. Call/run state, output metadata, usage, and committed events use short shared-lock transactions.
- Client disconnect and explicit cancellation propagate to the adapter and persist `cancelled` for the active call and run.
- Model output files are UTF-8, size-bounded, atomically published, hash-verified, and addressed by SHA-256.

## Verification

- Ruff format: 210 files formatted.
- Ruff lint: passed.
- Mypy strict: 120 source files passed.
- Pytest: `707 passed, 12 skipped`.
- One non-failing third-party warning remains from FastAPI's current TestClient compatibility wrapper.
