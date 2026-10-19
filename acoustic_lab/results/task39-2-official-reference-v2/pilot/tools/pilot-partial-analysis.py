#!/usr/bin/env python3
"""Task 39-2 pilot 数据分析：单元 WAV 的分音识别 + 独立留出预测检验（只读输入）。

依据：v2 预登记 `acceptance_metrics.admitted_partial_prediction`
（RMS <=1 cent、max <=3 cents on independent partials）与 `physical_admission`
（minimum_identified_partials >=5；>=3 训练分音 + >=2 未触碰分音用于预测）。
机制与 `run_acoustic_experiments.py` 的 fit_family 同源（同一非谐性模型与 cents 域最小二乘），
针对 pilot 数据结构（三个音符、双声道 24-bit）改写为批处理，并采用两阶段匹配：

- 阶段 A：理论基频与多个 B 种子，仅第 1--6 分音起步，容差 ±1.5%，相对功率 >=1e-5；
- 每级扩展重新拟合 (f1,B)，再按 ±0.7%、相对功率 >=1e-6 完成阶段 B；
- strongest/nearest 只生成候选，实际单分量估计由共享 sampled observer 决定；
  原 FFT 候选族、逐种子轨迹及逐窗失败永久保留，>=5 合格观察才重新拟合；
- 独立留出预测（method-amendment-1/2，2026-10-13）：h = max(2, N // 5) 个分音为 untouched 留出
  （确定性均匀选取；训练集 >= 3），训练拟合初值取 (theory, seed) 网格（无全数据解泄漏），
  留出峰在原始谱峰内按预测位置独立重新识别：窗口 = min(50 cents, 0.45 x 相邻分音间隔)
  （amendment-2：避免跨入相邻分音；不回退全数据配对值）；
  记录 independent_max_cents / independent_rms_cents 与逐点明细。

谱候选：0.08–3.8 s / 0.5–4.1 s Hann、立体声功率和、局部极大及插值，低限 min(40 Hz, theory/2)。
观测器保留复数双声道采样窗，并列单频/同频双衰减/两频/三频解释与条件频率区间。

输入网格：`--preset pilot|register|corpus|bridge|anchors2|midfill|interp|interpval`；`corpus`（training 12 音 × 3 力度 × 2 rate）需多次
`--batch`——复用单元来自 pilot-v2 / register 批次，新单元来自 corpus 批次，按会话名在首个命中的根下查找。
`midfill`（P3：48 kHz {25,27,49,51,64,74}）用默认口径；`interp`（P3 interp-training：{26,52,57} × 3 力度 × 2 rate × 2 reps = 36 单元）用默认口径；
`interpval`（P3 interp 验证集：{25,27,53,59} × 力度 47/79/107 × 2 rate × 2 reps = 48 单元）用默认口径；
`interpval2`（P3 后继验证集：{29,55,67,88} × 力度 47/79/107 × 2 rate × 2 reps = 48 单元）用默认口径；
treble96 已因参考环境限制关闭，不提供执行入口。

高音区仍按 MIDI>=72 启用 25 dB 局部 SNR 通道与扩展 B 种子。
本轮共同观察器改变所有音区研究分析；历史正式行为仅由归档工具复现，
不以新工具复算恢复旧判决或盲证据身份。CLI 的通道开关只用于开发诊断。

时间轴与坐标（v3 NoteOn 相对坐标，2026-10-15）：`analyze_samples` / `analyze_unit` 必须显式传入
`timing=`，没有默认原点，也不做首非零/相关推断。
- `timing={"coordinate":"file_absolute"}`：消费数据诊断域（旧批绝对秒窗，int() 截断口径逐位保留）；
- `coordinate="note_on_relative"`：必须给出 sample_rate/frames/note_on_sample/note_off_sample/
  evidence_role；窗界 = note_on_sample + llround(相对秒*rate)（半远离零），半开 [start,stop)，
  频谱与观测器共用同一段整数样本，不再做 float*rate 重算；W2 止于首个释放样本之前，
  越界窗只失败该窗，不裁剪、不提升另一窗；
- `evidence_role` 支持 `synthetic_fixture`（合成夹具）、`dev_render_verification`（A4 dev render 报告）
  与 `reference_origin_authenticated`（A5 参考原点证书 + 实际 MIDI 事件生成的逐单元报告）；
  后两者只能经 `load_timing_report` 登记，绝不互相改标。

输出：`partial-analysis.json`（逐单元）+ `partial-analysis-summary.json`（族汇总与判据对照）。
单 WAV 冒烟（NoteOn 相对坐标）：`--wav FILE --note N --timing-report FILE --out 全新目录`（与 --batch 互斥）。
"""

import argparse
import hashlib
import importlib.util
import json
import math
import wave
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

OBSERVER_PATH = Path(__file__).with_name("partial-observer.py")
observer_spec = importlib.util.spec_from_file_location("partial_observer", OBSERVER_PATH)
observer = importlib.util.module_from_spec(observer_spec)
observer_spec.loader.exec_module(observer)

NOTE_NAMES = {21: "A0", 24: "C1", 25: "C#1", 26: "D1", 27: "D#1", 28: "E1", 29: "F1", 33: "A1",
              36: "C2", 40: "E2", 43: "G2", 44: "G#2", 45: "A2", 47: "B2", 48: "C3",
              49: "C#3", 51: "D#3", 52: "E3", 53: "F3", 55: "G3", 57: "A3", 59: "B3", 60: "C4",
              64: "E4", 67: "G4", 69: "A4", 72: "C5", 74: "D5", 84: "C6", 88: "E6", 91: "G6",
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
    "interp": {  # P3 interp-training：n26/52/57（3 音 × 3 力度 × 2 rate × 2 reps = 36 单元）
        "notes": {26: 36.7081, 52: 164.8138, 57: 220.0},
        "sessions": [
            ("s01-n26-44100-rep0", 26, 44100, 0), ("s02-n26-44100-rep1", 26, 44100, 1),
            ("s03-n26-48000-rep0", 26, 48000, 0), ("s04-n26-48000-rep1", 26, 48000, 1),
            ("s05-n52-44100-rep0", 52, 44100, 0), ("s06-n52-44100-rep1", 52, 44100, 1),
            ("s07-n52-48000-rep0", 52, 48000, 0), ("s08-n52-48000-rep1", 52, 48000, 1),
            ("s09-n57-44100-rep0", 57, 44100, 0), ("s10-n57-44100-rep1", 57, 44100, 1),
            ("s11-n57-48000-rep0", 57, 48000, 0), ("s12-n57-48000-rep1", 57, 48000, 1),
        ],
    },
    "interpval": {  # P3 interp 验证集：n25/27/53/59（4 音 × 3 力度(47/79/107) × 2 rate × 2 reps = 48 单元）
        "notes": {25: 34.6478, 27: 38.8909, 53: 174.6141, 59: 246.9417},
        "velocities": [47, 79, 107],  # 更正：preset 声明的力度此前回落到全局默认 [41,70,98]
        "sessions": [
            ("s01-n25-44100-rep0", 25, 44100, 0), ("s02-n25-44100-rep1", 25, 44100, 1),
            ("s03-n25-48000-rep0", 25, 48000, 0), ("s04-n25-48000-rep1", 25, 48000, 1),
            ("s05-n27-44100-rep0", 27, 44100, 0), ("s06-n27-44100-rep1", 27, 44100, 1),
            ("s07-n27-48000-rep0", 27, 48000, 0), ("s08-n27-48000-rep1", 27, 48000, 1),
            ("s09-n53-44100-rep0", 53, 44100, 0), ("s10-n53-44100-rep1", 53, 44100, 1),
            ("s11-n53-48000-rep0", 53, 48000, 0), ("s12-n53-48000-rep1", 53, 48000, 1),
            ("s13-n59-44100-rep0", 59, 44100, 0), ("s14-n59-44100-rep1", 59, 44100, 1),
            ("s15-n59-48000-rep0", 59, 48000, 0), ("s16-n59-48000-rep1", 59, 48000, 1),
        ],
    },
    "interpval2": {  # P3 后继验证集：n29/55/67/88（F1/G3/G4/E6；全部首次使用音高；4 音 × 3 力度 × 2 rate × 2 reps = 48 单元）
        "notes": {29: 43.6536, 55: 195.9977, 67: 391.9954, 88: 1318.5102},
        "velocities": [47, 79, 107],
        "sessions": [
            ("s01-n29-44100-rep0", 29, 44100, 0), ("s02-n29-44100-rep1", 29, 44100, 1),
            ("s03-n29-48000-rep0", 29, 48000, 0), ("s04-n29-48000-rep1", 29, 48000, 1),
            ("s05-n55-44100-rep0", 55, 44100, 0), ("s06-n55-44100-rep1", 55, 44100, 1),
            ("s07-n55-48000-rep0", 55, 48000, 0), ("s08-n55-48000-rep1", 55, 48000, 1),
            ("s09-n67-44100-rep0", 67, 44100, 0), ("s10-n67-44100-rep1", 67, 44100, 1),
            ("s11-n67-48000-rep0", 67, 48000, 0), ("s12-n67-48000-rep1", 67, 48000, 1),
            ("s13-n88-44100-rep0", 88, 44100, 0), ("s14-n88-44100-rep1", 88, 44100, 1),
            ("s15-n88-48000-rep0", 88, 48000, 0), ("s16-n88-48000-rep1", 88, 48000, 1),
        ],
    },
}
NOTES = PRESETS["pilot"]["notes"]
SESSIONS = PRESETS["pilot"]["sessions"]

