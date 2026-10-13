#!/usr/bin/env python3
"""Task 39-2 pilot 数据分析：单元 WAV 的分音识别 + 独立留出预测检验（只读输入）。

依据：v2 预登记 `acceptance_metrics.admitted_partial_prediction`
（RMS <=1 cent、max <=3 cents on independent partials）与 `physical_admission`
（minimum_identified_partials >=5；>=3 训练分音 + >=2 未触碰分音用于预测）。
机制与 `run_acoustic_experiments.py` 的 fit_family 同源（同一非谐性模型与 cents 域最小二乘），
针对 pilot 数据结构（三个音符、双声道 24-bit）改写为批处理，并采用两阶段匹配：

- 阶段 A（初匹配）：理论基频（A4=440 均分律）+ B=2e-4 预测位置，容差 ±2%，
  仅接受相对功率 >= 1e-5（-50 dB）的峰——避开 onset 瞬态在 17-60 Hz 形成的弱伪峰；
- 拟合 (f1, B)（cents 域最小二乘，±2% 界）；
- 阶段 B（扩展匹配）：用拟合参数预测位置，容差 ±1%，相对功率 >= 1e-6（-60 dB），
  窗内多峰取最强；再拟合得到最终参数；
- 独立留出预测（method-amendment-1/2，2026-10-13）：h = max(2, N // 5) 个分音为 untouched 留出
  （确定性均匀选取；训练集 >= 3），训练拟合初值取 (theory, seed) 网格（无全数据解泄漏），
  留出峰在原始谱峰内按预测位置独立重新识别：窗口 = min(50 cents, 0.45 x 相邻分音间隔)
  （amendment-2：避免跨入相邻分音；不回退全数据配对值）；
  记录 independent_max_cents / independent_rms_cents 与逐点明细。

谱：0.08–3.8 s 或 0.5–4.1 s Hann 窗，立体声功率和（L、R 各自 FFT 后功率相加，非相干下混）；
峰：局部极大 + 抛物线插值，低限 40 Hz（C2 基频 65.4 Hz 之上，避开瞬态伪峰区）。

输入网格：`--preset pilot|register|corpus|bridge|anchors2|treble96|midfill`；`corpus`（training 12 音 × 3 力度 × 2 rate）需多次
`--batch`——复用单元来自 pilot-v2 / register 批次，新单元来自 corpus 批次，按会话名在首个命中的根下查找。
`treble96`（P3：96 kHz 高音区 {87,93,99,105,108}）需配合 `--max-freq 40000`；`midfill`（P3：48 kHz {25,27,49,51,64,74}）用默认口径。

高音区默认（2026-10-13 批准的正式方法）：`note >= --snr-min-note`（默认 72）时默认启用局部 SNR
准入通道（默认 25 dB：峰值 ±3% 带内功率中位数为噪声地板，>= 阈值且相对功率 >= 1e-9 准入）
并追加扩展 stiffness 种子（至 3e-2）；`note <= 60` 走原路径逐位不变。
`--snr-admission-db none` 关闭该通道以复现同口径结果。

输出：`partial-analysis.json`（逐单元）+ `partial-analysis-summary.json`（族汇总与判据对照）。
"""

import argparse
import hashlib
import json
import math
import wave
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

NOTE_NAMES = {21: "A0", 24: "C1", 28: "E1", 33: "A1", 36: "C2", 40: "E2", 43: "G2", 44: "G#2",
              45: "A2", 47: "B2", 48: "C3", 60: "C4", 69: "A4", 72: "C5", 84: "C6", 91: "G6",
              95: "B6", 96: "C7", 108: "C8"}
