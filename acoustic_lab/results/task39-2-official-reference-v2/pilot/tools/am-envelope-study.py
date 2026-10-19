#!/usr/bin/env python3
"""AM/包络的独立方法研究：固定配方、PCM 往返、留出预测和分离声明。"""
import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import platform
import sys
import time
import wave

import numpy as np
import scipy


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def synthesize(recipe, generator):
    """独立时域生成，不调用被测模型的 basis、预测器或任何 B 表。"""
    rate = recipe["rate"]
    t = np.arange(int(generator["duration_s"] * rate)) / rate
    carrier, fm, depth, decay = (recipe[key] for key in ("carrier_hz", "modulation_hz", "depth", "decay_per_s"))
    phase, psi, amplitude = (recipe[key] for key in ("carrier_phase_rad", "modulation_phase_rad", "amplitude"))
    kind = recipe["kind"]
    channels = []
    rng = np.random.default_rng(recipe["seed"])
    for channel in range(2):
        phi = phase + channel * generator["right_phase_offset_rad"]
        gain = 1.0 if channel == 0 else generator["right_gain"]
        angle = 2 * math.pi * carrier * t + phi
        envelope = np.exp(-decay * t)
        if kind in ("am_product", "slow_unidentifiable_am"):
            clean = amplitude * envelope * (1 + depth * np.cos(2 * math.pi * fm * t + psi)) * np.cos(angle)
        elif kind in ("coherent_triplet", "asymmetric_triplet"):
            upper_gain, upper_shift = (1.0, 0.0) if kind == "coherent_triplet" else (0.35, 0.7)
            clean = amplitude * envelope * (
                np.cos(angle) + depth / 2 * np.cos(2 * math.pi * (carrier - fm) * t + phi - psi)
                + upper_gain * depth / 2 * np.cos(2 * math.pi * (carrier + fm) * t + phi + psi + upper_shift))
        elif kind == "beating_doublet":
            clean = amplitude * envelope * (np.cos(2 * math.pi * (carrier - fm / 2) * t + phi)
                                           + np.cos(2 * math.pi * (carrier + fm / 2) * t + phi + 0.9))
        elif kind == "fm":
            clean = amplitude * envelope * np.cos(angle + (0.65 / fm) * np.sin(2 * math.pi * fm * t + psi))
        elif kind == "chirp":
            clean = amplitude * envelope * np.cos(2 * math.pi * (carrier * t + 0.4 * t * t) + phi)
        elif kind == "constant_decay":
            clean = amplitude * envelope * np.cos(angle)
        elif kind == "noise":
            clean = np.zeros_like(t)
        else:
            raise ValueError(f"Unknown fixed generator: {kind}")
        channels.append(gain * clean + rng.normal(0.0, recipe["noise_sigma"], len(t)))
    samples = np.stack(channels, axis=1)
    if not np.isfinite(samples).all() or np.max(np.abs(samples)) >= 0.95:
        raise ValueError("nonfinite or clipping fixture; normalization prohibited")
    return samples


def pcm_roundtrip(path, rate, samples):
    integers = np.rint(samples * 8388608).astype(np.int32)
    packed = np.stack([(integers.ravel() >> shift) & 255 for shift in (0, 8, 16)], axis=1).astype(np.uint8)
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(3)
        stream.setframerate(rate)
        stream.writeframes(packed.tobytes())
    with wave.open(str(path), "rb") as stream:
        if stream.getnchannels() != 2 or stream.getsampwidth() != 3 or stream.getframerate() != rate:
            raise ValueError("unexpected fixture PCM metadata")
        encoded = np.frombuffer(stream.readframes(stream.getnframes()), dtype=np.uint8).reshape(-1, 3).astype(np.int32)
    values = encoded[:, 0] | (encoded[:, 1] << 8) | (encoded[:, 2] << 16)
    values = np.where(values >= 8388608, values - 16777216, values).reshape(-1, 2)
    decoded = values.astype(float) / 8388608
    if np.max(np.abs(decoded - samples)) > 0.5 / 8388608 + 1e-15:
        raise ValueError("PCM roundtrip exceeds half LSB")
    return decoded


def spectral_candidate(samples, rate, window, config):
    start, stop = (int(value * rate) for value in window)
    spectrum = np.fft.rfft(samples[start:stop] * np.hanning(stop - start)[:, None], axis=0)
    frequency = np.fft.rfftfreq(stop - start, 1 / rate)
    indices = np.flatnonzero((frequency >= config["candidate_low_hz"]) & (frequency <= min(rate / 2, config["candidate_high_hz"])))
    index = indices[np.argmax(np.sum(np.abs(spectrum[indices]) ** 2, axis=1))]
    return float(frequency[index])


