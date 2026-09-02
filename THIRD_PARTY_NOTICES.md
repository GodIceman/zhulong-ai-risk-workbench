# Third-party notices

The repository's MIT license applies only to original Zhulong source. Model artifacts, datasets, research code, and package dependencies remain governed by their own upstream terms. No model weight or evaluation dataset is redistributed here.

| Component | Role | Pinned source/revision | Upstream terms noted by the project |
| --- | --- | --- | --- |
| Dual Data Alignment | Primary image signal | `Junwei-Xi/Dual-Data-Alignment` @ `26afc31e6b40c312c3fd42c05a758be62446215b` | Apache-2.0 metadata in the upstream release |
| Community Forensics | Auxiliary image signal | `OwensLab/commfor-model-224` at the pinned revision in code | MIT metadata in the upstream release |
| Chinese AI detector BERT | Chinese writing-style signal | `AnxForever/chinese-ai-detector-bert` @ `ea3fca0fca3fd1b8f304812171232d115cd65a75` | Model metadata says MIT; associated dataset documentation limits use to academic research, so commercial qualification remains false |
| AEGIS | Fully generated-video primary signal | [source](https://github.com/MusapYildiz/ai_video_detection_benchmark) @ `d86a774fd971954a023e1cd00ed7ff5b2575e0d1`; checkpoint @ `95b71346cec650165e6ad3fb20ed9e80f4b6702a` | MIT declaration; dependency and provenance review still required before product release |
| D3 | Temporal consensus guard | [source](https://github.com/Zig-HS/D3) @ `c798fbc57fe0c4198d63a73732c2c0f9e4b4816c` | MIT declaration |
| LNCLIP-DF | Face-manipulation signal | model @ `9a6857ec642deb57373c5437be803a199468b8c6` | Detector repository declares MIT; processor-license metadata requires further review |
| WaveRep | Excluded research candidate | [source](https://github.com/grip-unina/WaveRep-SyntheticVideoDetection) @ `0fd6010759c14b572b7842a28fa9f85fe1ddd2fd` | Custom informational/nonprofit-only license; not part of the default runtime decision chain |

Pinned identifiers document the locally evaluated configuration; they are not an endorsement or a claim that every transitive dependency is cleared for commercial deployment. Review the current upstream terms before using any model or dataset outside a local research/portfolio context.
