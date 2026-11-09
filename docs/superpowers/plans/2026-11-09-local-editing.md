# Local Editing Upgrade Implementation Plan

> For agentic workers: use superpowers:subagent-driven-development for independent implementation and final review. Existing user confirmation authorizes this plan.

**Goal:** Upgrade the customer repository to a local-material Codex + ChatCut workflow.
**Architecture:** Migrate tracked local-production modules at fixed upstream revision. Remove discovery/download modules and enforce local-only intake; preserve legacy tools. Add verified ChatCut export delivery registration to the task model.
**Tech Stack:** Python 3.12+, FastAPI/Pydantic/SQLAlchemy, MCP, FFmpeg, ChatCut Desktop, uv, pytest.
**Spec:** docs/superpowers/specs/2026-11-09-local-editing-design.md

## Global Constraints

- Customer repository only; source repository remains unchanged.
- Local customer footage only; no search/download or collector dependencies.
- Keep old rendering tools and tests; default customer route is Codex + ChatCut Desktop.
- Preserve real source hashes, per-video progress, resumability, original files, and truthful QA scope.
- No fabricated user approvals; no publication or global account/config changes.
- Python >=3.12; uv.lock and pyproject.toml form the installation contract.

## Tasks

- [x] 1. Clone customer repository, branch, archive original; migrate tracked local modules/tests and extract reference validation independently of collector.
- [x] 2. Core: change workflow/api.py, cli.py, mcp_server.py, orchestration/pipeline.py and tests; reject URL sources and collection inputs including persisted jobs, remove collection stages/capabilities, preserve local jobs and missing-material status. Run tests for API/CLI/MCP/pipeline and local-only regressions.
- [x] 3. Desktop delivery: add workflow/desktop_delivery.py and direct CLI script plus tests. Consume job-owned imported sources and actual ChatCut export files; validate MP4/SRT, bind hashes and evidence, copy atomically to per-job delivery, persist per-item status/count, reject foreign assets, stale inputs, bad subtitles and overwrite conflicts. Run real synthetic-media delivery tests.
- [x] 4. Documentation: update README, DEPLOYMENT, AGENTS, editing/setup skills, native ChatCut instructions and config templates. Remove collection instructions; explain customer local-material flow and draft/debug distinction. Verify commands and relative links.
- [x] 5. Packaging: merge runtime dependencies, regenerate lock; remove legacy downloader/tool installer requirements, update capabilities, version, CI and manifest. Run frozen dependency installation, lint, full relevant suite, synthetic end-to-end smoke and readonly ChatCut health where available.
- [x] 6. Review final source removal/integration, resolve findings, record exact verification and remaining live acceptance limits. Leave a reviewable local branch ready for user-authorized upload.

## Verification evidence

2026-11-09: full default suite 459 passed / 3 Windows-specific skips; lint, frozen environment, config parse and independent review passed. See UPGRADE-VALIDATION.md for exact scope and live acceptance limitations. Branch preserved locally, no push or release.