VELOCITIES = [41, 70, 98]
RATES = [44100, 48000]
PRESETS = {
    "pilot": {  # v2 pilot：n36/48/60
        "notes": {36: 65.4064, 48: 130.8128, 60: 261.6256},  # 理论基频（A4=440）
        "sessions": [
            ("s01-n60-44100-rep0", 60, 44100, 0), ("s02-n60-48000-rep0", 60, 48000, 0),
            ("s03-n60-44100-rep1", 60, 44100, 1), ("s04-n60-48000-rep1", 60, 48000, 1),
            ("s05-n36-44100-rep0", 36, 44100, 0), ("s06-n36-48000-rep0", 36, 48000, 0),
            ("s07-n36-44100-rep1", 36, 44100, 1), ("s08-n36-48000-rep1", 36, 48000, 1),
            ("s09-n48-44100-rep0", 48, 44100, 0), ("s10-n48-44100-rep1", 48, 44100, 1),
            ("s11-n48-48000-rep0", 48, 48000, 0), ("s12-n48-48000-rep1", 48, 48000, 1),
        ],
    },
    "register": {  # 高音区 lead-in：n72/84/96
        "notes": {72: 523.2511, 84: 1046.5022, 96: 2093.0045},
        "sessions": [
            ("s01-n72-44100-rep0", 72, 44100, 0), ("s02-n72-48000-rep0", 72, 48000, 0),
            ("s03-n72-44100-rep1", 72, 44100, 1), ("s04-n72-48000-rep1", 72, 48000, 1),
            ("s05-n84-44100-rep0", 84, 44100, 0), ("s06-n84-48000-rep0", 84, 48000, 0),
            ("s07-n84-44100-rep1", 84, 44100, 1), ("s08-n84-48000-rep1", 84, 48000, 1),
            ("s09-n96-44100-rep0", 96, 44100, 0), ("s10-n96-44100-rep1", 96, 44100, 1),
            ("s11-n96-48000-rep0", 96, 48000, 0), ("s12-n96-48000-rep1", 96, 48000, 1),
        ],
    },
    "corpus": {  # training corpus：12 音 × 3 力度 × 2 rate（复用 rep0 单元 + 新采集）
        # 多批次输入：--batch 可重复；复用单元来自 pilot-v2 / register 批次，新单元来自 corpus 批次
        "notes": {21: 27.5, 24: 32.7032, 36: 65.4064, 43: 97.9989, 44: 103.8262, 48: 130.8128,
                  60: 261.6256, 69: 440.0, 72: 523.2511, 84: 1046.5022, 96: 2093.0045, 108: 4186.009},
        "sessions": [
            # 复用 rep0（pilot-v2 批次）：n36/48/60
            ("s05-n36-44100-rep0", 36, 44100, 0), ("s06-n36-48000-rep0", 36, 48000, 0),
            ("s09-n48-44100-rep0", 48, 44100, 0), ("s11-n48-48000-rep0", 48, 48000, 0),
            ("s01-n60-44100-rep0", 60, 44100, 0), ("s02-n60-48000-rep0", 60, 48000, 0),
            # 复用 rep0（register 批次）：n72/84/96
            ("s01-n72-44100-rep0", 72, 44100, 0), ("s02-n72-48000-rep0", 72, 48000, 0),
            ("s05-n84-44100-rep0", 84, 44100, 0), ("s06-n84-48000-rep0", 84, 48000, 0),
            ("s09-n96-44100-rep0", 96, 44100, 0), ("s11-n96-48000-rep0", 96, 48000, 0),
            # 新采集（corpus 批次）：n44/43/69 先行，n24/21/108 后置
            ("s01-n44-44100-rep0", 44, 44100, 0), ("s02-n44-48000-rep0", 44, 48000, 0),
            ("s03-n43-44100-rep0", 43, 44100, 0), ("s04-n43-48000-rep0", 43, 48000, 0),
            ("s05-n69-44100-rep0", 69, 44100, 0), ("s06-n69-48000-rep0", 69, 48000, 0),
            ("s07-n24-44100-rep0", 24, 44100, 0), ("s08-n24-48000-rep0", 24, 48000, 0),
            ("s09-n21-44100-rep0", 21, 44100, 0), ("s10-n21-48000-rep0", 21, 48000, 0),
            ("s11-n108-44100-rep0", 108, 44100, 0), ("s12-n108-48000-rep0", 108, 48000, 0),
        ],
    },
    "bridge": {  # 桥界区段诊断：n45/n47（G2-C3 之间的白键锚点）
        "notes": {45: 110.0, 47: 123.4708},
        "sessions": [
            ("s01-n45-44100-rep0", 45, 44100, 0), ("s02-n45-48000-rep0", 45, 48000, 0),
            ("s03-n47-44100-rep0", 47, 44100, 0), ("s04-n47-48000-rep0", 47, 48000, 0),
        ],
    },
    "anchors2": {  # 补充锚点：n28/33/40（低音 k 符号变化区）+ n91/95（高音 k 加速判定）
        "notes": {28: 41.2034, 33: 55.0, 40: 82.4069, 91: 1567.9817, 95: 1975.5332},
        "sessions": [
            ("s01-n28-44100-rep0", 28, 44100, 0), ("s02-n28-48000-rep0", 28, 48000, 0),
            ("s03-n33-44100-rep0", 33, 44100, 0), ("s04-n33-48000-rep0", 33, 48000, 0),
            ("s05-n40-44100-rep0", 40, 44100, 0), ("s06-n40-48000-rep0", 40, 48000, 0),
            ("s07-n91-44100-rep0", 91, 44100, 0), ("s08-n91-48000-rep0", 91, 48000, 0),
            ("s09-n95-44100-rep0", 95, 44100, 0), ("s10-n95-48000-rep0", 95, 48000, 0),
        ],
    },
    "treble96": {  # P3：96 kHz 高音区新验证集（未看过参考的音高；--max-freq 40000）
        "notes": {87: 1244.5081, 93: 1760.0, 99: 2489.0162, 105: 3520.0, 108: 4186.0090},
        "sessions": [
            ("s01-n87-96000-rep0", 87, 96000, 0),
            ("s02-n93-96000-rep0", 93, 96000, 0),
            ("s03-n99-96000-rep0", 99, 96000, 0),
            ("s04-n105-96000-rep0", 105, 96000, 0),
            ("s05-n108-96000-rep0", 108, 96000, 0),
        ],
    },
    "midfill": {  # P3：48 kHz 中低音加密新验证集（24->28 与 48->60 曲率诊断确认）
        "notes": {25: 34.6478, 27: 38.8909, 49: 138.5913, 51: 155.5635, 64: 329.6276, 74: 587.3295},
        "sessions": [
            ("s01-n25-48000-rep0", 25, 48000, 0),
            ("s02-n27-48000-rep0", 27, 48000, 0),
            ("s03-n49-48000-rep0", 49, 48000, 0),
            ("s04-n51-48000-rep0", 51, 48000, 0),
            ("s05-n64-48000-rep0", 64, 48000, 0),
            ("s06-n74-48000-rep0", 74, 48000, 0),
        ],
    },
}
NOTES = PRESETS["pilot"]["notes"]
SESSIONS = PRESETS["pilot"]["sessions"]

