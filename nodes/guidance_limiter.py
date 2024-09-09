import torch
import comfy.samplers


# Based on Applying Guidance in a Limited Interval Improves Sample and Distribution Quality in Diffusion Models by Kynkäänniemi et al.
class GuidanceLimiter:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "model": ("MODEL",),
                "sigma_start": ("FLOAT", {"default": 5.42, "min": -1.0, "max": 10000.0, "step": 0.01, "round": False}),
                "sigma_end": ("FLOAT", {"default": 0.28, "min": -1.0, "max": 10000.0, "step": 0.01, "round": False}),
                "cfg_rescale": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01}),
            }
        }

    RETURN_TYPES = ("MODEL",)
    FUNCTION = "patch"

    CATEGORY = "model_patches/unet"

    def patch(self, model, sigma_start: float, sigma_end: float, cfg_rescale: float):
        m = model.clone()

        def limited_cfg(args):
            cond = args["cond"]
            uncond = args["uncond"]
            sigma = args["sigma"]
            cond_scale = args["cond_scale"]

            if sigma_start >= 0 and sigma[0] > sigma_start:
                cond_scale = 1

            if sigma_end >= 0 and sigma[0] <= sigma_end:
                cond_scale = 1

            if cfg_rescale > 0:
                x_orig = args["input"]
                sigma = sigma.view(sigma.shape[:1] + (1,) * (cond.ndim - 1))

                # rescale cfg has to be done on v-pred model output
                x = x_orig / (sigma * sigma + 1.0)
                cond = ((x - (x_orig - cond)) * (sigma**2 + 1.0) ** 0.5) / (sigma)
                uncond = ((x - (x_orig - uncond)) * (sigma**2 + 1.0) ** 0.5) / (sigma)

                # rescalecfg
                x_cfg = uncond + cond_scale * (cond - uncond)
                ro_pos = torch.std(cond, dim=(1, 2, 3), keepdim=True)
                ro_cfg = torch.std(x_cfg, dim=(1, 2, 3), keepdim=True)

                x_rescaled = x_cfg * (ro_pos / ro_cfg)
                x_final = cfg_rescale * x_rescaled + (1.0 - cfg_rescale) * x_cfg

                return x_orig - (x - x_final * sigma / (sigma * sigma + 1.0) ** 0.5)

            cfg_result = uncond + (cond - uncond) * cond_scale

            return cfg_result

        m.set_model_sampler_cfg_function(limited_cfg)

        return (m,)


class Guider_CFGLimiter(comfy.samplers.CFGGuider):
    def set_limits(self, sigma_start, sigma_end):
        self.sigma_start = sigma_start
        self.sigma_end = sigma_end

    def predict_noise(self, x, timestep, model_options={}, seed=None):
        cfg = self.cfg
        sigma = self.inner_model.model_sampling.sigma(timestep)

        if self.sigma_start >= 0 and sigma[0] > self.sigma_start:
            cfg = 1

        if self.sigma_end >= 0 and sigma[0] <= self.sigma_end:
            cfg = 1

        return comfy.samplers.sampling_function(
            self.inner_model,
            x,
            timestep,
            self.conds.get("negative", None),
            self.conds.get("positive", None),
            cfg,
            model_options=model_options,
            seed=seed,
        )


class CFGLimiterGuider:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "model": ("MODEL",),
                "positive": ("CONDITIONING",),
                "negative": ("CONDITIONING",),
                "cfg": ("FLOAT", {"default": 8.0, "min": 0.0, "max": 100.0, "step": 0.1, "round": 0.01}),
                "sigma_start": ("FLOAT", {"default": 5.42, "min": -1.0, "max": 10000.0, "step": 0.01, "round": False}),
                "sigma_end": ("FLOAT", {"default": 0.28, "min": -1.0, "max": 10000.0, "step": 0.01, "round": False}),
            }
        }

    RETURN_TYPES = ("GUIDER",)

    FUNCTION = "get_guider"
    CATEGORY = "sampling/custom_sampling/guiders"

    def get_guider(self, model, positive, negative, cfg: float, sigma_start: float, sigma_end: float):
        guider = Guider_CFGLimiter(model)
        guider.set_conds(positive, negative)
        guider.set_cfg(cfg)
        guider.set_limits(sigma_start, sigma_end)
        return (guider,)
