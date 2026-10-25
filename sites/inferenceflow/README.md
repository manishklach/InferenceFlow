# InferenceFlow showcase

Buildless, responsive product showcase deployed with Sites. Source assets live in `dist/`.

The execution widget is an explicitly labeled browser replay of the verified MVP recording. It never contacts a GPU, payment provider or control plane. The seven screenshots, synthetic evidence JSON and integration guide were copied from the InferenceFlow repository's recorded walkthrough; no private runtime state, credentials or real customer content is included.

## Preview

```sh
python -m http.server 8093 --bind 127.0.0.1 --directory dist
```

## Behavior checked

- Single-request replay: reserve 54 microUSD, capture 36, release 18.
- Three-request replay: reserve 142 microUSD, capture 88, release 54.
- Screenshot navigation and full-size accessible dialog.
- Python/cURL tabs, keyboard switching and copy action.
- Mobile navigation and no horizontal page overflow at a 390px viewport.
- Downloadable guide and same-origin evidence assets.

The FastAPI, PostgreSQL, scheduler and GPU services retain their separate deployment path. This Site does not claim that real GPU or external payment integration has been validated.

Hosting identity is tracked in `.openai/hosting.json`; preserve it when updating this Site.

## Engineering blog

- [Blog](https://inferenceflow-execution.abc123xyza.chatgpt.site/blog/)
- [What If AI Inference Didn't Have to Be Instant?](https://inferenceflow-execution.abc123xyza.chatgpt.site/blog/what-if-ai-inference-didnt-have-to-be-instant/)

Published October 23, 2026, by The InferenceFlow Team. Full editorial source: `content/first-engineering-post.md`. The static article and index live in `dist/blog/`; diagrams and social image sources live in `dist/assets/blog/`. Future posts can follow the same directory-per-slug structure and add a card to the index. Keep canonical URLs and structured data aligned with each actual publication date. No analytics were added. Site audience remains owner-private; SEO metadata does not make private content discoverable.

### Validation

No build step is needed. For repeatable checks, install `beautifulsoup4 markdown playwright`, then `python -m playwright install chromium`. Start the preview on port 8095 (`python -m http.server 8095 --bind 127.0.0.1 --directory dist`), then run `python tests/check_blog.py`. Screenshots go into ignored `.qa/`. Checks cover full source paragraph fidelity, eight main sections, local links/assets, metadata, desktop/mobile layout, image loading, navigation, single/batch replay, walkthrough dialog and language tabs/copy.

The article distinguishes the engineering vision from measured results: real GPU benchmarks remain pending, the 60-minute target is not an SLA, and vLLM owns continuous batching. No backend, billing or GPU configuration is changed by this publication.

## Published validation fixes and compute rates

The October23 follow-up adds canonical/social metadata, explicit prototype copy, stronger label contrast and private indexing directives. Those retained changes and the GPU/CPU rates page were published through Sites; the latest verified deployment is version 5, managed source commit `a1d27df7ebb46c710aaac4763ec171e2886d87f3`. GitHub commits alone do not publish Sites.

The main navigation now links to [GPU Hourly Rates](https://inferenceflow-execution.abc123xyza.chatgpt.site/gpu-hourly-rates/), with all named RunPod GPU catalog entries across Community/Secure, search/stock filters, per-model history and daily summaries. The same page includes [CPU rates](https://inferenceflow-execution.abc123xyza.chatgpt.site/gpu-hourly-rates/#cpu-rates), six CPU Pod families, per-vCPU hourly units and estimated 2–32-vCPU instance costs. Availability is explicitly measured at two vCPUs only.

`dist/gpu-hourly-rates/` is a buildless page. It reads public `docs/gpu-rates/observations.jsonl` and `docs/cpu-rates/observations.jsonl` from this repository's main branch, falling back to labeled bundled snapshots. Valid raw observations are retained; invalidated renderer replays are excluded from graphs/exports, and missing collections stay unknown. Hourly collection is a local Codex follow-up, dependent on app/connector access. It updates scoped data files rather than redeploying the site. No RunPod credential is shipped to the browser. B300 Secure $8.99/hour and CPU3 Compute-Optimized $0.03/vCPU-hour were verified in the live page on October25.

Validation: JavaScript syntax checks passed, browser search matched B300, CPU selection correctly converted eight vCPUs to $0.24/hour, native Sites publication succeeded and the deployed page read both GitHub histories. [Second GPU backend experiment](../../docs/validation/2026-10-25/second-gpu-report.md) is separate: 410 successes, recovery/accounting evidence, no large-run or commercial-readiness claim. The site audience is unchanged.
