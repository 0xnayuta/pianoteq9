#!/usr/bin/env python3
"""参考侧分音峰位置稳健性核验（只读、独立实现，不 import pilot-partial-analysis）。

目的：判定 validation-interp 中 n27-v107 的 n11/n12 异常（参考侧跨采样率峰估计差
7.2 / 5.5 cents，dev 侧双率一致）属于峰值估计伪影还是信号层（渲染输出）差异。

方法：
1) 以 pilot-partial-analysis 的 W1 口径（0.08–3.8 s、Hann、log 抛物线插值、
   L+R 功率谱）复现该工具的峰估计，作为基准管道；
2) 变参数：窗长（2.0/3.0/3.72/4.5 s）、窗函数（Hann / Blackman-Harris 7 项 /
   flat-top）、零填充（1x/8x/32x），在同一邻域重复峰定位；
3) 输出跨采样率、跨重复、跨参数的峰频率及相对 cents 差；
4) 报告邻域内全部局部极大（频率、相对功率、局部 SNR），用于检测邻近分量。

只读：不修改任何输入；输出 JSON 与控制台表格。
"""

import argparse
import json
import math
import wave
from pathlib import Path

import numpy as np


def read_wav_stereo(path):
    with wave.open(str(path), "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        frames = handle.getnframes()
        raw = handle.readframes(frames)
    if width != 3 or channels != 2:
        raise ValueError(f"unexpected format: {channels}ch/{width * 8}bit/{rate}Hz")
    data = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
    value = (data[:, 0] | (data[:, 1] << 8) | (data[:, 2] << 16)).astype(np.int64)
    value = np.where(value >= (1 << 23), value - (1 << 24), value).astype(np.float64)
    value = value.reshape(frames, 2) / float(1 << 23)
    return rate, frames, value[:, 0], value[:, 1]


def window_values(kind, length):
    if kind == "hann":
        return np.hanning(length)
    if kind == "blackman-harris":
        # 7 项 Blackman-Harris（公认低旁瓣）
        a = (0.27105140069342, 0.43329793923448, 0.21812299954311,
             0.06592544638803, 0.01081174209837, 0.00077658482522,
             0.00001388721735)
        n = np.arange(length, dtype=np.float64)
        w = np.zeros(length, dtype=np.float64)
        for k, coefficient in enumerate(a):
            w += ((-1) ** k) * coefficient * np.cos(2.0 * np.pi * k * n / (length - 1))
        return w
    if kind == "flat-top":
        a = (0.21557895, 0.41663158, 0.277263158, 0.083578947, 0.006947368)
        n = np.arange(length, dtype=np.float64)
        w = np.zeros(length, dtype=np.float64)
        for k, coefficient in enumerate(a):
            w += ((-1) ** k) * coefficient * np.cos(2.0 * np.pi * k * n / (length - 1))
        return w
    raise ValueError(kind)


def power_spectrum(left, right, rate, start_s, stop_s, window_kind, pad_factor):
    start = int(start_s * rate)
    stop = min(int(stop_s * rate), len(left))
    segment = stop - start
    window = window_values(window_kind, segment)
    spectrum_l = np.fft.rfft(left[start:stop] * window, n=segment * pad_factor)
    spectrum_r = np.fft.rfft(right[start:stop] * window, n=segment * pad_factor)
    power = (spectrum_l.real ** 2 + spectrum_l.imag ** 2
             + spectrum_r.real ** 2 + spectrum_r.imag ** 2)
    frequency = np.fft.rfftfreq(segment * pad_factor, 1.0 / rate)
    return frequency, power


def peaks_in_band(frequency, power, center, halfwidth):
    """邻域内全部局部极大 + log 抛物线插值（与基准工具同法）。"""
    low = center - halfwidth
    high = center + halfwidth
    band = (frequency >= low) & (frequency <= high)
    relative = power / np.max(power)
    indices = np.flatnonzero((relative[1:-1] > relative[:-2]) & (relative[1:-1] >= relative[2:])) + 1
    indices = indices[band[indices]]
    results = []
    for index in indices:
        x0, x1, x2 = np.log(relative[index - 1:index + 2] + 1e-30)
        denominator = x0 - 2.0 * x1 + x2
        delta = 0.5 * (x0 - x2) / denominator if denominator else 0.0
        peak = float(frequency[index] + delta * (frequency[1] - frequency[0]))
        results.append({"Hz": peak, "rel": float(relative[index]),
                        "bin_Hz": float(frequency[1] - frequency[0])})
    return sorted(results, key=lambda row: -row["rel"])


def cents(a, b):
    return 1200.0 * math.log2(a / b)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="output directory")
    parser.add_argument("--ref-root", required=True)
    parser.add_argument("--dev-root", required=True)
    options = parser.parse_args()

    ref_root = Path(options.ref_root)
    dev_root = Path(options.dev_root)
    out_dir = Path(options.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 目标：n27 三个力度双率 rep0；对照 n25/n53/n59 的 v107 双率；dev 侧同网格
    cases = []
    for velocity in (47, 79, 107):
        for rate in (44100, 48000):
            session = {44100: "s05", 48000: "s07"}[rate]
            cases.append({
                "label": f"ref-n27-v{velocity}-{rate}-rep0",
                "path": ref_root / "sessions" / f"{session}-n27-{rate}-rep0" / "units"
                        / f"n27-v{velocity}-{rate}-rep0" / "export.wav",
            })
            cases.append({
                "label": f"dev-n27-v{velocity}-{rate}",
                "path": dev_root / str(rate) / f"n27-v{velocity}.wav",
            })
    for note, sessions in ((25, {44100: "s01", 48000: "s03"}),
                           (53, {44100: "s09", 48000: "s11"}),
                           (59, {44100: "s13", 48000: "s15"})):
        for rate in (44100, 48000):
            cases.append({
                "label": f"ref-n{note}-v107-{rate}-rep0",
                "path": ref_root / "sessions" / f"{sessions[rate]}-n{note}-{rate}-rep0"
                        / "units" / f"n{note}-v107-{rate}-rep0" / "export.wav",
            })

    a4 = 440.0
    note = 27
    nominal_f1 = a4 * 2.0 ** ((note - 69) / 12.0)
    targets = {11: 11 * nominal_f1, 12: 12 * nominal_f1}

    parameters = [
        # (窗长标签, start, stop, 窗, 零填充)
        ("W1-repro", 0.08, 3.8, "hann", 8),
        ("W1-pad32", 0.08, 3.8, "hann", 32),
        ("long-4.5", 0.08, 4.58, "hann", 8),
        ("short-2.0", 0.08, 2.08, "hann", 8),
        ("BH7-3.72", 0.08, 3.8, "blackman-harris", 8),
        ("flattop-3.72", 0.08, 3.8, "flat-top", 8),
        ("W2-repro", 0.5, 4.1, "hann", 8),
    ]

    records = []
    for case in cases:
        path = Path(case["path"])
        if not path.is_file():
            records.append({"label": case["label"], "error": "missing file"})
            continue
        rate, frames, left, right = read_wav_stereo(path)
        entry = {"label": case["label"], "rate": rate, "path": str(path), "partials": {}}
        for number, center in targets.items():
            entry["partials"][number] = {}
            for name, start, stop, window_kind, pad in parameters:
                frequency, power = power_spectrum(left, right, rate, start, stop,
                                                  window_kind, pad)
                found = peaks_in_band(frequency, power, center, halfwidth=center * 0.01)
                entry["partials"][number][name] = found[:3]
        records.append(entry)

    with open(out_dir / "peak-robustness.json", "w", encoding="utf-8") as handle:
        json.dump({"schema": "devpiano-task39-2-partial-peak-robustness",
                   "ref_root": str(ref_root), "dev_root": str(dev_root),
                   "records": records}, handle, ensure_ascii=False, indent=1)

    # 控制台报告：跨采样率差（同 label 前缀、同参数、同分音，主峰的 cents 差）
    by_label = {record["label"]: record for record in records if "error" not in record}
    print("== 跨采样率主峰差（cents），按参数 ==")
    for prefix, velocity in (("n27-v47", 47), ("n27-v79", 79), ("n27-v107", 107)):
        for side, root in (("ref", "ref"), ("dev", "dev")):
            key44 = next((k for k in by_label if k.startswith(f"{root}-{prefix}-44100")), None)
            key48 = next((k for k in by_label if k.startswith(f"{root}-{prefix}-48000")), None)
            if not key44 or not key48:
                continue
            for number in (11, 12):
                row = []
                for name, *_ in parameters:
                    a = by_label[key44]["partials"][number][name]
                    b = by_label[key48]["partials"][number][name]
                    if not a or not b:
                        row.append(f"{name}: n/a")
                        continue
                    row.append(f"{name}: {cents(b[0]['Hz'], a[0]['Hz']):+.3f}")
                print(f"  {root}-{prefix} n{number}: " + " | ".join(row))
    print()
    print("== 邻域结构（主峰 + 次峰，Hz / 相对功率 dB） ==")
    for record in records:
        if "error" in record:
            continue
        for number in (11, 12):
            found = record["partials"][number]["W1-pad32"]
            text = ", ".join(f"{p['Hz']:.4f}({10 * math.log10(max(p['rel'], 1e-30)):.1f}dB)"
                             for p in found)
            print(f"  {record['label']} n{number}: {text}")


if __name__ == "__main__":
    main()