WINDOWS = {"W1": (0.08, 3.8), "W2": (0.5, 4.1)}
LOW_FREQ = 40.0
MAX_FREQ = 20000.0  # 默认口径；96 kHz 采集用 --max-freq 40000（见 runbook-treble96）
SEED_STIFFNESS = 1e-4
DEFAULT_SEEDS = (3e-5, 5e-5, 8e-5, 1.2e-4, 2e-4)
EXTENDED_SEEDS = DEFAULT_SEEDS + (4e-4, 8e-4, 1.6e-3, 3e-3, 7e-3, 1.5e-2, 3e-2)
SEEDS = DEFAULT_SEEDS  # analyze_unit 按音符选择 DEFAULT/EXTENDED
SNR_ADMISSION_DB = 25.0  # 高音区正式方法：局部 SNR 准入阈值（dB）；None = 关闭（同口径复现）
SNR_MIN_NOTE = 72  # 启用 SNR 通道与扩展种子的最低 MIDI 音符（高音区）
STAGE_A_TOL, STAGE_A_REL = 0.015, 1e-5
STAGE_B_TOL, STAGE_B_REL = 0.007, 1e-6
NEAREST_REL = 1e-7  # nearest 精化轮专用阈值：容许被附加强峰遮蔽的弱真分音（如 C2-v98 n=72 的 -65 dB 真峰）
EXPANSION_LEVELS = (10, 16, 24, 32, 40, 48, 60, 80, 120, 160, 220, 300)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


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


def power_spectrum(left, right, rate, window):
    start = int(window[0] * rate)
    stop = min(int(window[1] * rate), len(left))
    hann = np.hanning(stop - start)
    spectrum_l = np.fft.rfft(left[start:stop] * hann)
    spectrum_r = np.fft.rfft(right[start:stop] * hann)
    power = spectrum_l.real ** 2 + spectrum_l.imag ** 2 + spectrum_r.real ** 2 + spectrum_r.imag ** 2
    return np.fft.rfftfreq(stop - start, 1.0 / rate), power