def assess(recipe, envelope, static, registration):
    """真值首次在观察后评分；包络成功不改变静态门禁结果。"""
    errors, metrics = [], {}
    if recipe["envelope_expectation"] == "supported":
        if envelope["status"] != "supported":
            errors.append("expected_envelope_explanation_missing")
        else:
            p = envelope["parameters"]
            assessment = registration["assessment"]
            begin = registration["observation"]["training_window_s"][0]
            t = np.arange(int((registration["observation"]["prediction_end_s"] - begin) * recipe["rate"])) / recipe["rate"]
            true_envelope = np.exp(-recipe["decay_per_s"] * (t + begin)) * (
                1 + recipe["depth"] * np.cos(2 * math.pi * recipe["modulation_hz"] * (t + begin) + recipe["modulation_phase_rad"]))
            fitted_envelope = np.exp(-p["decay_per_s"] * t) * (1 + p["depth"] * np.cos(
                2 * math.pi * p["modulation_hz"] * t + p["phase_at_training_start_rad"]))
            split = int((registration["observation"]["training_window_s"][1] - begin) * recipe["rate"])
            true_envelope /= math.sqrt(float(np.mean(true_envelope[:split] ** 2)))
            fitted_envelope /= math.sqrt(float(np.mean(fitted_envelope[:split] ** 2)))
            metrics = {
                "carrier_error_hz": abs(p["carrier_hz"] - recipe["carrier_hz"]),
                "modulation_error_hz": abs(p["modulation_hz"] - recipe["modulation_hz"]),
                "depth_error": abs(p["depth"] - recipe["depth"]),
                "decay_error_per_s": abs(p["decay_per_s"] - recipe["decay_per_s"]),
                "phase_error_rad": abs(math.atan2(math.sin(p["phase_at_training_start_rad"] - recipe["modulation_phase_rad"]
                                                        - 2 * math.pi * recipe["modulation_hz"] * begin),
                                                 math.cos(p["phase_at_training_start_rad"] - recipe["modulation_phase_rad"]
                                                          - 2 * math.pi * recipe["modulation_hz"] * begin))),
                "normalized_envelope_rms": math.sqrt(float(np.mean((true_envelope - fitted_envelope) ** 2))),
                "carrier_interval_covers_truth": envelope["carrier_interval_hz"][0] <= recipe["carrier_hz"] <= envelope["carrier_interval_hz"][1]}
            config = registration["observation"]["model_config"]
            budget = max(config["carrier_frequency_floor_hz"], recipe["carrier_hz"] * (2 ** (config["carrier_frequency_cents"] / 1200) - 1))
            limits = {"carrier_error_hz": budget, "modulation_error_hz": assessment["maximum_modulation_error_hz"],
                      "depth_error": assessment["maximum_depth_error"], "decay_error_per_s": assessment["maximum_decay_error_per_s"],
                      "phase_error_rad": assessment["maximum_phase_error_rad"],
                      "normalized_envelope_rms": assessment["maximum_normalized_envelope_rms"]}
            errors.extend(name for name, limit in limits.items() if metrics[name] > limit)
            if not metrics["carrier_interval_covers_truth"]:
                errors.append("carrier_interval_misses_truth")
    elif envelope["status"] == "supported":
        errors.append("false_supported_envelope")
    static_admitted = static["status"] == "single_component_adequate"
    expectation = recipe["static_expectation"]
    if expectation == "admitted" and not static_admitted:
        errors.append("static_control_not_admitted")
    if expectation == "not_admitted" and static_admitted:
        errors.append("static_false_single_component_admission")
    return {"passed": not errors, "violations": errors, "truth_metrics": metrics,
            "envelope_explained": envelope["status"] == "supported", "static_admitted": static_admitted,
            "physical_B_certified": False}


