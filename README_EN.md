# Zhulong · AI Content Risk Analysis Workbench

[Live demo](https://godiceman.github.io/zhulong-ai-risk-workbench/) · [中文](README.md) · [Privacy](PRIVACY.md) · [Security](SECURITY.md)

> Zhulong is a local-first, multimodal risk-triage prototype. It organizes model signals, provenance clues, and explicit limitations for human review. It is not a general-purpose authenticity certification system.

![Zhulong workbench](docs/assets/overview-desktop.png)

## What it does

- **Images:** combines a DDA primary signal with an independent Community Forensics signal, then considers EXIF, XMP, and unverified source declarations.
- **Video:** requires strong AEGIS + D3 consensus before raising a fully generated-video warning; LNCLIP-DF independently provides face-manipulation signals.
- **Chinese text:** uses a pinned Chinese BERT classifier over representative segments and reports writing-style signals, coverage, and excerpts.

![Risk report](docs/assets/report-desktop.png)

The system abstains when evidence conflicts, a model is unavailable, or the input is outside the evaluated scope. A negative or uncertain result must never be interpreted as proof that content is authentic or human-authored.

## Demo versus local inference

The GitHub Pages site is a static product demo with no model backend:

- selected files remain inside the browser for preview;
- reports are clearly labeled, fixed fictional fixtures unrelated to user input;
- real inference is available only in the locally installed application.

## Local setup

The currently verified environment is Windows 11 with Node.js 20.19+, Python 3.11, Git, and [uv](https://docs.astral.sh/uv/). A compatible NVIDIA GPU is recommended.

Frontend only:

```powershell
Set-Location zhulong
npm ci
npm run dev:frontend
```

Full local demo:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_venv.ps1
powershell -ExecutionPolicy Bypass -File scripts/setup_video_forensics.ps1
./start.bat
```

The first setup downloads several gigabytes of Python/CUDA packages and pinned model artifacts. See the [local setup guide](docs/public/LOCAL_SETUP.md) before starting.

## Architecture and privacy

```text
Vue 3 / Pinia / Vite
        |
        v
Unified Media API :5002
   +-- Image + Text Service :5004
   +-- Video Ensemble Service :5003
```

Services bind to `127.0.0.1` by default. Temporary uploaded-media copies are removed after processing. Reports stay in process memory unless `PERSIST_REPORTS=true` is explicitly enabled. See [architecture](docs/public/ARCHITECTURE.md) and [privacy](PRIVACY.md).

## Evidence limits

- The image policy was calibrated on a small 62-image local regression set and prioritizes low false positives over coverage. It is not a production accuracy claim.
- The video full-generation branch did not meet the project's coverage release gate and remains a conservative portfolio prototype.
- The Chinese writing-style model has not completed an independent generalization evaluation.
- CI covers the production frontend build and API/decision-policy tests that do not require large model weights.

Pinned revisions, thresholds, license gates, and limitations are documented in the [model card](docs/public/MODEL_CARD.md). Evaluation media and model weights are not included in this repository.

## Licensing and collaboration

Original project source is available under the [MIT License](LICENSE). Models, datasets, and runtime dependencies remain subject to their upstream terms; this repository's MIT license does not grant rights to those artifacts. See [third-party notices](THIRD_PARTY_NOTICES.md).

Product definition, interface and interaction design, acceptance, and testing are led by the project owner. Engineering implementation includes AI coding tools working under the owner's direction and review.

Small, testable contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md) first.