WINDOWS = {"W1": (0.08, 3.8), "W2": (0.5, 4.1)}
LOW_FREQ = 40.0  # 默认候选低限；低音按 theory/2 下调，不能预先截断有效基频
MAX_FREQ = 20000.0  # 搜索上限不增加输入 WAV 的实际带宽
SEED_STIFFNESS = 1e-4
DEFAULT_SEEDS = (3e-5, 5e-5, 8e-5, 1.2e-4, 2e-4)
EXTENDED_SEEDS = DEFAULT_SEEDS + (4e-4, 8e-4, 1.6e-3, 3e-3, 7e-3, 1.5e-2, 3e-2)
SEEDS = DEFAULT_SEEDS  # analyze_unit 按音符选择 DEFAULT/EXTENDED
SNR_ADMISSION_DB = 25.0  # 高音区正式方法：局部 SNR 准入阈值（dB）；None = 关闭（同口径复现）
SNR_MIN_NOTE = 72  # 启用 SNR 通道与扩展种子的最低 MIDI 音符（高音区）
STAGE_A_TOL, STAGE_A_REL = 0.015, 1e-5
STAGE_B_TOL, STAGE_B_REL = 0.007, 1e-6
NEAREST_REL = 1e-7  # nearest 精化轮专用阈值：容许被附加强峰遮蔽的弱真分音（如 C2-v98 n=72 的 -65 dB 真峰）
REFINEMENT_GUARD_DB = 20.0  # 方法修订 5：nearest 精化轮候选强度守卫（候选低于窗内最强该 dB 数则排除；None = 关闭守卫）
EXPANSION_LEVELS = (10, 16, 24, 32, 40, 48, 60, 80, 120, 160, 220, 300)

COORDINATE_FILE_ABSOLUTE = "file_absolute"  # 旧批消费数据诊断：窗从文件第 0 样本起算的绝对秒窗
COORDINATE_NOTE_ON_RELATIVE = "note_on_relative"  # v3：窗从显式 NoteOn 样本起算
ROLE_SYNTHETIC_FIXTURE = "synthetic_fixture"  # 合成夹具（qualification 合成用例也用这套坐标）
ROLE_DEV_RENDER_VERIFICATION = "dev_render_verification"  # A4 dev render 报告，只能由 load_timing_report 登记
ROLE_REFERENCE_ORIGIN_AUTHENTICATED = "reference_origin_authenticated"  # A5 证书 + 实际 MIDI 事件逐单元报告
REFERENCE_TIMING_SCHEMA = "devpiano-task39-2-reference-origin-timing-v1"
REFERENCE_ORIGIN_CERTIFICATE_SCHEMA = "devpiano-task39-2-a5-origin-certificate-v1"
KNOWN_EVIDENCE_ROLES = (ROLE_SYNTHETIC_FIXTURE, ROLE_DEV_RENDER_VERIFICATION,
                        ROLE_REFERENCE_ORIGIN_AUTHENTICATED)
SUPPORTED_EVIDENCE_ROLES = (ROLE_SYNTHETIC_FIXTURE, ROLE_DEV_RENDER_VERIFICATION,
                            ROLE_REFERENCE_ORIGIN_AUTHENTICATED)
DEV_RENDER_REPORT_ROLE = "input_and_dev_render_contract_only"  # A4 independent-verification.json 的 role
CONSUMED_DATA_ROLE = "consumed_data_diagnostic"  # 批处理 CLI 的角色标签（非 v3 相对坐标）
ONSET_DIAGNOSTIC_S = 0.05  # 仅记录能量诊断（非门禁、不用于估计或认证原点）
RELEASE_DIAGNOSTIC_S = 0.02  # 仅记录能量诊断（非门禁、不用于估计或认证原点）


class MatchFailure(ValueError):
    """失败保留阶段轨迹，便于区分缺少分音与数值求解失败。"""

    def __init__(self, message, trace):
        super().__init__(message)
        self.trace = trace


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


def llround(value):
    """C llround 口径的秒->样本换算（半远离零）；不做首非零/相关推断。"""
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("non-finite seconds-to-samples conversion")
    return int(math.floor(value + 0.5)) if value >= 0 else int(math.ceil(value - 0.5))


def integral_sample_index(value):
    """样本下标必须是整数值：拦截 float 截断，接受 int/numpy 整数（半开端点语义不变）。"""
    if isinstance(value, bool):
        raise ValueError("sample index must be an integer value, not a bool")
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    raise ValueError(f"sample index must be an integer value, got {value!r}")


def note_on_relative_bounds(relative_seconds_window, note_on_sample, rate):
    """NoteOn 相对秒窗 -> 半开绝对样本界 [start, stop)（llround，半远离零）。"""
    if len(relative_seconds_window) != 2:
        raise ValueError("window must be a (start, stop) second pair")
    if rate <= 0:
        raise ValueError("sample rate must be positive")
    origin = integral_sample_index(note_on_sample)
    return tuple(origin + llround(value * rate) for value in relative_seconds_window)


def validate_timing(timing, rate, frames, note):
    """校验显式时间轴并返回副本；无默认原点、无隐式坐标、无推断。

    - file_absolute：旧批消费数据诊断域，只要求坐标，不得携带 NoteOn 原点字段；
    - note_on_relative：要求 sample_rate/frames/note_on_sample/note_off_sample/evidence_role，
      且时间轴必须与传入声道一致；reference_origin_authenticated 还要求证书绑定的
      wav_sha256/certificate_sha256 与 reference_origin_certified=true。
    """
    if not isinstance(timing, dict):
        raise ValueError("explicit timing is required (no default origin): pass a timing dict")
    coordinate = timing.get("coordinate")
    if coordinate not in (COORDINATE_FILE_ABSOLUTE, COORDINATE_NOTE_ON_RELATIVE):
        raise ValueError(f"timing.coordinate must be '{COORDINATE_FILE_ABSOLUTE}' or "
                         f"'{COORDINATE_NOTE_ON_RELATIVE}', got {coordinate!r}")
    if timing.get("sample_rate") is not None and int(timing["sample_rate"]) != int(rate):
        raise ValueError(f"timing.sample_rate {timing['sample_rate']} does not match rate {rate}")
    if timing.get("frames") is not None and int(timing["frames"]) != int(frames):
        raise ValueError(f"timing.frames {timing['frames']} does not match channel frames {frames}")
    role = timing.get("evidence_role")
    if role is not None:
        if role not in KNOWN_EVIDENCE_ROLES:
            raise ValueError(f"unknown timing.evidence_role {role!r}")
        if role not in SUPPORTED_EVIDENCE_ROLES:
            raise ValueError("reference-origin timing needs an approved reference evidence contract; "
                             "dev render reports cannot be relabelled as reference authentication")
    if timing.get("note") is not None and int(timing["note"]) != int(note):
        raise ValueError(f"timing.note {timing['note']} does not match requested note {note}")
    if coordinate == COORDINATE_FILE_ABSOLUTE:
        if "note_on_sample" in timing or "note_off_sample" in timing:
            raise ValueError("file_absolute timing must not carry a NoteOn origin")
        return dict(timing)
    if role is None:
        raise ValueError("note_on_relative timing requires evidence_role")
    if timing.get("sample_rate") is None or timing.get("frames") is None:
        raise ValueError("note_on_relative timing requires sample_rate and frames")
    for key in ("note_on_sample", "note_off_sample"):
        if timing.get(key) is None:
            raise ValueError(f"note_on_relative timing requires {key}")
    note_on = integral_sample_index(timing["note_on_sample"])
    note_off = integral_sample_index(timing["note_off_sample"])
    if not 0 <= note_on < note_off <= int(frames):
        raise ValueError(f"invalid NoteOn timeline: need 0 <= {note_on} < {note_off} <= {frames}")
    if role == ROLE_DEV_RENDER_VERIFICATION and not timing.get("wav_sha256"):
        raise ValueError("dev_render_verification timing requires the bound wav_sha256 identity")
    if role == ROLE_REFERENCE_ORIGIN_AUTHENTICATED:
        if not timing.get("wav_sha256"):
            raise ValueError("reference_origin_authenticated timing requires the bound wav_sha256 identity")
        if not timing.get("certificate_sha256"):
            raise ValueError("reference_origin_authenticated timing requires certificate_sha256")
        if timing.get("reference_origin_certified") is not True:
            raise ValueError("reference_origin_authenticated timing requires reference_origin_certified=true")
    return dict(timing)


