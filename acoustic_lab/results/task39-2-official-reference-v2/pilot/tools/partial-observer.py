#!/usr/bin/env python3
"""有限采样窗的分量观察器；区间仅以声明的衰减正弦模型为条件。

Hann DFT 由离散几何级数计算（含负频率像），不把 FFT 点间距当成估计误差。
频率/衰减率非线性拟合，双声道幅度与相位以实系数 least squares 消元。
同频双衰减与两/三频模型作为竞争解释；多分量、未辨明或超预算返回弃权。
低于可检测幅度的伴线、未建模激励与任意商业内部结构不在认证范围内。
"""
import math

import numpy as np
from scipy.optimize import least_squares

MAX_NFEV = 120
MAX_BINS = 2049
MAX_SAMPLES = 1000000
MIN_DURATION_S = 0.25
MAX_DECAY_PER_S = 40.0
MODEL_EVIDENCE_DELTA = 10.0
INTERVAL_SIGMAS = 3.0


def _sum_exp(q, count):
    denominator = np.expm1(q)
    value = np.empty_like(q, dtype=np.complex128)
    small = np.abs(denominator) < 1e-12
    value[small] = count
    value[~small] = np.expm1(count * q[~small]) / denominator[~small]
    return value


def _hann_response(q, count):
    phase = 2j * math.pi / (count - 1)
    return (0.5 * _sum_exp(q, count) - 0.25 * _sum_exp(q + phase, count)
            - 0.25 * _sum_exp(q - phase, count)) / ((count - 1) / 2.0)


def _basis(frequencies, decays, bins_hz, rate, count):
    columns = []
    for frequency, decay in zip(frequencies, decays, strict=True):
        positive = _hann_response((-decay + 2j * math.pi * (frequency - bins_hz)) / rate, count)
        negative = _hann_response((-decay + 2j * math.pi * (-frequency - bins_hz)) / rate, count)
        columns.extend([0.5 * (positive + negative), (positive - negative) / (2j)])
    complex_basis = np.stack(columns, axis=1)
    return np.concatenate([complex_basis.real, complex_basis.imag], axis=0)


def _parameters(values, model, center):
    if model == "same_frequency_two_decay":
        return np.array([center + values[0], center + values[0]]), np.array(values[1:])
    count = len(values) // 2
    return center + values[:count], values[count:]


