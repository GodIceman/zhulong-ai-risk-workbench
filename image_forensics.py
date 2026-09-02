#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Local AI-generated image detector backends.

The module intentionally keeps the detector independent from Flask so it can be
used by the API and by the small local regression evaluator.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Sequence

from PIL import Image, ImageOps


COMMUNITY_FORENSICS_MODEL_ID = "OwensLab/commfor-model-224"
COMMUNITY_FORENSICS_REVISION = "26afc31e6b40c312c3fd42c05a758be62446215b"
COMMUNITY_FORENSICS_384_MODEL_ID = "OwensLab/commfor-model-384"
COMMUNITY_FORENSICS_384_REVISION = "6076002bf0d9dd37537f965ee2f06f826c333b61"
DDA_MODEL_ID = "Junwei-Xi/Dual-Data-Alignment"
DDA_MODEL_REVISION = "4390d9023899196b437480bb6a441915ef5d816c"
DINOV2_REPOSITORY_REVISION = "7764ea0f912e53c92e82eb78a2a1631e92725fc8"


def choose_torch_device(preference: str = "auto") -> str:
    """Resolve auto/cuda/cpu without failing on machines without CUDA."""
    import torch

    normalized = (preference or "auto").strip().lower()
    if normalized == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if normalized == "cuda" and not torch.cuda.is_available():
        return "cpu"
    if normalized not in {"cuda", "cpu"}:
        raise ValueError("device must be one of: auto, cuda, cpu")
    return normalized


class _CommunityForensicsModel:
    """Build the exact ViT wrapper used by the released checkpoint."""

    @staticmethod
    def create(device: str, input_size: int):
        import timm
        import torch.nn as nn

        class ViTClassifier(nn.Module):
            def __init__(self):
                super().__init__()
                # The released checkpoint contains the full backbone, so no
                # secondary pretrained download is needed here.
                self.vit = timm.create_model(
                    (
                        "vit_small_patch16_224.augreg_in21k_ft_in1k"
                        if input_size == 224
                        else "vit_small_patch16_384.augreg_in21k_ft_in1k"
                    ),
                    pretrained=False,
                )
                self.vit.head = nn.Linear(384, 1)

            def forward(self, pixel_values):
                return self.vit(pixel_values)

        return ViTClassifier().to(device)


class CommunityForensicsDetector:
    """Inference wrapper for the CVPR 2025 Community Forensics 224 model."""

    positive_label = "ai_generated"

    def __init__(self, device: str = "auto", input_size: int = 224):
        if input_size not in {224, 384}:
            raise ValueError("input_size must be 224 or 384")
        self.input_size = input_size
        if input_size == 224:
            self.model_id = COMMUNITY_FORENSICS_MODEL_ID
            self.model_revision = COMMUNITY_FORENSICS_REVISION
        else:
            self.model_id = COMMUNITY_FORENSICS_384_MODEL_ID
            self.model_revision = COMMUNITY_FORENSICS_384_REVISION
        self.device = choose_torch_device(device)
        self.model = None
        self.transform = None

    def load(self) -> "CommunityForensicsDetector":
        import torch
        from huggingface_hub import hf_hub_download
        from safetensors.torch import load_file
        from torchvision import transforms

        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        checkpoint_path = hf_hub_download(
            repo_id=self.model_id,
            filename="model.safetensors",
            revision=self.model_revision,
        )
        model = _CommunityForensicsModel.create(self.device, self.input_size)
        state_dict = load_file(checkpoint_path, device="cpu")
        missing, unexpected = model.load_state_dict(state_dict, strict=True)
        if missing or unexpected:
            raise RuntimeError(
                f"checkpoint mismatch: missing={missing}, unexpected={unexpected}"
            )
        model.eval()

        self.model = model
        self.transform = transforms.Compose(
            [
                transforms.Resize(256 if self.input_size == 224 else 440),
                transforms.CenterCrop(self.input_size),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ]
        )
        # Keep inference deterministic while allowing the CUDA backend to pick
        # efficient kernels for this fixed input size.
        if self.device == "cuda":
            torch.backends.cudnn.benchmark = True
        return self

    def _prepare(self, image: Image.Image):
        if self.transform is None:
            raise RuntimeError("detector is not loaded")
        image = ImageOps.exif_transpose(image).convert("RGB")
        return self.transform(image)

    def predict_images(
        self,
        images: Sequence[Image.Image],
        batch_size: int = 16,
    ) -> List[float]:
        """Return AI-generation probabilities in input order."""
        import torch

        if self.model is None:
            raise RuntimeError("detector is not loaded")
        if not images:
            return []

        tensors = [self._prepare(image) for image in images]
        scores: List[float] = []
        with torch.inference_mode():
            for offset in range(0, len(tensors), max(1, batch_size)):
                batch = torch.stack(tensors[offset : offset + batch_size]).to(
                    self.device,
                    non_blocking=self.device == "cuda",
                )
                logits = self.model(batch).flatten()
                scores.extend(torch.sigmoid(logits).detach().cpu().tolist())
        return [float(score) for score in scores]

    def predict_image(self, image: Image.Image) -> float:
        return self.predict_images([image], batch_size=1)[0]

    def predict_paths(
        self,
        paths: Iterable[Path],
        batch_size: int = 16,
    ) -> List[float]:
        images = []
        for path in paths:
            with Image.open(path) as image:
                images.append(image.convert("RGB"))
        return self.predict_images(images, batch_size=batch_size)