def window_sample_bounds(window, timing, rate):
    """按坐标解析窗口样本界；file_absolute 返回 None（沿用历史 int() 截断口径）。"""
    if timing["coordinate"] == COORDINATE_FILE_ABSOLUTE:
        return None
    return note_on_relative_bounds(window, timing["note_on_sample"], rate)


def _smf_vlq(data, offset):
    """读取 SMF 可变长度量，返回 (value, next_offset)。"""
    value = 0
    for _ in range(4):
        if offset >= len(data):
            raise ValueError("truncated MIDI variable-length quantity")
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, offset
    raise ValueError("MIDI variable-length quantity exceeds four bytes")


def parse_smf_note_timeline(midi_path, note, velocity=None):
    """解析标准 MIDI 文件，返回指定 note 的唯一 NoteOn/NoteOff 事件及秒坐标。

    只接受 format 0/1 的 PPQ 计时；拒绝 SMPTE、缺失事件或同 note 多个候选。
    tempo map 按 meta 0x51 分段，缺省 500000 us/quarter。该函数只做 MIDI 时间线解析，
    不推断音频起点、不做首非零/相关对齐。
    """
    midi_path = Path(midi_path)
    raw = midi_path.read_bytes()
    if len(raw) < 14 or raw[:4] != b"MThd":
        raise ValueError("not a standard MIDI file: missing MThd")
    header_length = int.from_bytes(raw[4:8], "big")
    if header_length < 6 or 8 + header_length > len(raw):
        raise ValueError("invalid MIDI header length")
    fmt = int.from_bytes(raw[8:10], "big")
    track_count = int.from_bytes(raw[10:12], "big")
    division = int.from_bytes(raw[12:14], "big")
    if fmt not in (0, 1):
        raise ValueError(f"unsupported MIDI format {fmt}")
    if division & 0x8000 or division == 0:
        raise ValueError("SMPTE or zero MIDI division is unsupported")
    ppq = division
    offset = 8 + header_length
    tempo_events, note_events = [], []
    for _ in range(track_count):
        if offset + 8 > len(raw) or raw[offset:offset + 4] != b"MTrk":
            raise ValueError("invalid MIDI track header")
        length = int.from_bytes(raw[offset + 4:offset + 8], "big")
        track = raw[offset + 8:offset + 8 + length]
        if len(track) != length:
            raise ValueError("truncated MIDI track")
        offset += 8 + length
        tick, index, running = 0, 0, None
        while index < len(track):
            delta, index = _smf_vlq(track, index)
            tick += delta
            if index >= len(track):
                raise ValueError("truncated MIDI event")
            status = track[index]
            if status < 0x80:
                if running is None:
                    raise ValueError("MIDI running status without a channel status")
                status = running
            else:
                index += 1
                if status < 0xF0:
                    running = status
            if status == 0xFF:
                if index >= len(track):
                    raise ValueError("truncated MIDI meta event")
                meta = track[index]
                index += 1
                size, index = _smf_vlq(track, index)
                payload = track[index:index + size]
                if len(payload) != size:
                    raise ValueError("truncated MIDI meta payload")
                index += size
                if meta == 0x51 and size == 3:
                    tempo_events.append((tick, int.from_bytes(payload, "big")))
                elif meta == 0x2F:
                    break
            elif status in (0xF0, 0xF7):
                size, index = _smf_vlq(track, index)
                index += size
            else:
                kind = status & 0xF0
                if kind in (0xC0, 0xD0):
                    index += 1
                else:
                    if index + 2 > len(track):
                        raise ValueError("truncated MIDI channel event")
                    data1, data2 = track[index], track[index + 1]
                    index += 2
                    if kind == 0x90 and data2 > 0:
                        note_events.append({"tick": tick, "kind": "note_on",
                                            "note": data1, "velocity": data2})
                    elif kind == 0x80 or (kind == 0x90 and data2 == 0):
                        note_events.append({"tick": tick, "kind": "note_off",
                                            "note": data1, "velocity": 0})
    if not tempo_events:
        tempo_events = [(0, 500000)]
    tempo_events.sort()
    deduped = []
    for event in tempo_events:
        if deduped and deduped[-1][0] == event[0]:
            deduped[-1] = event
        else:
            deduped.append(event)
    tempo_events = deduped

    def seconds_at(target):
        seconds, last_tick, current = 0.0, 0, 500000
        for event_tick, event_tempo in tempo_events:
            if event_tick > target:
                break
            seconds += (event_tick - last_tick) * current / (ppq * 1_000_000.0)
            last_tick, current = event_tick, event_tempo
        seconds += (target - last_tick) * current / (ppq * 1_000_000.0)
        return seconds

    onsets = [event for event in note_events
              if event["kind"] == "note_on" and (note is None or event["note"] == note)
              and (velocity is None or event["velocity"] == velocity)]
    if len(onsets) != 1:
        raise ValueError(f"MIDI must contain exactly one matching NoteOn for note {note}: found {len(onsets)}")
    onset = onsets[0]
    note = int(onset["note"])
    releases = [event for event in note_events
                if event["kind"] == "note_off" and event["note"] == note
                and event["tick"] > onset["tick"]]
    if not releases:
        raise ValueError(f"MIDI has no NoteOff after NoteOn for note {note}")
    release = min(releases, key=lambda event: event["tick"])
    return {
        "midi_sha256": sha256(midi_path),
        "ppq": ppq,
        "tempo_us": tempo_events[0][1],
        "note": int(note),
        "velocity": int(onset["velocity"]),
        "note_on_tick": int(onset["tick"]),
        "note_off_tick": int(release["tick"]),
        "note_on_seconds": seconds_at(onset["tick"]),
        "note_off_seconds": seconds_at(release["tick"]),
    }