def spectral_peaks(frequency, power, low, high):
    """返回 (峰频率, 相对功率, 局部SNR dB) 数组；相对功率 = power / max(power)。

    局部 SNR：以峰为中心 ±3% 带内功率中位数（排除峰 ±0.2% 自身）作为噪声地板。
    """
    relative = power / np.max(power)
    candidates = np.flatnonzero((relative[1:-1] > relative[:-2]) & (relative[1:-1] >= relative[2:])) + 1
    candidates = candidates[(frequency[candidates] >= low) & (frequency[candidates] < high)
                            & (relative[candidates] > 1e-9)]
    refined, values, snrs = [], [], []
    for index in candidates:
        left, middle, right = np.log(relative[index - 1:index + 2] + 1e-30)
        denominator = left - 2 * middle + right
        delta = 0.5 * (left - right) / denominator if denominator else 0.0
        peak_frequency = float(frequency[index] + delta * (frequency[1] - frequency[0]))
        refined.append(peak_frequency)
        values.append(float(relative[index]))
        i0 = int(np.searchsorted(frequency, peak_frequency * 0.97))
        i1 = int(np.searchsorted(frequency, peak_frequency * 1.03))
        e0 = int(np.searchsorted(frequency, peak_frequency * 0.998))
        e1 = int(np.searchsorted(frequency, peak_frequency * 1.002))
        band = power[max(i0, 0):max(i1, 1)]
        if band.size:
            exclude = np.zeros(band.size, dtype=bool)
            exclude[max(e0 - max(i0, 0), 0):max(e1 - max(i0, 0), 0)] = True
            floor = np.median(band[~exclude]) if (~exclude).any() else np.median(band)
            snrs.append(float(10.0 * np.log10(max(power[index], 1e-30) / max(floor, 1e-30))))
        else:
            snrs.append(0.0)
    return np.array(refined), np.array(values), np.array(snrs)


def partial_prediction(parameters, numbers):
    first, stiffness = parameters
    return numbers * first * np.sqrt((1 + stiffness * numbers ** 2) / (1 + stiffness))


def match_partials(peaks, rel, snr, first, stiffness, tolerance, min_rel,
                   maximum=400, mode="strongest", min_snr=None):
    """按模型预测位置匹配峰；mode=strongest 取窗内最强，mode=nearest 取最靠近预测。

    峰值准入：rel >= min_rel；若给定 min_snr，则追加“rel >= 1e-9 且局部 SNR >= min_snr”通道
    （用于动态范围大的高音区，真分音相对基频低但局部 SNR 很高）。
    """
    numbers, observed = [], []
    for number in range(1, maximum + 1):
        prediction = float(partial_prediction([first, stiffness], np.array([number]))[0])
        if prediction > MAX_FREQ:
            break
        inside = np.flatnonzero(np.abs(peaks - prediction) / prediction <= tolerance)
        if inside.size:
            keep = rel[inside] >= min_rel
            if min_snr is not None:
                keep = keep | ((snr[inside] >= min_snr) & (rel[inside] >= 1e-9))
            inside = inside[keep]
        if len(inside):
            if mode == "nearest":
                best = inside[np.argmin(np.abs(peaks[inside] - prediction))]
            else:
                best = inside[np.argmax(rel[inside])]
            numbers.append(number)
            observed.append(float(peaks[best]))
    return np.array(numbers), np.array(observed)


def fit(actual, numbers, seed_first, seed_stiffness):
    solution = least_squares(
        lambda parameters: 1200 * np.log2(actual / partial_prediction(parameters, numbers)),
        [seed_first, seed_stiffness],
        bounds=([seed_first * 0.98, 0], [seed_first * 1.02, 0.3]),
        x_scale=[seed_first, max(seed_stiffness, 1e-5)], max_nfev=4000)
    if not solution.success:
        raise ValueError("frequency fit did not converge")
    return solution