class _DDAModel:
    """Build the DINOv2-L/14 + LoRA graph used by the official DDA release."""

    @staticmethod
    def create(device: str):
        import math

        import torch
        import torch.nn as nn

        class LoRALayer(nn.Module):
            def __init__(self, in_dim, out_dim, rank=8, alpha=1.0):
                super().__init__()
                self.alpha = alpha
                self.rank = rank
                self.lora_A = nn.Parameter(torch.zeros((rank, in_dim)))
                self.lora_B = nn.Parameter(torch.zeros((out_dim, rank)))
                nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))
                nn.init.zeros_(self.lora_B)

            def forward(self, values):
                reduced = torch.einsum("...d,rd->...r", values, self.lora_A)
                expanded = torch.einsum("...r,or->...o", reduced, self.lora_B)
                return expanded * (self.alpha / self.rank)

        class LoRALinear(nn.Module):
            def __init__(self, original_layer):
                super().__init__()
                self.original_layer = original_layer
                self.lora = LoRALayer(
                    original_layer.in_features,
                    original_layer.out_features,
                )

            def forward(self, values):
                return self.original_layer(values) + self.lora(values)

        def get_submodule(model, name):
            current = model
            for part in name.split("."):
                current = current[int(part)] if part.isdigit() else getattr(current, part)
            return current

        def apply_lora(model):
            targets = ("attn.qkv", "attn.proj", "mlp.fc1", "mlp.fc2")
            replacements = []
            for name, module in model.named_modules():
                if isinstance(module, nn.Linear) and any(target in name for target in targets):
                    replacements.append((name, module))
            for name, module in replacements:
                parent_name, child_name = name.rsplit(".", 1)
                setattr(get_submodule(model, parent_name), child_name, LoRALinear(module))
            return model

        class DINOv2Model(nn.Module):
            def __init__(self):
                super().__init__()
                self.model = torch.hub.load(
                    f"facebookresearch/dinov2:{DINOV2_REPOSITORY_REVISION}",
                    "dinov2_vitl14",
                    pretrained=False,
                    trust_repo=True,
                )
                self.fc = nn.Linear(1024, 1)

            def forward(self, values):
                features = self.model.forward_features(values)["x_norm_clstoken"]
                return self.fc(features)

        class DINOv2ModelWithLoRA(nn.Module):
            def __init__(self):
                super().__init__()
                self.base_model = DINOv2Model()
                self.base_model.model = apply_lora(self.base_model.model)

            def forward(self, values):
                return self.base_model(values)

        return DINOv2ModelWithLoRA().to(device)


class DualDataAlignmentDetector:
    """Inference wrapper for the NeurIPS 2025 DDA detector."""

    model_id = DDA_MODEL_ID
    model_revision = DDA_MODEL_REVISION
    input_size = 336
    positive_label = "ai_generated"

    def __init__(self, device: str = "auto"):
        self.device = choose_torch_device(device)
        self.model = None
        self.transform = None

    def load(self) -> "DualDataAlignmentDetector":
        import torch
        from huggingface_hub import hf_hub_download
        from torchvision import transforms

        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        checkpoint_path = hf_hub_download(
            repo_id=self.model_id,
            filename="DDA_ckpt.pth",
            revision=self.model_revision,
        )
        model = _DDAModel.create(self.device)
        checkpoint = torch.load(
            checkpoint_path,
            map_location="cpu",
            weights_only=True,
        )
        missing, unexpected = model.load_state_dict(checkpoint["model"], strict=True)
        del checkpoint
        if missing or unexpected:
            raise RuntimeError(
                f"checkpoint mismatch: missing={missing}, unexpected={unexpected}"
            )
        model.eval()
        self.model = model
        self.transform = transforms.Compose(
            [
                transforms.CenterCrop(336),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.48145466, 0.4578275, 0.40821073],
                    std=[0.26862954, 0.26130258, 0.27577711],
                ),
            ]
        )
        return self

    def _prepare(self, image: Image.Image):
        if self.transform is None:
            raise RuntimeError("detector is not loaded")
        return self.transform(ImageOps.exif_transpose(image).convert("RGB"))

    def predict_images(
        self,
        images: Sequence[Image.Image],
        batch_size: int = 2,
    ) -> List[float]:
        import torch

        if self.model is None:
            raise RuntimeError("detector is not loaded")
        tensors = [self._prepare(image) for image in images]
        scores: List[float] = []
        with torch.inference_mode():
            for offset in range(0, len(tensors), max(1, batch_size)):
                batch = torch.stack(tensors[offset : offset + batch_size]).to(self.device)
                logits = self.model(batch).flatten()
                scores.extend(torch.sigmoid(logits).detach().cpu().tolist())
        return [float(score) for score in scores]

    def predict_image(self, image: Image.Image) -> float:
        return self.predict_images([image], batch_size=1)[0]