def load_reference_origin_timing(report_path, wav_path, report=None):
    """载入 A5 参考原点逐单元 timing 报告。

    报告必须绑定已认证证书（SHA-256）、实际 MIDI（SHA-256 + NoteOn/NoteOff tick/秒）、
    实际 WAV（SHA-256 + rate/frames/channels/bits）。NoteOn/NoteOff 样本由证书的
    midi_origin_sample + llround(秒*rate) 唯一计算，不接受报告自报值或音频对齐推断。
    参考 WAV 允许起点前非零（诊断 WAV 即有 dither）；能量只作非门禁诊断。
    """
    report_path, wav_path = Path(report_path), Path(wav_path)
    if report is None:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("schema") != REFERENCE_TIMING_SCHEMA:
        raise ValueError(f"unsupported reference timing schema {report.get('schema')!r}")
    if report.get("role") != ROLE_REFERENCE_ORIGIN_AUTHENTICATED:
        raise ValueError(f"reference timing report role must be {ROLE_REFERENCE_ORIGIN_AUTHENTICATED!r}")
    if report.get("passed") is not True or report.get("failures") != []:
        raise ValueError("reference timing report did not pass or records failures")
    if report.get("reference_origin_certified") is not True:
        raise ValueError("reference timing report must declare reference_origin_certified=true")

    certificate_ref = report.get("certificate") or {}
    certificate_path = Path(str(certificate_ref.get("path", "")))
    if not certificate_path.is_absolute():
        certificate_path = report_path.parent / certificate_path
    if not certificate_path.is_file():
        raise ValueError("reference timing report certificate is missing")
    if certificate_ref.get("sha256") != sha256(certificate_path):
        raise ValueError("reference timing report certificate_sha256 does not match")
    certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
    if certificate.get("schema") != REFERENCE_ORIGIN_CERTIFICATE_SCHEMA:
        raise ValueError("unsupported reference origin certificate schema")
    if certificate.get("status") != "authenticated":
        raise ValueError("reference origin certificate is not authenticated")
    origin = certificate.get("midi_origin_sample")
    if not isinstance(origin, int) or isinstance(origin, bool):
        raise ValueError("reference origin certificate has no integer midi_origin_sample")

    midi_ref = report.get("midi") or {}
    midi_path = Path(str(midi_ref.get("path", "")))
    if not midi_path.is_absolute():
        midi_path = report_path.parent / midi_path
    if not midi_path.is_file():
        raise ValueError("reference timing report MIDI is missing")
    if midi_ref.get("sha256") != sha256(midi_path):
        raise ValueError("reference timing report midi_sha256 does not match")
    note = midi_ref.get("note")
    velocity = midi_ref.get("velocity")
    if not isinstance(note, int) or isinstance(note, bool):
        raise ValueError("reference timing report has no MIDI note identity")
    timeline = parse_smf_note_timeline(midi_path, note, velocity)
    for key in ("ppq", "note_on_tick", "note_off_tick"):
        if int(midi_ref.get(key, -1)) != timeline[key]:
            raise ValueError(f"reference timing report {key} does not match the MIDI file")
    for key in ("note_on_seconds", "note_off_seconds"):
        try:
            declared = float(midi_ref[key])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"reference timing report missing numeric {key}")
        if not math.isfinite(declared) or not math.isclose(declared, timeline[key], rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"reference timing report {key} does not match the MIDI file")

    rate, frames, left, right = read_wav_stereo(wav_path)
    with wave.open(str(wav_path), "rb") as handle:
        channels, bits = handle.getnchannels(), handle.getsampwidth() * 8
    declared_wav = report.get("wav") or {}
    if (int(declared_wav.get("rate", -1)) != rate
            or int(declared_wav.get("frames", -1)) != frames
            or int(declared_wav.get("channels", -1)) != channels
            or int(declared_wav.get("bits", -1)) != bits):
        raise ValueError("reference timing report WAV metadata does not match the analyzed WAV")
    if report.get("wav_sha256") != sha256(wav_path):
        raise ValueError("reference timing report wav_sha256 does not match the analyzed WAV bytes")

    note_on_sample = origin + llround(timeline["note_on_seconds"] * rate)
    note_off_sample = origin + llround(timeline["note_off_seconds"] * rate)
    if int(report.get("note_on_sample", -1)) != note_on_sample:
        raise ValueError("reference timing report note_on_sample does not match the certificate formula")
    if int(report.get("note_off_sample", -1)) != note_off_sample:
        raise ValueError("reference timing report note_off_sample does not match the certificate formula")
    if not 0 <= note_on_sample < note_off_sample <= frames:
        raise ValueError("reference timing report has an invalid NoteOn/NoteOff timeline")

    reported = report.get("windows") or {}
    verified_windows = {}
    for name, window in WINDOWS.items():
        start, stop = note_on_relative_bounds(window, note_on_sample, rate)
        entry = reported.get(name) or {}
        if int(entry.get("start_sample", -1)) != start or int(entry.get("stop_sample", -1)) != stop:
            raise ValueError(f"reported {name} window {entry!r} is inconsistent with the certificate grid "
                             f"[{start}, {stop})")
        verified_windows[name] = {"start_sample": start, "stop_sample": stop}

    onset_stop = min(frames, note_on_sample + max(1, llround(ONSET_DIAGNOSTIC_S * rate)))
    energy_diagnostics = {
        "pre_onset_nonzero_samples": int(np.count_nonzero(left[:note_on_sample])
                                         + np.count_nonzero(right[:note_on_sample])),
        "onset_nonzero_samples": int(np.count_nonzero(left[note_on_sample:onset_stop])
                                     + np.count_nonzero(right[note_on_sample:onset_stop])),
        "onset_window_s": [note_on_sample / rate, onset_stop / rate],
        "gating": False,
        "note": "非门禁能量观测；参考导出允许起点前 dither，不用首非零或相关对齐认证原点",
    }
    return {
        "coordinate": COORDINATE_NOTE_ON_RELATIVE,
        "sample_rate": rate,
        "frames": frames,
        "note": int(note),
        "velocity": timeline["velocity"],
        "note_on_sample": note_on_sample,
        "note_off_sample": note_off_sample,
        "evidence_role": ROLE_REFERENCE_ORIGIN_AUTHENTICATED,
        "wav_sha256": report["wav_sha256"],
        "certificate_sha256": certificate_ref["sha256"],
        "certificate_path": str(certificate_path),
        "midi_sha256": timeline["midi_sha256"],
        "midi_path": str(midi_path),
        "report_sha256": sha256(report_path),
        "report_path": str(report_path),
        "report_role": report["role"],
        "reference_origin_certified": True,
        "midi_origin_sample": origin,
        "timeline_check": "certificate_origin_midi_identity_formula_and_wav_hash",
        "energy_diagnostics": energy_diagnostics,
        "reported_windows": verified_windows,
    }


def load_timing_report(report_path, wav_path):
    """载入 A4 独立核验报告作为 NoteOn 相对时间轴（只登记 dev render 契约证据）。

    只接受 role=input_and_dev_render_contract_only、passed=true、failures 空、且
    reference_origin_certified/static_B_qualified/formal_evaluation 显式 false 的报告；
    独立复核 WAV 字节散列与 rate/frames/channels/bits、报告声明的 note_on/note_off 事件时刻在帧内、
    A4 契约的 note_on 前逐样本静音、以及报告 windows 是否等于 note_on+llround(相对秒*rate)。
    起音/释放附近的能量只作为非门禁诊断记录，不用于估计或认证原点。
    产出 evidence_role=dev_render_verification；绝不升级为参考原点认证。
    """
    report_path, wav_path = Path(report_path), Path(wav_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("role") == ROLE_REFERENCE_ORIGIN_AUTHENTICATED:
        return load_reference_origin_timing(report_path, wav_path, report=report)
    if report.get("role") != DEV_RENDER_REPORT_ROLE:
        raise ValueError(f"unsupported timing report role {report.get('role')!r}: only "
                         f"'{DEV_RENDER_REPORT_ROLE}' and '{ROLE_REFERENCE_ORIGIN_AUTHENTICATED}' "
                         f"are accepted")
    if report.get("passed") is not True:
        raise ValueError("timing report did not pass its own independent verification")
    if report.get("failures") != []:
        raise ValueError("timing report records failures")
    for flag in ("reference_origin_certified", "static_B_qualified", "formal_evaluation"):
        if report.get(flag) is not False:
            raise ValueError(f"timing report must declare {flag}=false: it is not reference-origin evidence")
    midi = report.get("midi") or {}
    note = midi.get("note")
    if not isinstance(note, int) or isinstance(note, bool):
        raise ValueError("timing report has no MIDI note identity")
    rate, frames, left, right = read_wav_stereo(wav_path)
    declared = report.get("wav") or {}
    if (int(declared.get("rate", -1)) != rate or int(declared.get("frames", -1)) != frames
            or int(declared.get("channels", -1)) != 2 or int(declared.get("bits", -1)) != 24):
        raise ValueError("timing report WAV metadata does not match the analyzed WAV")
    if report.get("wav_sha256") != sha256(wav_path):
        raise ValueError("timing report wav_sha256 does not match the analyzed WAV bytes")
    instants = []
    for key in ("note_on_sample", "note_off_sample"):
        value = report.get(key)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"timing report lacks an integer {key} event instant")
        instants.append(value)
    note_on, note_off = instants
    if not 0 <= note_on < note_off <= frames:
        raise ValueError(f"invalid report timeline: need 0 <= {note_on} < {note_off} <= {frames}")
    if np.any(left[:note_on] != 0.0) or np.any(right[:note_on] != 0.0):
        raise ValueError("WAV has content before the declared note_on_sample")
    onset_stop = min(frames, note_on + max(1, llround(ONSET_DIAGNOSTIC_S * rate)))
    release_start = max(0, note_off - max(1, llround(RELEASE_DIAGNOSTIC_S * rate)))
    energy_diagnostics = {
        "onset_nonzero_samples": int(np.count_nonzero(left[note_on:onset_stop])
                                     + np.count_nonzero(right[note_on:onset_stop])),
        "pre_release_nonzero_samples": int(np.count_nonzero(left[release_start:note_off])
                                           + np.count_nonzero(right[release_start:note_off])),
        "onset_window_s": [note_on / rate, onset_stop / rate],
        "pre_release_window_s": [release_start / rate, note_off / rate],
        "gating": False,
        "note": "非门禁能量观测：不构成准入门禁，不用于估计或认证原点"}
    reported, verified_windows = report.get("windows") or {}, {}
    for name, window in WINDOWS.items():
        start, stop = note_on_relative_bounds(window, note_on, rate)
        entry = reported.get(name) or {}
        if int(entry.get("start_sample", -1)) != start or int(entry.get("stop_sample", -1)) != stop:
            raise ValueError(f"reported {name} window {entry!r} is inconsistent with the NoteOn grid "
                             f"[{start}, {stop})")
        verified_windows[name] = {"start_sample": start, "stop_sample": stop}
    return {"coordinate": COORDINATE_NOTE_ON_RELATIVE, "sample_rate": rate, "frames": frames,
            "note": int(note), "velocity": midi.get("velocity"),
            "note_on_sample": note_on, "note_off_sample": note_off,
            "evidence_role": ROLE_DEV_RENDER_VERIFICATION,
            "wav_sha256": report["wav_sha256"], "report_sha256": sha256(report_path),
            "report_path": str(report_path), "report_role": report["role"],
            "reference_origin_certified": False,
            "timeline_check": "wav_sha256_rate_frames_pre_onset_silence_and_reported_window_grid",
            "energy_diagnostics": energy_diagnostics,
            "reported_windows": verified_windows}