def staged_match(peaks, rel, snr, theory, seed_stiffness=SEED_STIFFNESS, min_snr=None):
    """逐级扩展匹配：低分音可靠区起步，随拟合精化逐步扩展分音编号上限。

    单阶段大容差匹配会在 seed stiffness 偏离真实值数倍时把高分音错配到邻近峰，
    形成自洽但错误的解（f1 偏移 ~9 cents、B 偏差 4 倍）；逐级扩展从 n=1..6
    的可靠区出发，每扩展一级重新拟合，使预测位置始终与真实峰对齐。
    """
    first, stiffness = theory, seed_stiffness
    numbers, observed = match_partials(peaks, rel, snr, first, stiffness, STAGE_A_TOL, STAGE_A_REL,
                                       min_snr=min_snr)
    if len(numbers) < 3:
        raise ValueError(f"stage-A insufficient partials: {len(numbers)}")
    solution = fit(observed, numbers, first, stiffness)
    first, stiffness = float(solution.x[0]), float(solution.x[1])
    for level in EXPANSION_LEVELS:
        expanded_numbers, expanded_observed = match_partials(
            peaks, rel, snr, first, stiffness, STAGE_A_TOL, STAGE_A_REL, maximum=level, min_snr=min_snr)
        if len(expanded_numbers) > len(numbers):
            solution = fit(expanded_observed, expanded_numbers, first, stiffness)
            first, stiffness = float(solution.x[0]), float(solution.x[1])
            numbers, observed = expanded_numbers, expanded_observed
    numbers, observed = match_partials(peaks, rel, snr, first, stiffness, STAGE_B_TOL, STAGE_B_REL,
                                       min_snr=min_snr)
    if len(numbers) < 5:
        raise ValueError(f"insufficient identified partials after staged match: {len(numbers)}")
    solution = fit(observed, numbers, first, stiffness)
    return float(solution.x[0]), float(solution.x[1]), numbers, observed


def staged_match_multi(peaks, rel, snr, theory, seeds=SEEDS, min_snr=None):
    """多起点逐级匹配：以多个 stiffness 起点求解，按 (残差>3 cents, -分音数, 残差) 择优。

    真实解在"分音多且残差小"两个维度同时占优；错误收敛解分音少且残差大。
    默认起点覆盖钢琴低音 B 的常见量级（3e-5 … 2e-4）；高音区（B 可达 1e-2 量级）
    由调用方传入扩展种子表。
    """
    best = None
    best_key = None
    for seed in seeds:
        try:
            first, stiffness, numbers, observed = staged_match(peaks, rel, snr, theory, seed, min_snr=min_snr)
        except ValueError:
            continue
        residual = 1200 * np.log2(observed / partial_prediction([first, stiffness], numbers))
        max_residual = float(np.max(np.abs(residual)))
        key = (max_residual > 3.0, -len(numbers), max_residual)
        if best_key is None or key < best_key:
            best, best_key = (first, stiffness, numbers, observed), key
    if best is None:
        raise ValueError("no staged match converged from any stiffness seed")
    return best


HOLDOUT_TOLERANCE_CENTS = 50.0  # 上限；低音区相邻分音间隔远大于此
HOLDOUT_NEIGHBOUR_FRACTION = 0.45  # 窗口不得超过相邻分音间隔的此比例（amendment-2）
HOLDOUT_REL_FLOOR = 1e-7


def holdout_window_cents(number):
    """独立识别窗口：min(50 cents, 0.45 x 相邻分音间隔)，避免跨入相邻分音。"""
    neighbour_interval = 1200.0 * math.log2((number + 1.0) / float(number))
    return min(HOLDOUT_TOLERANCE_CENTS, HOLDOUT_NEIGHBOUR_FRACTION * neighbour_interval)


