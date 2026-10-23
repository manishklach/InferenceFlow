# Quality report — October23, 2026

## Final results

- Full PostgreSQL-backed suite: **113 passed,1 real-GPU test skipped**,86.73s, one Starlette/AnyIO deprecation warning. Python3.12/Linux, isolated inferenceflow_batching_test only. Includes API lifecycle, tenant isolation/concurrent accounting, stale generation/lease recovery, v2 admission/fairness/adaptive rollback, mock HTTP overlap, provider contracts, sequential/fixed/adaptive tooling, exact-pod guard and economics assumptions.
- Ruff: apps/packages/scripts/tests passed. Mypy: packages/apps,34 source files passed. compileall apps/packages/scripts passed. OpenAPI re-exported for telemetry schema.
- Bash launch.sh syntax passed after correcting Windows CRLF; proposed payload regenerated from current sources. No GPU image build/runtime execution was attempted. Existing image digest was independently read from Docker registry.
- CPU-only mocked runner exercised1000 requests and ten100-request submissions for both fixed and sequential configurations. Missing/unsafe execution gates and mocks are tested, not paid inference. Provider and interruption fixtures use synthetic accounts/data.
- Site is buildless HTML/JS: no framework build necessary. Existing browser regression script passed desktop/mobile layout, full article fidelity, links, assets, navigation, single/batch replay, screenshot dialog, language tabs/copy and no JavaScript errors. Prepared source received a second static check of every local link/fragment, oneh1, canonical and private indexing directives. In-app browser independently accessed the LIVE homepage/index/article, checked menu/back navigation, keyboard skip and replay SUCCEEDED, captured desktop/mobile screenshots and loaded both SVGs.
- All15 live static assets returned200, total831292bytes. HTML/linked-route evidence and exact public GPU quote payloads saved without credentials. Browser network performance entries were unavailable; no HAR/Lighthouse or full WCAG certification is claimed.

## Failures resolved

An initial Windows system-Python unittest attempt lacked psycopg; rerunning with the project's installed virtualenv passed. Some WSL test launches raced PostgreSQL startup and failed fixture connection before any test; waiting for pg_isready resolved them. Final full suite passes. A new mocked-runner test initially had an undefined local policy variable; fixed and rerun. New compact Python source initially failed Ruff formatting rules; formatted and rerun. Direct Bash validation exposed CRLF in launch.sh; normalized LF and verified. None of these failures is counted as GPU evidence.

## Safety and remaining validation

No billable resources, real payments, public beta, automatic provisioning, optional-provider execution or production data modifications. Customer reservation/rate/capture algorithms and ledger schema unchanged. Runtime validation adds a reviewed private experiment gate; watchdog no longer deletes untracked same-prefix pods. New guard has explicit execution/receipt gates and mocked DELETE verification; no guard was armed or real resource deleted. A software guard can fail during networking/auth/host outages and does not create a provider hardcap.

Remote staging HTTPS/OIDC, independent provider-key read/delete readiness, image/dependency vulnerability assessment, real GPU memory/kernel/canary, measured batching/recovery, actual invoice economics, backup/restore and operational drills remain outstanding. Optional providers lack live credentialed validation, health/lifecycle integration and calibrated routing. The prototype is NOT production-ready. No20–30% savings or sub-hour SLA is claimed.

## Source and release

Development branch codex/readiness-validation builds on the committed blog work. Its PR is targeted at codex/engineering-blog so the GPU/readiness work stays separate from PR4; merge blog first before retargeting readiness to main. Website fixes remain unpushed to managed Sites and unpublished, as required by Phase1.5. GitHub source changes alone do not deploy the Site. No release has been published; the future private-alpha checklist records the remaining gates.

See [changed-files.txt](changed-files.txt) for the exact file list, [readiness report](readiness-report.md) for current state/approval package, [website report](website-report.md) for screenshots and issue table, and [unexecuted economics status](first-gpu-status.json).