def power_spectrum(left, right, rate, window, *, sample_bounds=None):
    if sample_bounds is None:
        start = int(window[0] * rate)
        stop = int(window[1] * rate)
    else:
        start, stop = int(sample_bounds[0]), int(sample_bounds[1])
    if rate <= 0 or start < 0 or stop <= start or stop > min(len(left), len(right)):
        raise ValueError("analysis window exceeds available samples or has invalid bounds")
    hann = np.hanning(stop - start)
    spectrum_l = np.fft.rfft(left[start:stop] * hann)
    spectrum_r = np.fft.rfft(right[start:stop] * hann)
    power = spectrum_l.real ** 2 + spectrum_l.imag ** 2 + spectrum_r.real ** 2 + spectrum_r.imag ** 2
    return np.fft.rfftfreq(stop - start, 1.0 / rate), power


def spectral_peaks(frequency, power, low, high):
    """返回 (峰频率, 相对功率, 局部SNR dB) 数组；相对功率 = power / max(power)。

    局部 SNR：以峰为中心 ±3% 带内功率中位数（排除峰 ±0.2% 自身）作为噪声地板。
    """
    maximum = float(np.max(power)) if len(power) else 0.0
    if not np.isfinite(maximum) or maximum <= 0:
        raise ValueError("spectrum has no finite positive power")
    relative = power / maximum
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
                   maximum=400, mode="strongest", min_snr=None, guard_db=None):
    """按模型预测位置匹配峰；mode=strongest 取窗内最强，mode=nearest 取最靠近预测。

    峰值准入：rel >= min_rel；若给定 min_snr，则追加“rel >= 1e-9 且局部 SNR >= min_snr”通道
    （用于动态范围大的高音区，真分音相对基频低但局部 SNR 很高）。
    guard_db（仅 nearest 模式，方法修订 5）：候选强度守卫——容差窗内相对功率低于最强候选
    该 dB 数的峰被排除，防止泄漏/噪声伪峰（如 -65 dB）在距离略近时抢占真分音。
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
                if guard_db is not None:
                    ceiling = float(np.max(rel[inside]))
                    admitted = inside[rel[inside] >= ceiling * 10.0 ** (-guard_db / 10.0)]
                    best = admitted[np.argmin(np.abs(peaks[admitted] - prediction))]
                else:
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


def staged_match(peaks, rel, snr, theory, seed_stiffness=SEED_STIFFNESS, min_snr=None, trace=None):
    """从第 1--6 分音起步，再按拟合结果逐级扩展。"""
    trace = [] if trace is None else trace
    first, stiffness = theory, seed_stiffness
    stage = {"stage": "stage-A", "maximum": 6}
    trace.append(stage)
    try:
        numbers, observed = match_partials(
            peaks, rel, snr, first, stiffness, STAGE_A_TOL, STAGE_A_REL,
            maximum=6, min_snr=min_snr)
        stage["identified_partials"] = int(len(numbers))
        if len(numbers) < 3:
            raise ValueError(f"stage-A insufficient partials: {len(numbers)}")
        solution = fit(observed, numbers, first, stiffness)
        first, stiffness = float(solution.x[0]), float(solution.x[1])
        stage.update({"status": "ok", "f1_Hz": first, "effective_B": stiffness})
        for level in EXPANSION_LEVELS:
            stage = {"stage": "expansion", "maximum": int(level)}
            trace.append(stage)
            expanded_numbers, expanded_observed = match_partials(
                peaks, rel, snr, first, stiffness, STAGE_A_TOL, STAGE_A_REL,
                maximum=level, min_snr=min_snr)
            stage["identified_partials"] = int(len(expanded_numbers))
            if len(expanded_numbers) > len(numbers):
                solution = fit(expanded_observed, expanded_numbers, first, stiffness)
                first, stiffness = float(solution.x[0]), float(solution.x[1])
                numbers, observed = expanded_numbers, expanded_observed
                stage.update({"status": "accepted", "f1_Hz": first, "effective_B": stiffness})
            else:
                stage["status"] = "no-expansion"
        stage = {"stage": "stage-B", "maximum": 400}
        trace.append(stage)
        numbers, observed = match_partials(
            peaks, rel, snr, first, stiffness, STAGE_B_TOL, STAGE_B_REL, min_snr=min_snr)
        stage["identified_partials"] = int(len(numbers))
        if len(numbers) < 5:
            raise ValueError(f"insufficient identified partials after staged match: {len(numbers)}")
        solution = fit(observed, numbers, first, stiffness)
        stage.update({"status": "ok", "f1_Hz": float(solution.x[0]),
                      "effective_B": float(solution.x[1])})
        return float(solution.x[0]), float(solution.x[1]), numbers, observed
    except (ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
        stage.update({"status": "failed", "error": str(error)})
        raise MatchFailure(str(error), trace) from error


def staged_match_multi(peaks, rel, snr, theory, seeds=SEEDS, min_snr=None, trace=None):
    """按残差与分音数量择优，保留所有种子的阶段记录。"""
    attempts = []
    best = None
    best_key = None
    for seed in seeds:
        seed_trace = []
        try:
            first, stiffness, numbers, observed = staged_match(
                peaks, rel, snr, theory, seed, min_snr=min_snr, trace=seed_trace)
        except (ValueError, FloatingPointError, np.linalg.LinAlgError) as error:
            attempts.append({"seed_stiffness": float(seed), "status": "failed",
                             "error": str(error), "stages": seed_trace})
            continue
        residual = 1200 * np.log2(observed / partial_prediction([first, stiffness], numbers))
        max_residual = float(np.max(np.abs(residual)))
        key = (max_residual > 3.0, -len(numbers), max_residual)
        attempts.append({"seed_stiffness": float(seed), "status": "ok",
                         "identified_partials": int(len(numbers)),
                         "max_residual_cents": max_residual, "stages": seed_trace})
        if best_key is None or key < best_key:
            best, best_key = (first, stiffness, numbers, observed), key
    if trace is not None:
        trace.extend(attempts)
    if best is None:
        raise MatchFailure("no staged match converged from any stiffness seed", attempts)
    return best


HOLDOUT_TOLERANCE_CENTS = 50.0  # 上限；低音区相邻分音间隔远大于此
HOLDOUT_NEIGHBOUR_FRACTION = 0.45  # 窗口不得超过相邻分音间隔的此比例（amendment-2）
HOLDOUT_REL_FLOOR = 1e-7


def holdout_window_cents(number):
    """独立识别窗口：min(50 cents, 0.45 x 相邻分音间隔)，避免跨入相邻分音。"""
    neighbour_interval = 1200.0 * math.log2((number + 1.0) / float(number))
    return min(HOLDOUT_TOLERANCE_CENTS, HOLDOUT_NEIGHBOUR_FRACTION * neighbour_interval)


def independent_split_prediction(peaks, rel, snr, theory, numbers, observed, seeds, min_snr, observe):
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
            candidate = float(peaks[window[np.argmax(rel[window])]])
            observation = observe(candidate)
            picked = observation["frequency_hz"] if observation["status"] == "single_component_adequate" else None
            error = float(1200.0 * np.log2(picked / predicted)) if picked is not None else None
            if error is not None:
                errors.append(error)
            details.append({"number": number, "predicted_Hz": predicted,
                            "raw_candidate_Hz": candidate, "reidentified_Hz": picked,
                            "error_cents": error, "observation": observation})
        else:
            details.append({"number": number, "predicted_Hz": predicted,
                            "reidentified_Hz": None, "error_cents": None})
    if not errors:
        return {"status": "no_holdout_peak_reidentified", "holdout_size": len(holdout_indices),
                "train_f1_Hz": train_first, "train_effective_B": train_stiffness, "details": details}
    return {"status": "ok" if len(errors) == len(holdout_indices) else "incomplete_observed_holdout",
            "holdout_size": len(holdout_indices),
            "training_size": int(keep_indices.size),
            "train_f1_Hz": train_first,
            "train_effective_B": train_stiffness,
            "max_cents": float(np.max(np.abs(errors))),
            "rms_cents": float(np.sqrt(np.mean(np.square(errors)))),
            "details": details}


def _exact_seconds_bound(sample, rate):
    """把单个整数样本下标映射为秒值 x，使 int(x*rate) 精确还原该下标（nextafter 微调）。"""
    candidate = float(sample) / rate
    for _ in range(8):
        converted = int(candidate * rate)
        if converted == sample:
            return candidate
        candidate = math.nextafter(candidate, math.inf if converted < sample else -math.inf)
    raise ValueError(f"cannot express sample {sample} at {rate} Hz as exact seconds")


def exact_seconds_window(start_sample, stop_sample, rate):
    """整数样本界 -> 文件绝对秒窗（供受保护观测器使用；int(x*rate) 精确还原端点）。

    观测器只接收秒窗并自行 int(window*rate) 切片，直接给 sample/rate 可能因浮点误差少取
    一个样本（如 4.1*44100 = 180809.99999999997 -> int 180809），故按需微调。
    """
    if rate <= 0:
        raise ValueError("sample rate must be positive")
    return (_exact_seconds_bound(int(start_sample), rate), _exact_seconds_bound(int(stop_sample), rate))


def observation_blocks_family(observation):
    """明确的结构证据阻断整族；普通低信息弃权不等于混合认证。"""
    if observation.get("status") == "resolved_components":
        return True
    reasons = observation.get("reasons") or ()
    return observation.get("status") == "ambiguous" and (
        "coherent_structure_outside_component_search_bounds" in reasons
        or "multiple_component_alternative_unresolved" in reasons)


def analyze_window(left, right, rate, window, theory, seeds, min_snr, *, sample_bounds=None, timing=None):
    """窗口失败只影响该窗口，保留已完成阶段和原始错误。

    - sample_bounds=None：历史绝对秒窗沿用 int() 截断与浮点窗长，不追认为 NoteOn 相对证据；
    - sample_bounds=(start, stop)：调用方按 llround 网格解析的半开整数样本界；频谱直接用整数端点，
      观测器（受保护模块，接口只收秒窗）改收 exact_seconds_window 生成的等价秒窗，逐样本一致；
    - timing 仅登记坐标/证据角色并执行释放边界（半开）校验，不进入拟合、匹配或阈值。
    """
    coordinate = timing["coordinate"] if timing else COORDINATE_FILE_ABSOLUTE
    evidence_role = timing.get("evidence_role") if timing else None
    if sample_bounds is None:
        start, stop = int(window[0] * rate), int(window[1] * rate)
        duration = float(window[1]) - float(window[0])
    else:
        start, stop = int(sample_bounds[0]), int(sample_bounds[1])
        duration = (stop - start) / rate if stop > start and rate > 0 else 0.0
    result = {"status": "failed", "bounds_s": list(window), "coordinate": coordinate,
              "evidence_role": evidence_role, "start_sample": start, "stop_sample": stop,
              "samples": stop - start if stop > start else None,
              "stage": "spectrum", "stages": [], "matching_attempts": []}
    try:
        # 可用样本/非法界优先（错误文本与历史一致），随后才判 NoteOn 释放边界
        if stop <= start or start < 0 or stop > min(len(left), len(right)):
            raise ValueError("analysis window exceeds available samples or has invalid bounds")
        if coordinate == COORDINATE_NOTE_ON_RELATIVE and stop > int(timing["note_off_sample"]):
            result["stage"], result["reason"] = "bounds", "release_boundary_exceeded"
            raise ValueError(f"window [{start}, {stop}) would analyze release samples from "
                             f"{timing['note_off_sample']}")
        observer_window = window if sample_bounds is None else exact_seconds_window(start, stop, rate)
        frequency, power = power_spectrum(left, right, rate, window, sample_bounds=(start, stop))
        peaks, rel, snr = spectral_peaks(frequency, power, min(LOW_FREQ, 0.5 * theory), MAX_FREQ)
        result["stages"].append({"stage": "spectrum", "status": "ok", "peaks": int(len(peaks))})
        cache = {}

        def observe(candidate):
            if candidate not in cache:
                half_width = min(0.2 * theory, max(4.0 / duration, 0.01 * candidate))
                cache[candidate] = observer.observe_partial(left, right, rate, observer_window, candidate,
                                                            half_width)
            return cache[candidate]

        result["stage"] = "matching"
        first, stiffness, numbers, observed = staged_match_multi(
            peaks, rel, snr, theory, seeds=seeds, min_snr=min_snr,
            trace=result["matching_attempts"])
        result["stages"].append({"stage": "matching", "status": "ok"})
        result["stage"] = "refinement"
        refined_numbers, refined_observed = match_partials(
            peaks, rel, snr, first, stiffness, STAGE_B_TOL, NEAREST_REL,
            mode="nearest", min_snr=min_snr, guard_db=REFINEMENT_GUARD_DB)
        refinement = {"stage": "refinement", "status": "not-selected",
                      "identified_partials": int(len(refined_numbers))}
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
                refinement["status"] = "selected"
        result["stages"].append(refinement)
        result["raw_candidate_family"] = {
            "partial_numbers": [int(n) for n in numbers],
            "observed_peak_Hz": [float(v) for v in observed],
            "f1_Hz": first, "effective_B": stiffness}
        result["stage"] = "partial-observation"
        observations = {}
        result["partial_observations"] = observations
        for number, candidate in zip(numbers, observed, strict=True):
            observations[str(int(number))] = {"raw_candidate_Hz": float(candidate),
                                              **observe(float(candidate))}
        keep = [i for i, n in enumerate(numbers)
                if observations[str(int(n))]["status"] == "single_component_adequate"]
        numbers = numbers[keep]
        observed = np.array([observations[str(int(n))]["frequency_hz"] for n in numbers])
        result.update({"identified_partials": int(len(numbers)),
                       "partial_numbers": [int(n) for n in numbers],
                       "observed_peak_Hz": [float(v) for v in observed]})
        result["stages"].append({"stage": "partial-observation", "status": "ok",
                                 "candidates": len(observations), "admitted": len(keep)})
        # 被排除编号上的多分量或保护带结构证据也必须阻断，不能用干净子集冒充整族。
        if any(observation_blocks_family(row) for row in observations.values()):
            result.update({"status": "inconclusive", "reason": "mixed_partial_observation"})
            return result
        if len(numbers) < 5:
            result.update({"status": "inconclusive", "reason": "insufficient_observer_admitted_partials"})
            return result
        result["stage"] = "observed-family-fit"
        solution = fit(observed, numbers, first, stiffness)
        first, stiffness = float(solution.x[0]), float(solution.x[1])
        result["stages"].append({"stage": "observed-family-fit", "status": "ok"})
        residual = 1200 * np.log2(observed / partial_prediction([first, stiffness], numbers))
        result.update({
            "identified_partials": int(len(numbers)),
            "partial_numbers": [int(n) for n in numbers],
            "observed_peak_Hz": [float(v) for v in observed],
            "f1_Hz": first, "effective_B": stiffness,
            "residual_cents": [float(v) for v in residual],
            "max_residual_cents": float(np.max(np.abs(residual))),
            "rms_residual_cents": float(np.sqrt(np.mean(residual ** 2)))})
        result["stage"] = "independent-prediction"
        independent = independent_split_prediction(
            peaks, rel, snr, theory, numbers, observed, seeds, min_snr, observe)
        result["independent_prediction"] = independent
        result["stages"].append({"stage": "independent-prediction", "status": independent["status"]})
        result.update({"status": "ok", "stage": "complete"})
    except Exception as error:  # noqa: BLE001 - 异常是逐窗证据，不能使另一窗口丢失
        result.update({"error": str(error), "error_type": type(error).__name__})
        result["stages"].append({"stage": result["stage"], "status": "failed",
                                 "error": str(error), "error_type": type(error).__name__})
    return result


def analyze_samples(left, right, rate, note, *, timing):
    """原始声道的共同分析入口，W1 失败时不改用 W2 的参数。

    timing 必填（无默认原点）：坐标决定窗界换算与释放边界校验，见模块文档；
    逐窗独立保留失败证据，绝不用另一窗替代或裁剪。
    """
    frames = len(left)
    if frames != len(right):
        raise ValueError("stereo sample counts differ")
    timing = validate_timing(timing, rate, frames, note)
    if note not in NOTES:
        raise ValueError(f"note {note} has no theory frequency in the active preset")
    theory = NOTES[note]
    min_snr = SNR_ADMISSION_DB if (SNR_ADMISSION_DB is not None and note >= SNR_MIN_NOTE) else None
    seeds = EXTENDED_SEEDS if note >= SNR_MIN_NOTE else DEFAULT_SEEDS
    windows = {}
    for name, window in WINDOWS.items():
        bounds = window_sample_bounds(window, timing, rate)
        windows[name] = analyze_window(left, right, rate, window, theory, seeds, min_snr,
                                       sample_bounds=bounds, timing=timing)
    failures = [{"window": name, "status": row["status"], "stage": row["stage"],
                 "error": row.get("error"), "reason": row.get("reason"),
                 "error_type": row.get("error_type")} for name, row in windows.items()
                if row["status"] != "ok"]
    main = windows.get("W1", {})
    prediction = main.get("independent_prediction", {})
    spread = None
    if all(windows.get(name, {}).get("status") == "ok" for name in ("W1", "W2")):
        spread = float(1200 * math.log2(windows["W1"]["f1_Hz"] / windows["W2"]["f1_Hz"]))
    return {"rate": rate, "frames": frames, "timing": timing, "theory_Hz": theory, "windows": windows,
            "status": ("window_failure" if any(w["status"] == "failed" for w in windows.values())
                       else "observation_inconclusive" if failures else "ok"), "window_failures": failures,
            "f1_window_spread_cents": spread, "f1_Hz": main.get("f1_Hz"),
            "effective_B": main.get("effective_B"), "identified_partials": main.get("identified_partials", 0),
            "independent_status": prediction.get("status", "window_failed"),
            "independent_max_cents": prediction.get("max_cents"),
            "independent_rms_cents": prediction.get("rms_cents")}


def analyze_unit(path, note, *, timing):
    """单元 WAV 入口；timing 必填，绑定的 wav_sha256 必须与文件逐字节一致。"""
    if isinstance(timing, dict) and timing.get("wav_sha256") is not None:
        if str(timing["wav_sha256"]) != sha256(Path(path)):
            raise ValueError("timing wav_sha256 does not match the analyzed WAV")
    rate, _, left, right = read_wav_stereo(path)
    return analyze_samples(left, right, rate, note, timing=timing)


def _snr_threshold(text):
    """CLI 值解析：'none' 关闭 SNR 通道；否则解析为 dB 阈值。"""
    if text.strip().lower() == "none":
        return None
    return float(text)


def _guard_threshold(text):
    """CLI 值解析：'off'/'none' 关闭候选强度守卫（legacy nearest 行为）；否则解析为 dB。"""
    if str(text).strip().lower() in ("off", "none"):
        return None
    return float(text)


def main():
    global NOTES, SESSIONS, VELOCITIES, SNR_ADMISSION_DB, SNR_MIN_NOTE, MAX_FREQ  # noqa: PLW0603 - 输入网格/通道由 CLI 决定
    global REFINEMENT_GUARD_DB  # noqa: PLW0603 - 方法修订 5 守卫由 CLI 决定
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", action="append", default=None,
                        help="consumed-data diagnostic batch root (WSL path), analysed with explicit "
                             "timing={coordinate:'file_absolute'}; repeat for multi-batch corpora")
    parser.add_argument("--wav", default=None,
                        help="single WAV analysed in NoteOn-relative coordinates (requires --note/--timing-report)")
    parser.add_argument("--note", type=int, default=None,
                        help="MIDI note for --wav (theory seed from A4=440 equal temperament)")
    parser.add_argument("--timing-report", type=Path, default=None,
                        help="A4 independent-verification.json or A5 reference-origin timing report for --wav")
    parser.add_argument("--out", required=True, help="output directory (WSL path); must not exist")
    parser.add_argument("--preset", choices=sorted(PRESETS), default="pilot",
                        help="input grid preset (pilot: n36/48/60; register: n72/84/96; corpus: training 12 notes; "
                             "bridge: n45/47; anchors2: n28/33/40/91/95; midfill: n25/27/49/51/64/74; "
                             "interp: n26/52/57 x3 vel x2 rate x2 reps; interpval: n25/27/53/59 x velocities 47/79/107; "
                             "interpval2: n29/55/67/88 x velocities 47/79/107)")
    parser.add_argument("--snr-admission-db", type=_snr_threshold, default=25.0,
                        help="local-SNR peak admission threshold (dB) at/above --snr-min-note; "
                             "default 25 (adopted high-register method); pass 'none' to disable")
    parser.add_argument("--snr-min-note", type=int, default=72,
                        help="lowest MIDI note for the SNR channel and extended stiffness seeds")
    parser.add_argument("--refinement-guard-db", type=_guard_threshold,
                        default=REFINEMENT_GUARD_DB,
                        help="nearest 精化轮候选强度守卫 (dB); 'off' 关闭守卫（legacy 行为）")
    parser.add_argument("--max-freq", type=float, default=20000.0,
                        help="peak-search and model upper frequency in Hz (default 20000); "
                             "does not increase the input WAV bandwidth")
    options = parser.parse_args()
    if options.wav is not None:
        if options.batch:
            parser.error("--wav and --batch are mutually exclusive")
        if options.note is None or options.timing_report is None:
            parser.error("--wav requires --note and --timing-report")
    elif not options.batch:
        parser.error("--batch is required for the consumed-data diagnostic (or pass --wav for a single unit)")
    REFINEMENT_GUARD_DB = options.refinement_guard_db
    SNR_ADMISSION_DB = options.snr_admission_db
    SNR_MIN_NOTE = options.snr_min_note
    MAX_FREQ = options.max_freq

    if options.wav is not None:
        NOTES = {options.note: 440.0 * 2.0 ** ((options.note - 69) / 12.0)}
        wav = Path(options.wav)
        try:
            # 先校验时间轴再建输出目录：错误报告不留下任何产物，也不被当作参考认证
            timing = load_timing_report(options.timing_report, wav)
            analysis = analyze_unit(wav, options.note, timing=timing)
        except ValueError as error:
            raise SystemExit(f"refused: {error}") from error
        out_dir = Path(options.out)
        if out_dir.exists():
            parser.error("Output exists; preserve previous evidence and use a fresh directory")
        out_dir.mkdir(parents=True, exist_ok=False)
        record = {"schema": "devpiano-task39-2-pilot-observer-analysis-v3-single-wav",
                  "mode": "single_wav_note_on_relative",
                  "wav": {"path": str(wav), "sha256": sha256(wav), "rate": analysis["rate"],
                          "frames": analysis["frames"], "note": options.note,
                          "note_name": NOTE_NAMES.get(options.note), "velocity": timing.get("velocity")},
                  "timing": timing,
                  "window_spans": {name: {"relative_s": row["bounds_s"], "start_sample": row["start_sample"],
                                          "stop_sample": row["stop_sample"], "samples": row["samples"],
                                          "coordinate": row["coordinate"], "evidence_role": row["evidence_role"]}
                                   for name, row in analysis["windows"].items()},
                  "analysis_tool_sha256": sha256(Path(__file__)),
                  "partial_observer_sha256": sha256(OBSERVER_PATH),
                  "analysis": analysis}
        with open(out_dir / "partial-analysis.json", "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=1, ensure_ascii=False)
        for name, row in analysis["windows"].items():
            print(f"{name}: samples [{row['start_sample']}, {row['stop_sample']}) = {row['samples']} samples "
                  f"relative={row['bounds_s']} coordinate={row['coordinate']} "
                  f"evidence_role={row['evidence_role']} status={row['status']} "
                  f"partials={row.get('identified_partials')}", flush=True)
        print(f"note={options.note} timing=note_on_relative evidence_role={timing['evidence_role']} "
              f"note_on_sample={timing['note_on_sample']} note_off_sample={timing['note_off_sample']} "
              f"wav_sha256={record['wav']['sha256']} status={analysis['status']}", flush=True)
        return

    NOTES, SESSIONS = PRESETS[options.preset]["notes"], PRESETS[options.preset]["sessions"]
    VELOCITIES = PRESETS[options.preset].get("velocities", VELOCITIES)
    batches = [Path(value) for value in options.batch]
    if not any((root / "sessions" / session).is_dir() for root in batches for session, *_ in SESSIONS):
        raise SystemExit(
            f"no expected session directory for preset '{options.preset}' under any --batch root "
            f"(expected e.g. {SESSIONS[0][0]}); check --preset/--batch")
    out_dir = Path(options.out)
    if out_dir.exists():
        parser.error("Output exists; preserve previous evidence and use a fresh directory")
    out_dir.mkdir(parents=True, exist_ok=False)

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
                analysis = analyze_unit(wav, note, timing={"coordinate": COORDINATE_FILE_ABSOLUTE})
                analysis.update({"unit": unit, "session": session, "note": note,
                                 "note_name": NOTE_NAMES[note], "velocity": velocity,
                                 "rate": rate, "repeat": rep, "wav_sha256": sha256(wav)})
                units[unit] = analysis
                if analysis["window_failures"]:
                    failures.append({"unit": unit, "reason": "window_failure",
                                     "windows": analysis["window_failures"]})
                independent_max = analysis["independent_max_cents"]
                independent_text = (f"indep max={independent_max:.3f} rms={analysis['independent_rms_cents']:.3f}"
                                    if independent_max is not None
                                    else f"indep {analysis['independent_status']}")
                print(f"{unit}: status={analysis['status']} partials={analysis['identified_partials']} "
                      f"f1={analysis['f1_Hz']} B={analysis['effective_B']} {independent_text} "
                      f"spread={analysis['f1_window_spread_cents']} cents", flush=True)
            except Exception as error:  # noqa: BLE001 - 记录失败单元而不中断批次
                failures.append({"unit": unit, "reason": str(error)})
                print(f"{unit}: FAILED {error}", flush=True)

    summary = {"schema": "devpiano-task39-2-pilot-observer-analysis-v3",
               "batch": str(batches[0]) if len(batches) == 1 else [str(root) for root in batches],
               "units_total": len(SESSIONS) * len(VELOCITIES),
               "units_analyzed": len(units), "failures": failures,
               "partial_observer_sha256": sha256(OBSERVER_PATH), "analysis_tool_sha256": sha256(Path(__file__)),
               "role": "method_development_or_consumed_data_diagnostic_not_formal_v3_acceptance",
               "timing": {"coordinate": COORDINATE_FILE_ABSOLUTE, "role": CONSUMED_DATA_ROLE,
                          "note": "windows are absolute seconds from the file start; not a v3 NoteOn-relative origin "
                                  "and not historical certification"},
               "criteria": {
                   "admitted_partial_prediction": "max <=3 cents and RMS <=1 cent on independent split holdout partials (method-amendment-1)",
                   "observer": "single-component adequate with a qualified conditional frequency interval",
                   "estimator_window_spread": "<=1 cent for admitted stationary line",
                   "minimum_identified_partials": 5},
               "families": {}}
    gate_spec = importlib.util.spec_from_file_location("analysis_quality", Path(__file__).with_name("validation-eval.py"))
    gate = importlib.util.module_from_spec(gate_spec)
    gate_spec.loader.exec_module(gate)
    for note in NOTES:
        for velocity in VELOCITIES:
            for rate in sorted({u["rate"] for u in units.values()}):
                rows = [u for u in units.values() if u["note"] == note and u["velocity"] == velocity and u["rate"] == rate]
                if not rows:
                    continue
                key = f"n{note}-v{velocity}-{rate}"
                missing = [u["unit"] for u in rows
                           if u["independent_max_cents"] is None or u["status"] != "ok"]
                expected_units = {f"n{note}-v{velocity}-{session_rate}-rep{rep}"
                                  for _, session_note, session_rate, rep in SESSIONS
                                  if session_note == note and session_rate == rate}
                missing.extend(sorted(expected_units - {u["unit"] for u in rows}))
                unit_quality = {u["unit"]: gate.reference_quality(u) for u in rows}
                repeat_rows = [{"unit": unit, "repeat": int(unit.rsplit("rep", 1)[1])}
                               for unit in sorted(expected_units)]
                repeat_quality = (gate.repeat_quality(repeat_rows, {u["unit"]: u for u in rows})
                                  if len(repeat_rows) > 1 else {"admitted": True, "reasons": []})
                entry = {"note_name": NOTE_NAMES[note], "units": [u["unit"] for u in rows],
                         "independent_max_cents": None if missing else max(u["independent_max_cents"] for u in rows),
                         "independent_rms_cents": None if missing else max(u["independent_rms_cents"] for u in rows),
                         "independent_missing_units": missing,
                         "identified_partials": min(u["identified_partials"] for u in rows),
                         "f1_Hz": [u["f1_Hz"] for u in rows],
                         "effective_B": [u["effective_B"] for u in rows],
                         "window_spread_cents": (None if any(u["f1_window_spread_cents"] is None for u in rows)
                                                 else max(abs(u["f1_window_spread_cents"]) for u in rows)),
                         "window_failures": {u["unit"]: u["window_failures"] for u in rows
                                             if u["window_failures"]}}
                entry["reference_quality"] = unit_quality
                entry["repeat_quality"] = repeat_quality
                entry["pass_quality"] = (not missing and all(q["admitted"] for q in unit_quality.values())
                                          and repeat_quality["admitted"])
                if len(rows) == 2 and not missing:
                    a, b = sorted(rows, key=lambda u: u["repeat"])
                    pair_delta = (None if a["independent_max_cents"] is None or b["independent_max_cents"] is None
                                  else float(abs(a["independent_max_cents"] - b["independent_max_cents"])))
                    entry["cross_repeat"] = {
                        "f1_delta_cents": float(1200 * math.log2(a["f1_Hz"] / b["f1_Hz"])),
                        "effective_B_relative_delta": (float(abs(a["effective_B"] - b["effective_B"]) / max(a["effective_B"], b["effective_B"]))
                                                       if max(a["effective_B"], b["effective_B"]) else 0.0),
                        "independent_max_delta_cents": pair_delta,
                    }
                entry["pass_max"] = entry["pass_quality"] and entry["independent_max_cents"] is not None and entry["independent_max_cents"] <= 3.0
                entry["pass_rms"] = entry["pass_quality"] and entry["independent_rms_cents"] is not None and entry["independent_rms_cents"] <= 1.0
                entry["pass_spread"] = entry["pass_quality"] and entry["window_spread_cents"] is not None and entry["window_spread_cents"] <= 1.0
                entry["pass_partials"] = entry["pass_quality"] and entry["identified_partials"] >= 5
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
              f"partials={family['identified_partials']} spread={family['window_spread_cents']}")


if __name__ == "__main__":
    main()