def validate_registration(registration):
    if (registration.get("schema") != "devpiano-task39-2-am-envelope-study-v1"
            or registration.get("status") != "preregistered_independent_method_study_not_v3_acceptance"):
        raise ValueError("Unsupported study registration")
    a, b = (registration["cases"][role] for role in ("development", "qualification"))
    if not a or not b or len({r["id"] for r in a + b}) != len(a + b):
        raise ValueError("Empty or duplicate study case ids")
    if {r["seed"] for r in a} & {r["seed"] for r in b}:
        raise ValueError("Role seeds must be disjoint")
    if {(r["carrier_hz"], r["modulation_hz"], r["carrier_phase_rad"]) for r in a} & {
        (r["carrier_hz"], r["modulation_hz"], r["carrier_phase_rad"]) for r in b}:
        raise ValueError("Role signal parameters must be disjoint")
    for role in (a, b):
        pairs = {}
        for row in role:
            if row.get("pair"):
                pairs.setdefault(row["pair"], []).append(row)
        if not pairs or any({r["kind"] for r in rows} != {"am_product", "coherent_triplet"} or len(rows) != 2 for rows in pairs.values()):
            raise ValueError("Equivalence controls require exactly one product and one triplet")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registration", type=Path, required=True)
    parser.add_argument("--role", choices=("development", "qualification"), required=True)
    parser.add_argument("--seal", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("Output exists; preserve previous evidence")
    registration = json.loads(args.registration.read_text(encoding="utf-8"))
    validate_registration(registration)
    tools = Path(__file__).resolve().parent
    dependencies = [Path(__file__), tools / "am-envelope-observer.py", tools / "partial-observer.py", args.registration]
    identities = {str(path.resolve()): digest(path) for path in dependencies}
    if args.role == "qualification":
        if args.seal is None:
            parser.error("Qualification requires a source seal made before execution")
        seal = json.loads(args.seal.read_text(encoding="utf-8"))
        if seal.get("role") != "am_envelope_method_qualification" or seal.get("files") != identities:
            parser.error("Qualification seal does not bind exact dependencies and registration")
    model = load_module(tools / "am-envelope-observer.py", "am_envelope")
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / "pcm").mkdir()
    rows, pairs = [], {}
    started = time.monotonic()
    for recipe in registration["cases"][args.role]:
        row = {"id": recipe["id"], "recipe": recipe}
        try:
            samples = synthesize(recipe, registration["generator"])
            wav_path = args.out / "pcm" / (recipe["id"] + ".wav")
            decoded = pcm_roundtrip(wav_path, recipe["rate"], samples)
            observation = registration["observation"]
            config = observation["model_config"]
            envelope = model.explain_envelope(decoded[:, 0], decoded[:, 1], recipe["rate"],
                                              observation["training_window_s"], observation["prediction_end_s"], config)
            candidate = spectral_candidate(decoded, recipe["rate"], observation["training_window_s"], config)
            static = model.partial.observe_partial(decoded[:, 0], decoded[:, 1], recipe["rate"],
                                                   observation["static_window_s"], candidate, observation["static_halfwidth_hz"])
            row.update(envelope=envelope, static_observation=static, pcm_sha256=digest(wav_path),
                       assessment=assess(recipe, envelope, static, registration))
            if recipe.get("pair"):
                pairs.setdefault(recipe["pair"], []).append((recipe["id"], samples, decoded))
        except Exception as error:
            row.update(error=str(error), error_type=type(error).__name__,
                       assessment={"passed": False, "violations": ["study_exception"]})
        rows.append(row)
        (args.out / (recipe["id"] + ".json")).write_text(json.dumps(row, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")
        print("CASE", recipe["id"], row["assessment"]["passed"], flush=True)
    pair_results = []
    for name, members in pairs.items():
        if len(members) != 2:
            pair_results.append({"pair": name, "passed": False, "reason": "missing_pair_observation"})
            continue
        (name_a, floating_a, pcm_a), (name_b, floating_b, pcm_b) = members
        float_error = float(np.max(np.abs(floating_a - floating_b)))
        pcm_lsb = float(np.max(np.abs(pcm_a - pcm_b)) * 8388608)
        okay = float_error <= registration["assessment"]["maximum_equivalence_float_error"] and pcm_lsb <= registration["assessment"]["maximum_equivalence_pcm_lsb"]
        pair_results.append({"pair": name, "members": [name_a, name_b], "max_float_error": float_error,
                             "max_pcm_lsb": pcm_lsb, "passed": okay})
    expected_pairs = {r["pair"] for r in registration["cases"][args.role] if r.get("pair")}
    failed = [row["id"] for row in rows if not row["assessment"]["passed"]]
    passed = not failed and len(pair_results) == len(expected_pairs) and all(pair["passed"] for pair in pair_results)
    summary = {"role": args.role, "outcome": ("study_qualified" if args.role == "qualification" else "development_passed") if passed else "not_qualified",
               "complete": len(rows) == len(registration["cases"][args.role]), "cases": len(rows), "failed_cases": failed,
               "envelope_supported_cases": [r["id"] for r in rows if r.get("assessment", {}).get("envelope_explained")],
               "static_admitted_cases": [r["id"] for r in rows if r.get("assessment", {}).get("static_admitted")],
               "equivalence_pairs": pair_results,
               "prior_meter_qualification_changed": False, "v3_acceptance_frozen": False,
               "reference_capture_authorized": False, "physical_source_certified": False}
    report = {"schema": "devpiano-am-envelope-study-result-v1", "summary": summary,
              "identity": {"files": identities, "python": sys.version, "numpy": np.__version__, "scipy": scipy.__version__,
                           "platform": platform.platform(), "elapsed_seconds": time.monotonic() - started,
                           "seal_sha256": digest(args.seal) if args.seal else None},
              "registration": registration, "cases": rows}
    (args.out / "study-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")
    (args.out / "study-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
