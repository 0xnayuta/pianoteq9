#!/usr/bin/env python3
"""AM 包络的条件解释研究；不修改或替代静态分量门禁。

模型 exp(-d*t)*(1+m*cos(2*pi*fm*t+psi)) 乘定频载波。
仅拟合前段实际 Hann 复数谱，以未参与拟合的后段原始样本检验预测。
AM 与满足相干关系的三音完全等价，成功解释不提供唯一物理来源证据。
"""
import importlib.util
import math
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

PARTIAL_OBSERVER_PATH = Path(__file__).with_name("partial-observer.py")
spec = importlib.util.spec_from_file_location("am_shared_partial", PARTIAL_OBSERVER_PATH)
partial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(partial)


def _basis(parameters, center, bins, rate, count):
    offset, decay, modulation_hz, depth, phase = parameters
    carrier = center + offset
    response = partial._basis([carrier - modulation_hz, carrier, carrier + modulation_hz],
                              [decay] * 3, bins, rate, count)
    cosine, sine = math.cos(phase), math.sin(phase)
    first = response[:, 2] + depth / 2 * (cosine * (response[:, 0] + response[:, 4])
                                         + sine * (response[:, 1] - response[:, 5]))
    second = response[:, 3] + depth / 2 * (cosine * (response[:, 1] + response[:, 5])
                                          + sine * (-response[:, 0] + response[:, 4]))
    return np.stack([first, second], axis=1)


def _predict(parameters, center, coefficients, time):
    offset, decay, modulation_hz, depth, phase = parameters
    envelope = np.exp(-decay * time) * (1 + depth * np.cos(2 * math.pi * modulation_hz * time + phase))
    angle = 2 * math.pi * (center + offset) * time
    carrier = np.stack([np.cos(angle), np.sin(angle)], axis=1)
    return envelope[:, None] * (carrier @ coefficients)