def independent_split_prediction(peaks, rel, snr, theory, numbers, observed, seeds, min_snr):
    """预登记 physical_admission.fitting_minimum 的独立预测检验（见 task39-2-method-amendment-1.md）。

    - 留出集 h = max(2, N // 5)，确定性均匀选取（np.linspace 中间点）；训练集 = 其余（需 >= 3）；
    - 训练拟合初值取 (theory, seed) 网格，多起点取训练残差最小者（不使用全数据拟合解）；
    - 留出峰在原始谱峰内按 |Δcents| <= 50 窗口独立重新识别（不回退全数据配对值）。
    """
    count = len(numbers)
    holdout_size = max(2, count // 5)
    if count - holdout_size < 3:
        return {"status": "insufficient_training_partials", "holdout_size": holdout_size, "details": []}
    candidates = np.round(np.linspace(0, count - 1, holdout_size + 2)[1:-1]).astype(int)
    holdout_indices = sorted({int(index) for index in candidates})
    holdout_set = set(holdout_indices)
    keep_indices = np.array([index for index in range(count) if index not in holdout_set])
    keep_numbers, keep_observed = numbers[keep_indices], observed[keep_indices]

    best_solution, best_residual = None, None
    for seed in seeds:
        try:
            solution = fit(keep_observed, keep_numbers, theory, seed)
        except ValueError:
            continue
        residual = float(np.max(np.abs(1200 * np.log2(
            keep_observed / partial_prediction(solution.x, keep_numbers)))))
        if best_residual is None or residual < best_residual:
            best_solution, best_residual = solution, residual
    if best_solution is None:
        return {"status": "training_fit_failed", "holdout_size": len(holdout_indices), "details": []}
    train_first, train_stiffness = float(best_solution.x[0]), float(best_solution.x[1])

    details, errors = [], []
    for index in holdout_indices:
        number = int(numbers[index])
        predicted = float(partial_prediction([train_first, train_stiffness], np.array([number]))[0])
        window = np.flatnonzero(np.abs(1200.0 * np.log2(peaks / predicted)) <= holdout_window_cents(number))
        if window.size:
            qualified = rel[window] >= HOLDOUT_REL_FLOOR
            if min_snr is not None:
                qualified = qualified | ((snr[window] >= min_snr) & (rel[window] >= 1e-9))
            window = window[qualified]
        if window.size:
            picked = float(peaks[window[np.argmax(rel[window])]])
            error = float(1200.0 * np.log2(picked / predicted))
            errors.append(error)
            details.append({"number": number, "predicted_Hz": predicted,
                            "reidentified_Hz": picked, "error_cents": error})
        else:
            details.append({"number": number, "predicted_Hz": predicted,
                            "reidentified_Hz": None, "error_cents": None})
    if not errors:
        return {"status": "no_holdout_peak_reidentified", "holdout_size": len(holdout_indices),
                "train_f1_Hz": train_first, "train_effective_B": train_stiffness, "details": details}
    return {"status": "ok",
            "holdout_size": len(holdout_indices),
            "training_size": int(keep_indices.size),
            "train_f1_Hz": train_first,
            "train_effective_B": train_stiffness,
            "max_cents": float(np.max(np.abs(errors))),
            "rms_cents": float(np.sqrt(np.mean(np.square(errors)))),
            "details": details}


def analyze_unit(path, note):
    rate, frames, left, right = read_wav_stereo(path)
    theory = NOTES[note]
    min_snr = SNR_ADMISSION_DB if (SNR_ADMISSION_DB is not None and note >= SNR_MIN_NOTE) else None
    seeds = EXTENDED_SEEDS if note >= SNR_MIN_NOTE else DEFAULT_SEEDS
    result = {"rate": rate, "frames": frames, "windows": {}}
    main = None
    for name, window in WINDOWS.items():
        frequency, power = power_spectrum(left, right, rate, window)
        peaks, rel, snr = spectral_peaks(frequency, power, LOW_FREQ, MAX_FREQ)
        first, stiffness, numbers, observed = staged_match_multi(
            peaks, rel, snr, theory, seeds=seeds, min_snr=min_snr)
        # 最近邻精化轮：修正"窗内更强非族峰遮蔽真分音"的情形
        # （如 C2-v98 的 n=72 处存在 -50 dB 附加峰遮蔽 -65 dB 真分音）
        refined_numbers, refined_observed = match_partials(
            peaks, rel, snr, first, stiffness, STAGE_B_TOL, NEAREST_REL, mode="nearest",
            min_snr=min_snr)
        if len(refined_numbers) >= 5:
            refined_solution = fit(refined_observed, refined_numbers, first, stiffness)
            refined_first = float(refined_solution.x[0])
            refined_stiffness = float(refined_solution.x[1])
            current_max = float(np.max(np.abs(1200 * np.log2(
                observed / partial_prediction([first, stiffness], numbers)))))
            refined_max = float(np.max(np.abs(1200 * np.log2(
                refined_observed / partial_prediction([refined_first, refined_stiffness], refined_numbers)))))
            if refined_max <= current_max:
                first, stiffness, numbers, observed = refined_first, refined_stiffness, refined_numbers, refined_observed
        residual = 1200 * np.log2(observed / partial_prediction([first, stiffness], numbers))
        independent = independent_split_prediction(peaks, rel, snr, theory, numbers, observed, seeds, min_snr)
        result["windows"][name] = {
            "identified_partials": int(len(numbers)),
            "partial_numbers": [int(n) for n in numbers],
            "observed_peak_Hz": [float(v) for v in observed],
            "f1_Hz": first,
            "effective_B": stiffness,
            "residual_cents": [float(v) for v in residual],
            "max_residual_cents": float(np.max(np.abs(residual))),
            "rms_residual_cents": float(np.sqrt(np.mean(residual ** 2))),
            "independent_prediction": independent,
        }
        if name == "W1":
            main = result["windows"][name]
    result["f1_window_spread_cents"] = float(1200 * math.log2(
        result["windows"]["W1"]["f1_Hz"] / result["windows"]["W2"]["f1_Hz"]))
    result["f1_Hz"] = main["f1_Hz"]
    result["effective_B"] = main["effective_B"]
    result["identified_partials"] = main["identified_partials"]
    result["independent_status"] = main["independent_prediction"]["status"]
    result["independent_max_cents"] = main["independent_prediction"].get("max_cents")
    result["independent_rms_cents"] = main["independent_prediction"].get("rms_cents")
    return result


def _snr_threshold(text):
    """CLI 值解析：'none' 关闭 SNR 通道；否则解析为 dB 阈值。"""
    if text.strip().lower() == "none":
        return None
    return float(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True, action="append",
                        help="pilot batch root (WSL path); repeat for multi-batch corpora")
    parser.add_argument("--out", required=True, help="output directory (WSL path)")
    parser.add_argument("--preset", choices=sorted(PRESETS), default="pilot",
                        help="input grid preset (pilot: n36/48/60; register: n72/84/96; corpus: training 12 notes; "
                             "bridge: n45/47; anchors2: n28/33/40/91/95)")
    parser.add_argument("--snr-admission-db", type=_snr_threshold, default=25.0,
                        help="local-SNR peak admission threshold (dB) at/above --snr-min-note; "
                             "default 25 (adopted high-register method); pass 'none' to disable")
    parser.add_argument("--snr-min-note", type=int, default=72,
                        help="lowest MIDI note for the SNR channel and extended stiffness seeds")
    parser.add_argument("--max-freq", type=float, default=20000.0,
                        help="peak-search and model upper frequency in Hz (default 20000; "
                             "use 40000 for 96 kHz captures, where treble partials extend above 20 kHz)")
    options = parser.parse_args()
    global NOTES, SESSIONS, SNR_ADMISSION_DB, SNR_MIN_NOTE, MAX_FREQ  # noqa: PLW0603 - 输入网格/通道由 CLI 决定
    NOTES, SESSIONS = PRESETS[options.preset]["notes"], PRESETS[options.preset]["sessions"]
    SNR_ADMISSION_DB = options.snr_admission_db
    SNR_MIN_NOTE = options.snr_min_note
    MAX_FREQ = options.max_freq
    batches = [Path(value) for value in options.batch]
    if not any((root / "sessions" / session).is_dir() for root in batches for session, *_ in SESSIONS):
        raise SystemExit(
            f"no expected session directory for preset '{options.preset}' under any --batch root "
            f"(expected e.g. {SESSIONS[0][0]}); check --preset/--batch")
    out_dir = Path(options.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    units = {}
    failures = []
    for session, note, rate, rep in SESSIONS:
        root = next((candidate for candidate in batches
                     if (candidate / "sessions" / session).is_dir()), None)
        for velocity in VELOCITIES:
            unit = f"n{note}-v{velocity}-{rate}-rep{rep}"
            wav = (root / "sessions" / session / "units" / unit / "export.wav") if root else None
            if wav is None or not wav.is_file():
                failures.append({"unit": unit, "reason": "missing wav"})
                continue
            try:
                analysis = analyze_unit(wav, note)
                analysis.update({"unit": unit, "session": session, "note": note,
                                 "note_name": NOTE_NAMES[note], "velocity": velocity,
                                 "rate": rate, "repeat": rep, "wav_sha256": sha256(wav)})
                units[unit] = analysis
                independent_max = analysis["independent_max_cents"]
                independent_text = (f"indep max={independent_max:.3f} rms={analysis['independent_rms_cents']:.3f}"
                                    if independent_max is not None
                                    else f"indep {analysis['independent_status']}")
                print(f"{unit}: partials={analysis['identified_partials']} "
                      f"f1={analysis['f1_Hz']:.3f} B={analysis['effective_B']:.4e} "
                      f"{independent_text} "
                      f"spread={analysis['f1_window_spread_cents']:.3f} cents", flush=True)
            except Exception as error:  # noqa: BLE001 - 记录失败单元而不中断批次
                failures.append({"unit": unit, "reason": str(error)})
                print(f"{unit}: FAILED {error}", flush=True)

    summary = {"schema": "devpiano-task39-2-pilot-partial-analysis",
               "batch": str(batches[0]) if len(batches) == 1 else [str(root) for root in batches],
               "units_total": len(SESSIONS) * len(VELOCITIES),
               "units_analyzed": len(units), "failures": failures,
               "criteria": {
                   "admitted_partial_prediction": "max <=3 cents and RMS <=1 cent on independent split holdout partials (method-amendment-1)",
                   "estimator_window_spread": "<=1 cent for admitted stationary line",
                   "minimum_identified_partials": 5},
               "families": {}}
    for note in NOTES:
        for velocity in VELOCITIES:
            for rate in sorted({u["rate"] for u in units.values()}):
                rows = [u for u in units.values() if u["note"] == note and u["velocity"] == velocity and u["rate"] == rate]
                if not rows:
                    continue
                key = f"n{note}-v{velocity}-{rate}"
                missing = [u["unit"] for u in rows if u["independent_max_cents"] is None]
                entry = {"note_name": NOTE_NAMES[note], "units": [u["unit"] for u in rows],
                         "independent_max_cents": None if missing else max(u["independent_max_cents"] for u in rows),
                         "independent_rms_cents": None if missing else max(u["independent_rms_cents"] for u in rows),
                         "independent_missing_units": missing,
                         "identified_partials": min(u["identified_partials"] for u in rows),
                         "f1_Hz": [u["f1_Hz"] for u in rows],
                         "effective_B": [u["effective_B"] for u in rows],
                         "window_spread_cents": max(abs(u["f1_window_spread_cents"]) for u in rows)}
                if len(rows) == 2:
                    a, b = sorted(rows, key=lambda u: u["repeat"])
                    pair_delta = (None if a["independent_max_cents"] is None or b["independent_max_cents"] is None
                                  else float(abs(a["independent_max_cents"] - b["independent_max_cents"])))
                    entry["cross_repeat"] = {
                        "f1_delta_cents": float(1200 * math.log2(a["f1_Hz"] / b["f1_Hz"])),
                        "effective_B_relative_delta": float(abs(a["effective_B"] - b["effective_B"]) / max(a["effective_B"], b["effective_B"])),
                        "independent_max_delta_cents": pair_delta,
                    }
                entry["pass_max"] = entry["independent_max_cents"] is not None and entry["independent_max_cents"] <= 3.0
                entry["pass_rms"] = entry["independent_rms_cents"] is not None and entry["independent_rms_cents"] <= 1.0
                entry["pass_spread"] = entry["window_spread_cents"] <= 1.0
                entry["pass_partials"] = entry["identified_partials"] >= 5
                summary["families"][key] = entry

    with open(out_dir / "partial-analysis.json", "w", encoding="utf-8") as handle:
        json.dump({"summary": summary, "units": units}, handle, indent=1, ensure_ascii=False)
    with open(out_dir / "partial-analysis-summary.json", "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=1, ensure_ascii=False)
    passed = sum(1 for f in summary["families"].values()
                 if f["pass_max"] and f["pass_rms"] and f["pass_spread"] and f["pass_partials"])
    print(f"\nfamilies: {len(summary['families'])}, all-criteria pass: {passed}, failures: {len(failures)}")
    for key, family in summary["families"].items():
        status = "PASS" if (family["pass_max"] and family["pass_rms"] and family["pass_spread"] and family["pass_partials"]) else "FAIL"
        max_text = "n/a" if family["independent_max_cents"] is None else f"{family['independent_max_cents']:.3f}"
        rms_text = "n/a" if family["independent_rms_cents"] is None else f"{family['independent_rms_cents']:.3f}"
        print(f"  {key}: {status} max={max_text} rms={rms_text} "
              f"partials={family['identified_partials']} spread={family['window_spread_cents']:.3f}")


if __name__ == "__main__":
    main()
