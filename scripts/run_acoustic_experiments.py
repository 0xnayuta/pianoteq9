#!/usr/bin/env python3
"""只读复算保留参考文件，验证散列、量测定义与条件性结果；不执行渲染。"""

import argparse
import hashlib
import json
import math
import struct
import sys
import wave
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "acoustic_lab/results/task39-1-reference-revalidation"


class EvidenceError(ValueError):
    """输入或冻结证据不满足本数据集的复算条件。"""


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def checked_hash(path, expected):
    if not path.is_file():
        raise EvidenceError(f"missing input: {path}")
    actual = sha256(path)
    if actual != expected:
        raise EvidenceError(f"SHA256 mismatch: {path}: {actual}")


def read_json(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def decode_midi(path):
    data = path.read_bytes()
    if len(data) < 22:
        raise EvidenceError(f"truncated SMF: {path}")
    magic, length, kind, tracks, ppq = struct.unpack(">4sIHHH", data[:14])
    if magic != b"MThd" or kind != 0 or tracks != 1 or not 0 < ppq < 0x8000:
        raise EvidenceError(f"unsupported reference SMF: {path}")
    offset = 8 + length
    if data[offset:offset + 4] != b"MTrk":
        raise EvidenceError(f"missing reference track: {path}")
    end = offset + 8 + int.from_bytes(data[offset + 4:offset + 8], "big")
    if end > len(data):
        raise EvidenceError(f"truncated reference track: {path}")
    position = offset + 8
    ticks, seconds, tempo, running = 0, 0.0, 500000, None
    events = []

    def vlq():
        nonlocal position
        value = 0
        for _ in range(4):
            if position >= end:
                raise EvidenceError(f"truncated VLQ: {path}")
            byte = data[position]
            position += 1
            value = (value << 7) | (byte & 127)
            if byte < 128:
                return value
        raise EvidenceError(f"invalid VLQ: {path}")

    while position < end:
        delta = vlq()
        ticks += delta
        seconds += delta * tempo / ppq / 1e6
        if position >= end:
            raise EvidenceError(f"missing MIDI status: {path}")
        status = data[position]
        if status >= 128:
            position += 1
            running = status if status < 240 else None
        elif running is None:
            raise EvidenceError(f"missing running status: {path}")
        else:
            status = running
        if status == 255:
            if position >= end:
                raise EvidenceError(f"truncated meta: {path}")
            meta = data[position]
            position += 1
            size = vlq()
            payload = data[position:position + size]
            position += size
            if position > end:
                raise EvidenceError(f"truncated meta payload: {path}")
            if meta == 81:
                if size != 3 or int.from_bytes(payload, "big") <= 0:
                    raise EvidenceError(f"invalid reference tempo: {path}")
                tempo = int.from_bytes(payload, "big")
            events.append({"tick": ticks, "seconds": seconds, "meta": meta, "data": list(payload)})
        elif status < 240:
            size = 1 if (status & 240) in (192, 208) else 2
            payload = data[position:position + size]
            position += size
            if len(payload) != size or any(byte >= 128 for byte in payload):
                raise EvidenceError(f"invalid channel message: {path}")
            events.append({"tick": ticks, "seconds": seconds, "status": status,
                           "channel": (status & 15) + 1, "data": list(payload)})
        else:
            raise EvidenceError(f"unsupported reference message: {path}")
    return {"format": kind, "tracks": tracks, "ppq": ppq, "events": events}


def read_audio(path, expected):
    with wave.open(str(path), "rb") as audio:
        actual = {"rate": audio.getframerate(), "bits": audio.getsampwidth() * 8,
                  "channels": audio.getnchannels(), "frames": audio.getnframes()}
        if any(actual[key] != expected[key] for key in actual):
            raise EvidenceError(f"WAV metadata mismatch: {path}")
        if actual["bits"] != 24 or actual["channels"] != 2:
            raise EvidenceError(f"unsupported reference PCM format: {path}")
        payload = audio.readframes(actual["frames"])
    if len(payload) != actual["frames"] * 6:
        raise EvidenceError(f"truncated PCM: {path}")
    raw = np.frombuffer(payload, dtype=np.uint8).reshape(actual["frames"], 2, 3).astype(np.int32)
    packed = raw[:, :, 0] | (raw[:, :, 1] << 8) | (raw[:, :, 2] << 16)
    values = ((packed ^ 0x800000) - 0x800000).astype(np.float64) / 8388608.0
    return actual["rate"], values


def spectrum(data, rate, start, stop, detrend=False):
    segment = data[int(round(start * rate)):int(round(stop * rate))]
    if len(segment) < 64:
        raise EvidenceError("insufficient fixed analysis window")
    if detrend:
        segment = segment - np.mean(segment, axis=0)
    count = 1 << int(math.ceil(math.log2(len(segment) * 8)))
    window = np.hanning(len(segment))
    transformed = np.fft.rfft(segment * window[:, None], n=count, axis=0)
    power = np.mean(np.abs(transformed) ** 2, axis=1)
    return np.fft.rfftfreq(count, 1 / rate), power


def spectral_peaks(frequency, power, low, high):
    relative = power / np.max(power)
    candidates = np.flatnonzero((relative[1:-1] > relative[:-2])
                               & (relative[1:-1] >= relative[2:])) + 1
    candidates = candidates[(frequency[candidates] >= low) & (frequency[candidates] < high)
                            & (relative[candidates] > 1e-8)]
    result = []
    for index in candidates:
        left, middle, right = np.log(relative[index - 1:index + 2] + 1e-30)
        denominator = left - 2 * middle + right
        delta = 0.5 * (left - right) / denominator if denominator else 0.0
        result.append(float(frequency[index] + delta * (frequency[1] - frequency[0])))
    if not result:
        raise EvidenceError("no peaks in the fixed reference window")
    return np.array(result)


def partial_prediction(parameters, numbers):
    first, stiffness = parameters
    return numbers * first * np.sqrt((1 + stiffness * numbers ** 2) / (1 + stiffness))


def fit_family(label, seed_first, seed_b, maximum, data, rate):
    window = [0.08, 0.8] if label == "C7" else [0.08, 3.8]
    frequency, power = spectrum(data, rate, *window)
    peaks = spectral_peaks(frequency, power, max(10, seed_first * 0.6), 20000)
    numbers, observed = [], []
    for number in range(1, maximum + 1):
        prediction = float(partial_prediction([seed_first, seed_b], np.array([number]))[0])
        if prediction > 20000:
            break
        index = int(np.argmin(np.abs(peaks - prediction) / prediction))
        if abs(peaks[index] - prediction) / prediction <= 0.01:
            numbers.append(number)
            observed.append(float(peaks[index]))
    n, actual = np.array(numbers), np.array(observed)
    if len(n) < 3:
        raise EvidenceError(f"insufficient candidate family: {label}")

    def fit(keep):
        solution = least_squares(
            lambda parameters: 1200 * np.log2(actual[keep] / partial_prediction(parameters, n[keep])),
            [seed_first, seed_b], bounds=([seed_first * 0.98, 0], [seed_first * 1.02, 0.3]),
            x_scale=[seed_first, max(seed_b, 1e-5)], max_nfev=2000)
        if not solution.success:
            raise EvidenceError(f"frequency fit did not converge: {label}")
        return solution

    solution = fit(np.ones(len(n), dtype=bool))
    residual = 1200 * np.log2(actual / partial_prediction(solution.x, n))
    holdout = []
    for index in range(len(n)):
        partial_fit = fit(np.arange(len(n)) != index)
        predicted = partial_prediction(partial_fit.x, np.array([n[index]]))[0]
        holdout.append(float(1200 * np.log2(actual[index] / predicted)))
    return {"note": label, "window": window, "fit_f1_Hz": float(solution.x[0]),
            "effective_B": float(solution.x[1]), "partial_numbers": numbers,
            "observed_peak_Hz": observed, "residual_cents": residual.tolist(),
            "residual_Hz": (actual - partial_prediction(solution.x, n)).tolist(),
            "max_residual_cents": float(np.max(np.abs(residual))),
            "rms_residual_cents": float(np.sqrt(np.mean(residual ** 2))),
            "leave_one_partial_out_residual_cents": holdout,
            "max_holdout_residual_cents": max(abs(value) for value in holdout)}


def amplitude_db(value):
    return 20 * math.log10(max(float(value), 1e-300))


def c4_features(name, velocity, data, rate):
    frequency, power = spectrum(data, rate, 0.05, 0.80, detrend=True)
    selected = frequency >= 20
    total = float(np.sum(power[selected]))
    ratio = float(np.sum(power[frequency > 2500]) / total)
    prefix = int(round(0.04 * rate))
    early = np.pad(data[:int(round(0.15 * rate))], ((prefix, 0), (0, 0)))
    energy = np.mean(early ** 2, axis=1)
    cumulative = np.concatenate(([0.0], np.cumsum(energy)))
    rises = {}
    for milliseconds in (10, 20, 40):
        width = int(round(rate * milliseconds / 1000))
        envelope = np.sqrt((cumulative[width:] - cumulative[:-width]) / width)
        peak = int(np.argmax(envelope))
        maximum = float(envelope[peak])
        low = int(np.flatnonzero(envelope[:peak + 1] >= 0.10 * maximum)[0])
        high = int(np.flatnonzero(envelope[:peak + 1] >= 0.90 * maximum)[0])
        rises[str(milliseconds)] = (high - low) * 1000 / rate
    return {"name": name, "velocity": velocity,
            "peak_stereo_dBFS": amplitude_db(np.max(np.abs(data))),
            "peak_mono_mean_dBFS": amplitude_db(np.max(np.abs(np.mean(data, axis=1)))),
            "centroid_stereo_power_Hz": float(np.sum(frequency[selected] * power[selected]) / total),
            "HF_stereo_power_ratio_dB": 10 * math.log10(ratio),
            "rise_rms_10_20_40ms_ms": rises}


def decay_features(data, rate, start, stop, power_domain):
    width, hop = int(round(0.1 * rate)), int(round(0.02 * rate))
    origins = np.arange(int(round(start * rate)), int(round(stop * rate)) - width + 1, hop)
    values = np.array([np.mean(data[index:index + width] ** 2) for index in origins])
    if not power_domain:
        values = np.sqrt(values)
    values /= np.max(values)
    times = (origins + width / 2) / rate
    relative = times - times[0]

    def shape(parameters):
        first, second, fast, delta = parameters
        return first * np.exp(-relative / fast) + second * np.exp(-relative / (fast + delta))

    solutions = [least_squares(lambda parameters: shape(parameters) - values, seed,
                               bounds=([0, 0, 0.02, 0.001], [10, 10, 5, 30]),
                               x_scale=[1, 1, 1, 5], max_nfev=4000)
                 for seed in ([0.9, 0.1, 0.8, 4.5], [0.5, 0.5, 0.3, 2], [0.8, 0.2, 1.0, 10])]
    successful = [solution for solution in solutions if solution.success]
    if not successful:
        raise EvidenceError("decay fit did not converge")
    best = min(successful, key=lambda solution: np.sum(solution.fun ** 2))
    first, second, fast, delta = best.x
    return {"window": [start, stop], "domain": "power" if power_domain else "RMS amplitude",
            "tau_fast_s": float(fast), "tau_slow_s": float(fast + delta),
            "coefficient_fast_fraction": float(first / (first + second)),
            "normalized_RMSE": float(np.sqrt(np.mean(best.fun ** 2))),
            "boundary_active": best.active_mask.tolist()}


def require_close(actual, expected, absolute=0.0, relative=0.0, label="measurement"):
    if not np.allclose(actual, expected, atol=absolute, rtol=relative):
        raise EvidenceError(f"frozen result mismatch: {label}")


def recompute(audio_dir, midi_dir, evidence_dir):
    manifest = read_json(evidence_dir / "manifest.json")
    if manifest.get("schema") != "pianoteq9-reference-revalidation-v1":
        raise EvidenceError("unsupported reference manifest")
    for receipt in manifest["receipts"]:
        name = receipt["path"]
        if Path(name).name != name:
            raise EvidenceError("unsafe evidence receipt path")
        checked_hash(evidence_dir / name, receipt["sha256"])
    methods = read_json(evidence_dir / "methods.json")
    if methods.get("method_id") != "task39-1-fixed-observation-v1":
        raise EvidenceError("unsupported measurement method")
    tolerance = methods["verification_tolerances"]
    audio = {}
    for case in manifest["inputs"]:
        name = case["name"]
        if Path(name).name != name:
            raise EvidenceError("unsafe reference input name")
        wav, midi = audio_dir / (name + ".wav"), midi_dir / (name + ".mid")
        checked_hash(wav, case["wav"]["sha256"])
        checked_hash(midi, case["midi"]["sha256"])
        decoded = decode_midi(midi)
        if any(decoded[key] != case["midi"][key] for key in decoded):
            raise EvidenceError(f"MIDI events differ from the frozen input: {midi}")
        audio[name] = read_audio(wav, case["wav"])
    expected_families = read_json(evidence_dir / "reference-family-checks.json")
    families = []
    for label, first, stiffness, maximum in methods["frequency"]["family_seeds"]:
        rate, data = audio["exp_a_" + label]
        result = fit_family(label, first, stiffness, maximum, data, rate)
        expected = next(item for item in expected_families if item["note"] == label)
        if result["partial_numbers"] != expected["partial_numbers"]:
            raise EvidenceError(f"candidate assignment changed: {label}")
        require_close(result["observed_peak_Hz"], expected["observed_peak_Hz"],
                      absolute=tolerance["peak_Hz"], label=label + " observed peaks")
        require_close(result["fit_f1_Hz"], expected["fit_f1_Hz"],
                      absolute=tolerance["family_f1_Hz"], label=label + " family first partial")
        require_close(result["effective_B"], expected["effective_B"],
                      relative=tolerance["family_B_relative"], label=label + " conditional stiffness")
        require_close(result["residual_cents"], expected["residual_cents"],
                      absolute=tolerance["family_residual_cents"], label=label + " residual")
        require_close(result["leave_one_partial_out_residual_cents"],
                      expected["leave_one_partial_out_residual_cents"],
                      absolute=tolerance["family_residual_cents"], label=label + " fixed-assignment holdout")
        families.append(result)
    expected = read_json(evidence_dir / "reference-parent-checks.json")
    c4 = []
    for name, velocity in (("exp_b_c4_piano", 41), ("exp_b_c4_mezzo", 70), ("exp_b_c4_forte", 98)):
        rate, data = audio[name]
        result = c4_features(name, velocity, data, rate)
        frozen = next(item for item in expected["C4"] if item["name"] == name)
        for key in ("peak_stereo_dBFS", "peak_mono_mean_dBFS", "HF_stereo_power_ratio_dB"):
            require_close(result[key], frozen[key], absolute=tolerance["metric_dB"], label=name + " " + key)
        require_close(result["centroid_stereo_power_Hz"], frozen["centroid_stereo_power_Hz"],
                      absolute=tolerance["centroid_Hz"], label=name + " power centroid")
        for window in ("10", "20", "40"):
            require_close(result["rise_rms_10_20_40ms_ms"][window],
                          frozen["rise_rms_10_20_40ms_ms"][window],
                          absolute=tolerance["rise_ms"], label=name + " causal RMS rise")
        c4.append(result)
    rate, data = audio["exp_c_c3_decay"]
    decay = []
    for start, stop in methods["C3"]["windows"]:
        for power_domain in (False, True):
            result = decay_features(data, rate, start, stop, power_domain)
            frozen = next(item for item in expected["C3_envelope_window_sensitivity"]
                          if item["window"] == result["window"] and item["domain"] == result["domain"])
            for key in ("tau_fast_s", "tau_slow_s", "normalized_RMSE"):
                require_close(result[key], frozen[key], relative=tolerance["decay_tau_relative"],
                              label="C3 output envelope " + key)
            decay.append(result)
    matrix = np.array([[1 / math.sqrt(3), 1 / math.sqrt(2), 1 / math.sqrt(6)],
                       [1 / math.sqrt(3), 0, -2 / math.sqrt(6)],
                       [1 / math.sqrt(3), -1 / math.sqrt(2), 1 / math.sqrt(6)]])
    require_close(matrix.sum(axis=0), expected["matrix_and_envelope_semantics"]["inverse_matrix_column_sums"],
                  absolute=tolerance["matrix_absolute"], label="generic matrix column sums")
    return {"schema": "pianoteq9-readonly-recomputation-v1", "method_id": methods["method_id"],
            "input_pairs_verified": len(audio), "input_hashes_and_events_verified": True,
            "frozen_result_checks_passed": True, "candidate_families": families,
            "C4": c4, "C3_output_envelope_fits": decay,
            "qualification": manifest["admission"],
            "source_ownership": manifest["cross_repository_ownership"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio-dir", type=Path, default=ROOT / "acoustic_lab/audio")
    parser.add_argument("--midi-dir", type=Path, default=ROOT / "acoustic_lab/midi")
    parser.add_argument("--evidence-dir", type=Path, default=RESULTS)
    parser.add_argument("--json", action="store_true", help="print computed results as JSON to stdout")
    args = parser.parse_args()
    try:
        result = recompute(args.audio_dir, args.midi_dir, args.evidence_dir)
    except (EvidenceError, OSError, ValueError, wave.Error, struct.error) as error:
        print(f"[error] {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Verified {result['input_pairs_verified']} reference MIDI/WAV pairs and frozen numeric results.")
        for family in result["candidate_families"]:
            print(f"{family['note']}: fit_f1={family['fit_f1_Hz']:.4f} Hz, "
                  f"B_eff={family['effective_B']:.6g}, "
                  f"max residual={family['max_residual_cents']:.3f} cents")
        difference = result["C4"][2]["HF_stereo_power_ratio_dB"] - result["C4"][1]["HF_stereo_power_ratio_dB"]
        print(f"C4 HF power ratio 70->98: {difference:.5f} dB")
        print("Conditional WAV observations only; historical rendering controls and commercial algorithm equivalence remain unknown.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