def _fit_model(model, initial, center, radius, bins_hz, data, rate, count, noise):
    shared = model == "same_frequency_two_decay"
    count_components = 2 if shared else len(initial) // 2
    frequency_parameters = 1 if shared else count_components
    lower = [-radius] * frequency_parameters + [0.0] * count_components
    upper = [radius] * frequency_parameters + [MAX_DECAY_PER_S] * count_components
    initial = np.clip(initial, np.array(lower) + 1e-8, np.array(upper) - 1e-8)
    scale = max(float(np.linalg.norm(data)), 1e-30)
    calls = 0

    def project(values):
        frequencies, decays = _parameters(values, model, center)
        basis = _basis(frequencies, decays, bins_hz, rate, count)
        coefficients, _, rank, singular = np.linalg.lstsq(basis, data, rcond=1e-10)
        return basis @ coefficients - data, basis, coefficients, int(rank), singular

    def residual(values):
        nonlocal calls
        calls += 1
        return (project(values)[0] / scale).ravel()

    solution = least_squares(residual, initial, bounds=(lower, upper),
                             x_scale=[max(1.0 / (count / rate), 0.1)] * frequency_parameters
                                     + [max(1.0, float(v)) for v in initial[frequency_parameters:]],
                             ftol=1e-9, xtol=1e-9, gtol=1e-9, max_nfev=MAX_NFEV)
    difference, basis, coefficients, rank, singular = project(solution.x)
    sse = float(np.sum(difference ** 2))
    observations = data.size
    fitted_parameters = len(initial) + 2 * basis.shape[1]
    dof = max(1, observations - fitted_parameters)
    variance = max(sse / dof, noise / 2.0)
    covariance = np.linalg.pinv(solution.jac.T @ solution.jac, rcond=1e-10) * variance / scale ** 2
    standard_errors = np.sqrt(np.maximum(0, np.diag(covariance)))
    frequencies, decays = _parameters(solution.x, model, center)
    amp = np.sqrt(np.sum(coefficients.reshape(count_components, 2, 2) ** 2, axis=(1, 2)))
    linear_cov = np.linalg.pinv(basis.T @ basis, rcond=1e-10) * variance
    amp_se = np.sqrt(np.sum(np.diag(linear_cov).reshape(count_components, 2), axis=1) * 2)
    bic = observations * math.log(max(sse / observations, noise / 2.0, 1e-30)) + fitted_parameters * math.log(observations)
    return {"model": model, "success": bool(solution.success), "frequencies": frequencies,
            "decays": decays, "sse": sse, "bic": bic, "noise_variance": variance,
            "adequate": sse <= max(noise * observations * 3.0, float(np.sum(data ** 2)) * 1e-9),
            "frequency_se": standard_errors[:frequency_parameters],
            "amplitudes": amp, "amplitude_se": amp_se,
            "rank": rank, "columns": basis.shape[1],
            "condition": float(singular[0] / singular[-1]) if singular.size and singular[-1] > 0 else None,
            "parameters": solution.x, "nfev": int(solution.nfev), "residual_calls": calls,
            "boundary": bool(np.any(np.abs(solution.x[:frequency_parameters]) > radius * 0.98)
                             or np.any(solution.x[frequency_parameters:] > MAX_DECAY_PER_S * 0.98))}


def _public_fit(fit):
    return {"model": fit["model"], "converged": fit["success"], "adequate": fit["adequate"],
            "sse": fit["sse"], "bic": fit["bic"], "condition": fit["condition"],
            "at_boundary": fit["boundary"], "nfev": fit["nfev"],
            "residual_calls": fit["residual_calls"],
            "frequency_standard_error_hz": [float(v) for v in fit["frequency_se"]],
            "components": [{"frequency_hz": float(f), "decay_per_s": float(d),
                            "amplitude": float(a), "amplitude_standard_error": float(s)}
                           for f, d, a, s in zip(fit["frequencies"], fit["decays"],
                                                 fit["amplitudes"], fit["amplitude_se"], strict=True)]}