def explain_envelope(left, right, rate, training_window, prediction_end_s, config):
    """只接收 PCM 和冻结方法配置，不接收 fixture 编号、真值或来源标签。"""
    channels = np.stack([np.asarray(left, dtype=float), np.asarray(right, dtype=float)], axis=1)
    if (channels.ndim != 2 or channels.shape[1] != 2 or not np.isfinite(channels).all()
            or not np.isfinite([rate, *training_window, prediction_end_s]).all() or rate <= 0):
        raise ValueError("invalid PCM or sample/time metadata")
    start, stop, end = (int(value * rate) for value in (*training_window, prediction_end_s))
    if start < 0 or stop <= start or end <= stop or end > len(channels):
        raise ValueError("invalid training or nonoverlapping prediction windows")
    count = stop - start
    result = {"status": "unidentifiable", "model": "exponential_real_sinusoidal_AM",
              "carrier_hz": None, "carrier_interval_hz": None, "parameters": None,
              "source_identity": "not_identifiable_from_AM_vs_coherent_triplet",
              "static_admission_override": False,
              "reasons": [], "diagnostics": {"fits": [], "training_samples": count,
                  "prediction_samples": end - stop,
                  "parameter_time_origin_s": start / rate,
                  "interval_semantics": "conditional local estimate, not universal confidence or source identity"}}
    if count < config["minimum_training_samples"] or end - start > config["maximum_samples"]:
        result["reasons"] = ["sample_budget_or_insufficient_observation"]
        return result
    train = channels[start:stop]
    if np.max(np.abs(train)) < config["minimum_peak_amplitude"]:
        result["reasons"] = ["insufficient_signal"]
        return result
    hann = np.hanning(count)
    spectrum = np.fft.rfft(train * hann[:, None], axis=0) / np.sum(hann)
    frequencies = np.fft.rfftfreq(count, 1 / rate)
    power = np.sum(np.abs(spectrum) ** 2, axis=1)
    candidates = np.flatnonzero((frequencies >= config["candidate_low_hz"])
                                & (frequencies <= min(config["candidate_high_hz"], rate / 2)))
    if not candidates.size:
        raise ValueError("candidate search band outside sample bandwidth")
    index = int(candidates[np.argmax(power[candidates])])
    center = float(frequencies[index])
    radius = config["carrier_search_halfwidth_hz"]
    selected = np.flatnonzero(np.abs(frequencies - center) <= config["spectral_fit_halfwidth_hz"])
    if len(selected) < 12 or len(selected) > config["maximum_bins"]:
        result["reasons"] = ["spectral_sample_budget"]
        return result
    bins = frequencies[selected]
    data = np.concatenate([spectrum[selected].real, spectrum[selected].imag], axis=0)
    scale = max(float(np.linalg.norm(data)), 1e-30)
    lower = [-radius, 0.0, config["modulation_hz_bounds"][0], 0.0, -2 * math.pi]
    upper = [radius, config["maximum_decay_per_s"], config["modulation_hz_bounds"][1],
             config["maximum_depth"], 2 * math.pi]
    fits = []
    for modulation_seed in config["modulation_seed_hz"]:
        for phase_seed in config["phase_seeds_rad"]:
            def project(values):
                basis = _basis(values, center, bins, rate, count)
                coefficients, _, rank, _ = np.linalg.lstsq(basis, data, rcond=1e-10)
                return basis @ coefficients - data, coefficients, rank

            solution = least_squares(lambda values: (project(values)[0] / scale).ravel(),
                                     [0.0, config["decay_seed_per_s"], modulation_seed, 0.4, phase_seed],
                                     bounds=(lower, upper), x_scale=[0.2, 1.0, 0.3, 0.3, 1.0],
                                     max_nfev=config["max_nfev"], ftol=1e-10, xtol=1e-10, gtol=1e-10)
            residual, coefficients, rank = project(solution.x)
            sse = float(np.sum(residual ** 2))
            record = {"seed_modulation_hz": modulation_seed, "seed_phase_rad": phase_seed,
                      "converged": bool(solution.success), "nfev": int(solution.nfev), "sse": sse}
            result["diagnostics"]["fits"].append(record)
            if solution.success and rank == 2:
                fits.append((sse, solution, coefficients))
    if not fits:
        result["reasons"] = ["all_fits_failed"]
        return result
    _, best, coefficients = min(fits, key=lambda fit: fit[0])
    offset, decay, modulation_hz, depth, phase = map(float, best.x)
    singular = np.linalg.svd(best.jac, compute_uv=False)
    condition = float(singular[0] / singular[-1]) if singular[-1] > 0 else None
    variance = max(float(np.sum(best.fun ** 2)) / max(1, data.size - 9), 1e-24)
    covariance = np.linalg.pinv(best.jac.T @ best.jac, rcond=1e-12) * variance
    errors = np.sqrt(np.maximum(0, np.diag(covariance)))
    candidate_estimate = center + offset
    half_interval = max(config["carrier_interval_floor_hz"], config["interval_sigmas"] * float(errors[0]))
    parameters = {"carrier_hz": candidate_estimate, "decay_per_s": decay,
                  "modulation_hz": modulation_hz, "depth": depth,
                  "phase_at_training_start_rad": math.atan2(math.sin(phase), math.cos(phase)),
                  "carrier_interval_hz": [candidate_estimate - half_interval, candidate_estimate + half_interval],
                  "modulation_standard_error_hz": float(errors[2])}
    result["diagnostics"].update({"candidate_from_training_spectrum_hz": center,
        "candidate_parameters": parameters, "jacobian_condition": condition,
        "conditional_standard_errors": [float(value) for value in errors],
        "coefficients_at_training_start": coefficients.tolist()})
    if (condition is None or condition > config["maximum_jacobian_condition"]
            or depth < config["minimum_identifiable_depth"]
            or config["interval_sigmas"] * errors[2] > config["maximum_modulation_half_interval_hz"]):
        result["reasons"] = ["modulation_parameters_unidentifiable"]
        return result
    if (abs(offset) > radius * 0.98 or decay > config["maximum_decay_per_s"] * 0.98
            or depth > config["maximum_depth"] * 0.98
            or modulation_hz <= config["modulation_hz_bounds"][0] * 1.02
            or modulation_hz >= config["modulation_hz_bounds"][1] * 0.98):
        result["reasons"] = ["fit_reaches_declared_model_boundary"]
        return result
    budget = max(config["carrier_frequency_floor_hz"], candidate_estimate * (2 ** (config["carrier_frequency_cents"] / 1200) - 1))
    if half_interval > budget:
        result["reasons"] = ["conditional_carrier_interval_exceeds_budget"]
        return result
    times = np.arange(end - start) / rate
    predicted = _predict(best.x, center, coefficients, times)
    split = stop - start
    observed = channels[start:end]
    train_rms = math.sqrt(float(np.mean(observed[:split] ** 2)))
    train_error = math.sqrt(float(np.mean((predicted[:split] - observed[:split]) ** 2))) / max(train_rms, 1e-30)
    holdout_error = math.sqrt(float(np.mean((predicted[split:] - observed[split:]) ** 2))) / max(train_rms, 1e-30)
    result["diagnostics"].update({"training_relative_rms": train_error,
                                 "heldout_relative_rms": holdout_error,
                                 "heldout_reestimated": False})
    if train_error > config["maximum_training_relative_rms"] or holdout_error > config["maximum_heldout_relative_rms"]:
        result.update(status="inadequate", reasons=["heldout_or_training_waveform_not_explained"])
        return result
    result.update(status="supported", carrier_hz=candidate_estimate,
                  carrier_interval_hz=parameters["carrier_interval_hz"], parameters=parameters,
                  reasons=["conditional_AM_envelope_predicts_independent_time_segment"])
    return result
