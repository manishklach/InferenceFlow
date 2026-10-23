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

## Pending validation fixes

The October23 follow-up adds canonical/social metadata, explicit prototype copy, stronger label contrast and private indexing directives. These changes are prepared, not deployed; publication requires the user confirmation requested by that task. Live source remains managed Sites commit809105c135da7388b49c5aa743693876d04b7724. See the repository [validation report](../../docs/validation/2026-10-23/website-report.md). GitHub commits do not publish Sites.
