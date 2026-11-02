# Hardening audit — November 2, 2026

## Findings and changes

| Finding verified in the working tree | Resolution |
| --- | --- |
| `get_or_create_user` automatically opted users in; handlers ignored opt-out | Default false; fresh explicit consent timestamp required at collection and both scoring entrypoints |
| Existing true flags could be automatic rather than consent | Legacy records preserved but excluded; `/optin` starts a new eligibility period |
| Startup dropped all tables | Removed; initialization only at explicit startup, missing tables created safely, known legacy columns added without row updates |
| `.env` loaded after the engine's configuration was read | Load configuration before engine creation |
| Score queries mixed channels from multiple servers | Restrict to current guild, requester-readable channels, and active allowlist |
| Cached scores omitted consent/channel scope and expiry | Preserve old cache records but stop reading/writing them |
| Explanations included raw message excerpts | Remove excerpts and make scores/leaderboards ephemeral |
| Per-message classification ran even though its response was commented out | Remove unused API calls; score only on demand |
| README claimed GPT-5 Nano; working copy used GPT-3.5 Turbo | Document configurable `OPENAI_MODEL`, default GPT-4.1 Mini; preserve prompt rules, ten-message sample and 1.5 multiplier |
| README promised heuristic fallback but unavailable classifications produced a misleading neutral score | Use existing heuristic algorithm when no sample is classified; expose actual successful counts for partial failures |
| Exception bodies could include sensitive payloads | Replace message, API, and command error handling with generic diagnostics |
| New local usernames, full URL features, and score examples increased stored data | Stop adding usernames, store domain-only link features, avoid new cached results/excerpts |
| Server administrators could change global heuristic settings | Namespace new config overrides by guild; preserve existing global settings as defaults |
| Fallback weights could produce scores outside advertised bounds | Clamp final heuristic score to 0–100 |
| IDE/macOS metadata tracked; Docker copied private local files | Stage metadata untracking while preserving copies; add ignore rules and `.dockerignore`; mount-aware Docker DB default |

## Validation and secret review

- Offline unittest suite covers collection/consent, preference commands, legacy rejection, re-opt-in boundaries, private/other-server channels, leaderboards, explanations, sample limits, arithmetic, fallback, scoped configuration, API payload/model selection, safe diagnostics, additive migrations, persistence, import safety, and mocked entrypoint startup.
- Synthetic databases only. The existing local database was not opened, migrated, reset, or otherwise inspected. Its schema and contents are intentionally outside this review.
- Installed runtime imports and `pip check` pass in the available local virtual environment. Tests use Python's standard `unittest`; no new test dependencies are required. Docker build and live integrations were not exercised.
- Heuristic secret scan covers all three commits reachable from local Git refs plus current tracked/unignored files. Patterns cover common OpenAI, Discord, GitHub and AWS credentials, private keys, credential-bearing URLs, and literal assignments. Local `.env` credentials are compared privately against those files/blobs; values are never printed. No suspected real secrets or local-credential matches were found. A synthetic test placeholder was reviewed and shortened to avoid a false positive.
- `.env` and SQLite filenames/journals are ignored; none are tracked. `config.yaml` contains scoring defaults, not credentials or user/server identifiers. Existing IDE/macOS blobs remain in history; untracking does not remove them from prior commits.
- No remote-only refs, hosted GitHub artifacts, forks, unreachable objects, or external deployment logs were inspected. The scanner is heuristic, not a full credential audit or a dependency-vulnerability scanner. No rotation or history rewriting was performed.

## Remaining operator work and risks

1. Back up the private database before first startup; test the additive migration on a protected copy. The migration was tested against synthetic legacy and current SQLite schemas. No migration has been applied to the real database. Non-SQLite databases/drivers and their identifier types have not been validated; SQLite is the supported setup documented here.
2. Communicate the consent model and identify an operator contact in each participating server. Everyone must run `/optin` again. Consent covers all servers served by the instance. Other members can request aggregate scores for participants.
3. Establish a concrete retention/deletion policy before further production collection. Raw text and legacy data remain locally until an operator removes them with authorization; the query window is not a purge. Protect database/backups and handle verified removal requests separately. No private records have been deleted.
4. Review OpenAI's applicable data policy, account access, and the selected model before a controlled test-server rollout. Message text itself may contain names, identifiers, URLs, or secrets. `store=False` does not imply zero retention. No live API/Discord access or production rollout occurred in this task.
5. Add workload limits, async/background scoring with consent-safe coordination, and a correctly scoped cache before high-traffic operation. Current synchronous API calls can block the Discord event loop; repeated commands incur costs. Requests use a 15-second timeout and no SDK retries per call, but a leaderboard can still take much longer. Run only one process per database.
6. Review the subjective classification prompt and existing fraternity substring rule before treating scores as meaningful. Prompt injection, stereotyping, stochastic results, partial API failures, and heuristic/LLM score differences remain limitations. Message edits/deletions and later reactions are not synchronized.
7. Consider versioned migrations, dependency locking/vulnerability scanning, automated CI, and an actual license file before presenting broader deployment guarantees. No license file is present, so the old unsupported MIT claim was removed.

No deployment, commit, push, visibility change, credential modification, history rewrite, or deletion of existing private data was performed. Metadata removals are staged in the Git index because the requested cleanup explicitly requires untracking; local copies remain intact. Other changes are left for review.
