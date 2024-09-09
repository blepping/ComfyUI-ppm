import math
import torch

import comfy.model_management
from nodes import MAX_RESOLUTION


MIN_RATIO = 0.15
MAX_RATIO = 1 / MIN_RATIO


def _calc_dimensions(resolution: int, ratio: float, step: int):
    target_res = resolution * resolution

    h = math.sqrt(target_res / ratio)
    h_s = int((h // step) * step)
    height = min([h_s, h_s + step], key=lambda x: abs(h - x))

    w = height * ratio
    w_s = int((w // step) * step)
    width = min([w_s, w_s + step], key=lambda x: abs(target_res - x * height))

    width, height = min(max(width, 16), MAX_RESOLUTION), min(max(height, 16), MAX_RESOLUTION)
    return width, height


class EmptyLatentImageAR:
    def __init__(self):
        self.device = comfy.model_management.intermediate_device()

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "resolution": ("INT", {"default": 512, "min": 16, "max": MAX_RESOLUTION, "step": 8}),
                "ratio": ("FLOAT", {"default": 1.0, "min": MIN_RATIO, "max": MAX_RATIO, "step": 0.001}),
                "step": ("INT", {"default": 64, "min": 8, "max": 128, "step": 8}),
                "batch_size": ("INT", {"default": 1, "min": 1, "max": 4096}),
            }
        }

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "generate"

    CATEGORY = "latent"

    def generate(self, resolution, ratio, step, batch_size=1):
        width, height = _calc_dimensions(resolution, ratio, step)

        latent = torch.zeros([batch_size, 4, height // 8, width // 8], device=self.device)
        return ({"samples": latent},)


class EmptyLatentImageARAdvanced:
    def __init__(self):
        self.device = comfy.model_management.intermediate_device()

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "resolution": ("INT", {"default": 512, "min": 16, "max": MAX_RESOLUTION, "step": 8}),
                "base_resolution": ("INT", {"default": 512, "min": 16, "max": MAX_RESOLUTION, "step": 8}),
                "ratio": ("FLOAT", {"default": 1.0, "min": MIN_RATIO, "max": MAX_RATIO, "step": 0.001}),
                "step": ("INT", {"default": 64, "min": 8, "max": 128, "step": 8}),
                "batch_size": ("INT", {"default": 1, "min": 1, "max": 4096}),
            }
        }

    RETURN_TYPES = ("LATENT", "LATENT")
    RETURN_NAMES = ("latent", "base_latent")
    FUNCTION = "generate"

    CATEGORY = "latent"

    def generate(self, resolution, base_resolution, ratio, step, batch_size=1):
        width, height = _calc_dimensions(resolution, ratio, step)
        base_width, base_height = _calc_dimensions(base_resolution, ratio, step)

        latent = torch.zeros([batch_size, 4, height // 8, width // 8], device=self.device)
        base_latent = torch.zeros([batch_size, 4, base_height // 8, base_width // 8], device=self.device)
        return ({"samples": latent}, {"samples": base_latent})


class LatentToWidthHeight:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "latent": ("LATENT",),
            }
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "convert"

    CATEGORY = "latent"

    def convert(self, latent):
        samples: torch.Tensor = latent["samples"]

        height = samples.shape[2] * 8
        width = samples.shape[3] * 8
        if height > MAX_RESOLUTION or width > MAX_RESOLUTION:
            raise ValueError(f"{height} and/or {width} are greater than {MAX_RESOLUTION}")

        return width, height


class LatentToMaskBB:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "latent": ("LATENT",),
                "x": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "y": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "w": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "h": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "value": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            },
            "optional": {
                "outer_value": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("MASK",)
    FUNCTION = "get_bounding_box"

    CATEGORY = "mask"

    def get_bounding_box(self, latent, x: float, y: float, w: float, h: float, value: float = 1.0, outer_value: float = 0.0):
        x_end, y_end = x + w, y + h
        if x_end > 1.0 or y_end > 1.0:
            raise ValueError("x + w and y + h must be less than 1.0")

        samples: torch.Tensor = latent["samples"]

        height = samples.shape[2] * 8
        width = samples.shape[3] * 8

        x_coord, x_end_coord = round(x * width), round(x_end * width)
        y_coord, y_end_coord = round(y * height), round(y_end * height)

        mask = torch.full((height, width), outer_value)
        mask[y_coord:y_end_coord, x_coord:x_end_coord] = value

        return (mask.unsqueeze(0),)
