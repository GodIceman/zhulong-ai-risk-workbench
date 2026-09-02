# Zhulong model and decision card

## Intended use

Zhulong is intended for local portfolio demonstrations, research exploration, and human-review triage. It is not qualified for judicial, disciplinary, moderation, authorship, or commercial authenticity decisions.

## Image branch

| Item | Value |
| --- | --- |
| Primary model | `Junwei-Xi/Dual-Data-Alignment` |
| Primary revision | `26afc31e6b40c312c3fd42c05a758be62446215b` |
| Auxiliary model | `OwensLab/commfor-model-224` |
| Policy | `image-provenance-policy-v10` |
| Decision behavior | Strong high-risk output generally requires independent model consensus when no explicit generator metadata exists |

The local 62-image regression set produced zero high-risk false positives under the release-aware policy, but explicit AI detections covered only a minority of AI samples and overall abstention was high. This small, locally curated set cannot establish general accuracy.

Known limitations include screenshots, game imagery, unseen generators, compression, local editing, inpainting, compositing, and domain shift. No region localization is provided.

## Video branch

| Item | Value |
| --- | --- |
| AEGIS model revision | `95b71346cec650165e6ad3fb20ed9e80f4b6702a` |
| AEGIS code revision | `d86a774fd971954a023e1cd00ed7ff5b2575e0d1` |
| AEGIS checkpoint SHA-256 | `7df233979f9d3ef340e101d0d635a4d074577d43e6d1591d677cde31f80e44ba` |
| AEGIS strong threshold | `0.90` |
| D3 revision | `c798fbc57fe0c4198d63a73732c2c0f9e4b4816c` |
| D3 support threshold | `0.0162` |
| LNCLIP-DF model revision | `9a6857ec642deb57373c5437be803a199468b8c6` |
| LNCLIP-DF threshold | `0.50`, with at least `0.50` face-hit ratio |
| Policy | `positive-only-video-ensemble-v1` |

AEGIS alone is not trusted because of observed domain-shift false positives. A fully generated-video warning requires AEGIS strong evidence and D3 support. D3 can never trigger that warning alone. LNCLIP-DF is a separate face-manipulation branch.

In local evaluation, the full-generation branch prioritized low false positives but had low coverage; it did not meet the project's product-release gate. Negative results are abstentions.

WaveRep is excluded from the default decision chain because of poor local domain behavior and its informational/nonprofit-only license.

## Chinese writing-style branch

| Item | Value |
| --- | --- |
| Model | `AnxForever/chinese-ai-detector-bert` |
| Revision | `ea3fca0fca3fd1b8f304812171232d115cd65a75` |
| Policy | `text-ai-style-policy-v1` |
| High document threshold | `0.80` plus multi-segment consensus |
| Low document threshold | `0.20` plus multi-segment consensus |

Scores describe classifier-specific writing-style signals, not the probability that an author is AI. Short text, mixed authorship, rewriting, unfamiliar genres, and future models may cause errors. Independent generalization qualification is not complete.

## Safety policy

- Do not label uncertain inputs as authentic.
- Do not treat user-declared provenance as verified evidence.
- Do not form a conclusion when a required model failed.
- Show model scope, evidence conflicts, and recommended human review.
- Keep model/runtime qualification separate from repository-source licensing.

## Data and reproducibility

Evaluation media is intentionally not published because it includes real photos/videos, device metadata, third-party datasets, and materials with separate terms. Public scripts document portions of the evaluation and acquisition process. Model weights are downloaded from pinned upstream revisions and are not committed.
