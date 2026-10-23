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

## Published preview and source

[Live Sites preview](https://inferenceflow-execution.abc123xyza.chatgpt.site/) (owner-private access). This directory mirrors the deployed showcase source at commit `f158ba612d7700650c292e9f0daf641c1d26311b`. Repository visibility does not change Site access.

From the repository root, preview with `python -m http.server 8093 --bind 127.0.0.1 --directory sites/inferenceflow/dist`. Preserve the existing Sites project identity when publishing updates; GitHub pushes alone do not deploy the Site or the platform backend.