def observe_partial(left, right, rate, window, center_hz, half_width_hz):
    """候选由调用方频谱产生；接口不接收分音编号、B 或真值。"""
    left, right = np.asarray(left, dtype=np.float64), np.asarray(right, dtype=np.float64)
    if (left.ndim != 1 or right.ndim != 1 or len(left) != len(right)
            or not np.isfinite([rate, center_hz, half_width_hz, *window]).all()
            or rate <= 0 or half_width_hz <= 0 or center_hz <= half_width_hz
            or center_hz + half_width_hz >= rate / 2):
        raise ValueError("invalid channels, rate, candidate frequency or search bounds")
    start, stop = int(window[0] * rate), int(window[1] * rate)
    if start < 0 or stop <= start or stop > len(left):
        raise ValueError("window exceeds available samples")
    count = stop - start
    output = {"status": "ambiguous", "frequency_hz": None, "interval_hz": None,
              "components": [], "reasons": [], "diagnostics": {
                  "candidate_hz": float(center_hz), "search_half_width_hz": float(half_width_hz),
                  "bounds_s": [float(v) for v in window], "samples": count,
                  "interval_semantics": "conditional sampled damped-sinusoid estimation; not physical source identity",
                  "limits": ["stationary frequencies with one or two exponential amplitudes",
                             "up to three candidate frequencies; undetectable companions not excluded",
                             "finite seeds and local optimization, no universal confidence coverage"],
                  "max_nfev_per_fit": MAX_NFEV, "fits": []}}
    diagnostics = output["diagnostics"]
    if count / rate < MIN_DURATION_S or count > MAX_SAMPLES:
        output["reasons"] = ["window_outside_supported_sample_budget"]
        return output
    channels = np.stack([left[start:stop], right[start:stop]], axis=1)
    if not np.isfinite(channels).all():
        raise ValueError("nonfinite PCM samples")
    hann = np.hanning(count)
    spectrum = np.fft.rfft(channels * hann[:, None], axis=0) / np.sum(hann)
    all_hz = np.fft.rfftfreq(count, 1.0 / rate)
    power = np.sum(np.abs(spectrum) ** 2, axis=1)
    padding = max(3.0, 8.0 / (count / rate), 0.5 * half_width_hz)
    fit_indices = np.flatnonzero(np.abs(all_hz - center_hz) <= half_width_hz + padding)
    if len(fit_indices) > MAX_BINS or len(fit_indices) < 12:
        output["reasons"] = ["local_spectral_sample_budget"]
        return output
    bins = all_hz[fit_indices]
    target = np.concatenate([spectrum[fit_indices].real, spectrum[fit_indices].imag], axis=0)
    noise_indices = fit_indices[np.abs(bins - center_hz) > half_width_hz + padding * 0.6]
    noise = float(np.median(power[noise_indices])) if noise_indices.size else float(np.median(power[fit_indices]))
    noise = max(noise, 1e-28)
    local_power = float(np.max(power[fit_indices]))
    diagnostics.update({"bins": len(bins), "noise_power_per_bin_stereo": noise,
                        "local_peak_power": local_power})
    if local_power <= noise * 20.0:
        output["reasons"] = ["insufficient_local_signal_information"]
        return output
    guard_peaks = fit_indices[(power[fit_indices] >= power[np.maximum(fit_indices - 1, 0)])
                             & (power[fit_indices] >= power[np.minimum(fit_indices + 1, len(power) - 1)])
                             & (np.abs(all_hz[fit_indices] - center_hz) > half_width_hz)]
    if any(power[index] > noise * 100.0 for index in guard_peaks):
        output["reasons"] = ["coherent_structure_outside_component_search_bounds"]
        return output
    duration = count / rate
    local = fit_indices[np.abs(bins - center_hz) <= half_width_hz]
    peak_indices = local[(power[local] >= power[np.maximum(local - 1, 0)])
                         & (power[local] >= power[np.minimum(local + 1, len(power) - 1)])]
    seeds = sorted(peak_indices, key=lambda index: -power[index])[:3]
    seed_freq = float(all_hz[seeds[0]] - center_hz) if seeds else 0.0
    attempts, errors = [], []

    def add(model, initial):
        try:
            fit = _fit_model(model, initial, center_hz, half_width_hz, bins, target, rate, count, noise)
            attempts.append(fit)
        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
            errors.append({"model": model, "error": str(error)})

    for decay in (0.0, 1.0, 6.0):
        add("single_frequency", [seed_freq, decay])
    singles = [fit for fit in attempts if fit["model"] == "single_frequency" and fit["success"]]
    if not singles:
        output["reasons"] = ["single_model_fit_failed"]
        diagnostics["fit_errors"] = errors
        diagnostics["fits"] = [_public_fit(fit) for fit in attempts]
        return output
    single = min(singles, key=lambda fit: fit["sse"])
    offset = float(single["frequencies"][0] - center_hz)
    decay = float(single["decays"][0])
    add("same_frequency_two_decay", [offset, max(0.1, decay / 4), min(30.0, max(3.0, decay * 2))])
    add("same_frequency_two_decay", [offset, 0.0, 8.0])
    two_seeds = [[offset - 0.5 / duration, offset + 0.5 / duration],
                 [offset - 0.4, offset + 0.4]]
    if len(seeds) >= 2:
        two_seeds.append([float(all_hz[i] - center_hz) for i in seeds[:2]])
    else:
        two_seeds.append([offset - min(1.2, half_width_hz / 2), offset + min(1.2, half_width_hz / 2)])
    for pair in two_seeds:
        add("two_frequencies", pair + [decay, decay])
    triple = ([float(all_hz[i] - center_hz) for i in seeds[:3]] if len(seeds) >= 3
              else [offset - min(1.2, half_width_hz / 2), offset, offset + min(1.2, half_width_hz / 2)])
    add("three_frequencies", triple + [decay] * 3)
    diagnostics["fit_errors"] = errors
    diagnostics["fits"] = [_public_fit(fit) for fit in attempts]
    diagnostics["residual_calls"] = sum(fit["residual_calls"] for fit in attempts)
    converged = [fit for fit in attempts if fit["success"] and fit["rank"] == fit["columns"]
                 and fit["condition"] is not None and fit["condition"] < 1e8 and not fit["boundary"]]
    if not converged:
        output["reasons"] = ["fit_unidentifiable_or_at_boundary"]
        return output
    single_models = [fit for fit in converged if fit["model"] in ("single_frequency", "same_frequency_two_decay")]
    base = min(single_models, key=lambda fit: fit["bic"]) if single_models else None
    best = min(converged, key=lambda fit: fit["bic"])
    output["components"] = _public_fit(best)["components"]
    diagnostics["selected_model"] = best["model"]
    if not best["adequate"]:
        output["reasons"] = ["stationary_damped_model_inadequate"]
        return output
    multi = [fit for fit in converged if fit["model"] in ("two_frequencies", "three_frequencies")
             and np.all(fit["amplitudes"] > 6.0 * fit["amplitude_se"])]
    competing = [fit for fit in multi if base is None or fit["bic"] + MODEL_EVIDENCE_DELTA < base["bic"]]
    if competing:
        best_multi = min(competing, key=lambda fit: fit["bic"])
        components = _public_fit(best_multi)["components"]
        output["components"] = components
        frequencies = np.sort(best_multi["frequencies"])
        uncertainty = max(best_multi["frequency_se"])
        supported = np.all(best_multi["amplitudes"] > 6.0 * best_multi["amplitude_se"])
        if (best_multi["adequate"] and supported
                and np.min(np.diff(frequencies)) > max(2.0 / duration, 6.0 * uncertainty)):
            output.update({"status": "resolved_components", "reasons": ["multiple_stationary_components_supported"]})
        else:
            output["reasons"] = ["multiple_component_alternative_unresolved"]
        return output
    if base is None or not base["adequate"]:
        output["reasons"] = ["single_component_not_supported"]
        return output
    frequency = float(base["frequencies"][0])
    plausible = [fit for fit in single_models if fit["adequate"] and fit["bic"] <= base["bic"] + MODEL_EVIDENCE_DELTA]
    model_spread = max((abs(float(fit["frequencies"][0]) - frequency) for fit in plausible), default=0.0)
    stochastic = INTERVAL_SIGMAS * float(base["frequency_se"][0])
    floor = max(0.0005, frequency * (2.0 ** (0.002 / 1200.0) - 1.0))
    half_interval = max(floor, stochastic, model_spread)
    budget = max(0.005, frequency * (2.0 ** (0.05 / 1200.0) - 1.0))
    diagnostics.update({"conditional_stochastic_halfwidth_hz": stochastic,
                        "single_model_frequency_spread_hz": model_spread,
                        "numerical_floor_hz": floor, "frequency_budget_hz": budget})
    if half_interval > budget or frequency - half_interval <= 0:
        output["reasons"] = ["conditional_frequency_interval_exceeds_budget"]
        return output
    if base["amplitudes"].max() <= 6.0 * base["amplitude_se"].max():
        output["reasons"] = ["component_amplitude_not_identifiable"]
        return output
    output.update({"status": "single_component_adequate", "frequency_hz": frequency,
                   "interval_hz": [frequency - half_interval, frequency + half_interval],
                   "components": _public_fit(base)["components"],
                   "reasons": ["single_stationary_frequency_adequate_in_declared_model_domain"]})
    return output
