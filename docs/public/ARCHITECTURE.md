# Architecture

## Runtime topology

```text
Browser (Vue 3, Pinia, hash routing)
        |
        | HTTP on loopback
        v
Unified Media API :5002
        |
        +-- Image + Chinese text service :5004
        |
        +-- Video ensemble service :5003
```

The browser calls only the unified API. Model services are implementation details and bind to `127.0.0.1` by default.

## Responsibilities

### Frontend

- validates basic file type and size before creating a task;
- routes text, image, and video inputs into a shared workbench;
- renders task progress, explicit abstention, evidence, and limitations;
- stores optional local user and task-history metadata in IndexedDB;
- switches to a fixed-fixture, no-upload demo mode during Pages builds.

### Unified Media API

- enforces upload, pixel-count, task-ID, origin, and report-path boundaries;
- owns task state and product-facing report contracts;
- treats user source hints as untrusted context;
- delegates inference to model services;
- returns `failed` or `uncertain` instead of manufacturing an authenticity conclusion.

### Image and text service

- loads pinned image and Chinese-text model revisions;
- emits raw model signals and runtime/license qualification metadata;
- does not own the final user-facing provenance decision.

### Video service

- samples the video once for multiple branches;
- keeps face manipulation and fully generated-video evidence separate;
- permits D3 only as a supporting consensus guard;
- never uses a negative result to certify authenticity.

## Task lifecycle

```text
received -> validating -> routing -> extracting -> detecting -> aggregating
         -> completed | uncertain | failed
```

Uploaded temporary media is removed at the end of processing. Reports remain in memory unless persistence is explicitly enabled.

## Static Pages build

The Pages workflow sets:

```text
VITE_DEMO_MODE=true
VITE_BASE_PATH=/zhulong-ai-risk-workbench/
```

Demo mode does not call loopback APIs. It displays fixed fictional reports and uses browser object URLs solely for local preview. Hash routing avoids server-side route fallback requirements under the repository subpath.
