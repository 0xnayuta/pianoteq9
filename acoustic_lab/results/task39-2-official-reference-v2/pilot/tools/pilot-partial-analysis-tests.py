#!/usr/bin/env python3
"""匹配编号恢复、逐窗证据保存、显式时间轴、NoteOn 样本网格与 dev render 报告契约的回归。

合成真值由本文件独立生成（不调用被测预测器当 oracle）；不含源匹配/接线回声断言，全部检查
analyze_samples / analyze_unit / load_timing_report / 观测器诊断的可观察输出。
"""
import hashlib
import importlib.util
import json
import math
import tempfile
import unittest
import wave
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location("ppa_tests", Path(__file__).with_name("pilot-partial-analysis.py"))
ppa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ppa)

FROZEN_WINDOWS = {"W1": (0.08, 3.8), "W2": (0.5, 4.1)}


def family_peaks(first, stiffness, count):
    # 真值由测试独立生成，不能调用被测预测器作为 oracle。
    numbers = np.arange(1, count + 1)
    return numbers * first * np.sqrt((1 + stiffness * numbers ** 2) / (1 + stiffness))


def tone(first, stiffness, rate, count, partials=12, amplitude=0.04):
    """独立生成的合成乐音（非谐性模型与 pilot 分析同源，但真值不经被测函数）。"""
    time = np.arange(count) / rate
    value = np.zeros(count)
    for number, frequency in enumerate(family_peaks(first, stiffness, partials), 1):
        value += amplitude / number * np.cos(2 * math.pi * frequency * time + 0.37 * number)
    return value


def placed_tone(first, stiffness, rate, frames, note_on, partials=12):
    """note_on 之前严格静音、之后为同一波形样本段的合成单元。"""
    value = np.zeros(frames)
    value[note_on:] = tone(first, stiffness, rate, frames - note_on, partials)
    return value


def write_wav_stereo(path, rate, left, right):
    ints = np.round(np.clip(np.stack([left, right], axis=1), -1.0, 1.0) * float(1 << 23)).astype(np.int64)
    unsigned = (ints & 0xFFFFFF).astype("<u4")
    raw = unsigned.view(np.uint8).reshape(-1, 4)[:, :3].reshape(-1).tobytes()
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(3)
        handle.setframerate(rate)
        handle.writeframes(raw)


def file_sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class PpaFixture(unittest.TestCase):
    """固定音符理论初值与冻结窗格；不改阈值、不动 seeds/SNR 阈值规则。"""

    rate = 44100
    first = 440.0
    stiffness = 3e-4

    def setUp(self):
        self.saved = {name: getattr(ppa, name) for name in
                      ("NOTES", "WINDOWS", "SNR_ADMISSION_DB", "SNR_MIN_NOTE", "REFINEMENT_GUARD_DB")}
        ppa.NOTES = {69: self.first, 55: 195.9977}
        ppa.WINDOWS = dict(FROZEN_WINDOWS)
        ppa.SNR_ADMISSION_DB = 25.0
        ppa.SNR_MIN_NOTE = 72

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(ppa, name, value)

    def timing(self, frames, note_on, note_off, note=69, **extra):
        return {"coordinate": ppa.COORDINATE_NOTE_ON_RELATIVE, "sample_rate": self.rate,
                "frames": frames, "note": note, "note_on_sample": note_on,
                "note_off_sample": note_off, "evidence_role": ppa.ROLE_SYNTHETIC_FIXTURE, **extra}


class MixedFamily(PpaFixture):
    def test_detected_companion_prevents_static_subset_fit_in_both_windows(self):
        frames = 190000
        number = 6
        frequency = float(family_peaks(self.first, self.stiffness, number)[-1])
        time = np.arange(frames) / self.rate
        value = tone(self.first, self.stiffness, self.rate, frames)
        value += 0.03 * np.cos(2 * math.pi * (frequency + 1.7) * time + 0.6)
        result = ppa.analyze_samples(
            value, value, self.rate, 69, timing=self.timing(frames, 0, 185220))
        self.assertEqual(result["status"], "observation_inconclusive")
        for name in ("W1", "W2"):
            with self.subTest(window=name):
                window = result["windows"][name]
                self.assertEqual(window["status"], "inconclusive")
                observation = window["partial_observations"][str(number)]
                self.assertEqual(observation["status"], "resolved_components")
                frequencies = [entry["frequency_hz"] for entry in observation["components"]]
                for expected in (frequency, frequency + 1.7):
                    self.assertLess(min(abs(actual - expected) for actual in frequencies), 0.01)
                self.assertIsNone(window.get("effective_B"))
                self.assertIsNone(window.get("independent_prediction"))

    def test_guarded_companion_blocks_a_sufficient_clean_subset(self):
        first = 65.40639132514966
        ppa.NOTES = {36: first}
        frames = ppa.llround(4.3 * self.rate)
        value = tone(first, self.stiffness, self.rate, frames, partials=9)
        companion = float(family_peaks(first, self.stiffness, 2)[-1]) + 1.7
        time = np.arange(frames) / self.rate
        value += 0.014 * np.cos(2 * math.pi * companion * time + 0.6)
        result = ppa.analyze_samples(
            value, value, self.rate, 36,
            timing=self.timing(frames, 0, ppa.llround(4.2 * self.rate), note=36))
        self.assertEqual(result["status"], "observation_inconclusive")
        for name in ("W1", "W2"):
            with self.subTest(window=name):
                window = result["windows"][name]
                self.assertEqual(window["status"], "inconclusive", window)
                self.assertEqual(window["stage"], "partial-observation")
                observation = window["partial_observations"]["2"]
                self.assertEqual(observation["status"], "ambiguous")
                self.assertIn("coherent_structure_outside_component_search_bounds",
                              observation["reasons"])
                self.assertIn(2, window["raw_candidate_family"]["partial_numbers"])
                self.assertNotIn(2, window["partial_numbers"])
                self.assertGreaterEqual(len(window["partial_numbers"]), 5)
                self.assertIsNone(window.get("effective_B"))
                self.assertIsNone(window.get("independent_prediction"))


class LowCandidateBand(PpaFixture):
    def test_lowest_note_with_exactly_five_partials_keeps_independent_prediction(self):
        first = 27.5
        ppa.NOTES = {21: first}
        frames = ppa.llround(4.3 * self.rate)
        value = placed_tone(first, self.stiffness, self.rate, frames, 0, partials=5)
        result = ppa.analyze_samples(
            value, value, self.rate, 21,
            timing=self.timing(frames, 0, ppa.llround(4.2 * self.rate), note=21))
        for name in ("W1", "W2"):
            with self.subTest(window=name):
                window = result["windows"][name]
                self.assertEqual(window["status"], "ok", window)
                self.assertEqual(window["partial_numbers"], [1, 2, 3, 4, 5])
                self.assertLessEqual(abs(window["f1_Hz"] - first),
                                     max(0.005, first * (2 ** (0.05 / 1200) - 1)))
                self.assertLessEqual(abs(window["effective_B"] / self.stiffness - 1), 0.02)
                prediction = window["independent_prediction"]
                self.assertEqual(prediction["status"], "ok", prediction)
                self.assertGreaterEqual(prediction["training_size"], 3)
                self.assertGreaterEqual(prediction["holdout_size"], 2)
                self.assertLessEqual(prediction["rms_cents"], 1.0)
                self.assertLessEqual(prediction["max_cents"], 3.0)


class MatchingInitialization(unittest.TestCase):
    def test_low_order_start_recovers_wrong_seed_without_high_order_alias(self):
        first, stiffness = 43.653529, 8e-5
        peaks = family_peaks(first, stiffness, 85)
        rel = 1.0 / np.arange(1, len(peaks) + 1) ** 1.6
        f, b, numbers, observed = ppa.staged_match(peaks, rel, np.full(len(peaks), 60.0), first, 2e-4)
        self.assertLess(abs(1200 * math.log2(f / first)), 0.005)
        self.assertLess(abs(b / stiffness - 1), 0.0001)
        self.assertTrue(np.array_equal(numbers, np.arange(1, len(peaks) + 1)))
        self.assertLess(float(np.max(np.abs(observed - peaks))), 1e-8)

    def test_no_low_order_information_cannot_be_replaced_with_high_order_self_fit(self):
        first, stiffness = 100.0, 1e-4
        peaks = family_peaks(first, stiffness, 30)[8:]
        trace = []
        with self.assertRaises(ppa.MatchFailure):
            ppa.staged_match_multi(peaks, np.ones(len(peaks)), np.full(len(peaks), 60.0), first, trace=trace)
        self.assertTrue(all(row["status"] == "failed" for row in trace))
        self.assertTrue(all(row["stages"][0]["identified_partials"] == 0 for row in trace))


class TimingContract(PpaFixture):
    """显式 timing 必填、无原点回落、非法/不匹配时间轴一律拒绝。"""

    def signal(self, count=4000):
        return placed_tone(self.first, self.stiffness, self.rate, count, 0)

    def test_timing_is_required_keyword_and_file_absolute_is_explicit(self):
        value = self.signal(int(4.2 * self.rate))
        with self.assertRaises(TypeError):
            ppa.analyze_samples(value, value, self.rate, 69)
        with self.assertRaises(TypeError):
            ppa.analyze_unit(Path("unused.wav"), 69)
        result = ppa.analyze_samples(value, value, self.rate, 69,
                                     timing={"coordinate": ppa.COORDINATE_FILE_ABSOLUTE})
        self.assertEqual(result["timing"], {"coordinate": ppa.COORDINATE_FILE_ABSOLUTE})
        w1 = result["windows"]["W1"]
        self.assertEqual(w1["coordinate"], ppa.COORDINATE_FILE_ABSOLUTE)
        self.assertIsNone(w1["evidence_role"])
        # file_absolute 保持历史 int() 截断口径的绝对样本界（不套用 v3 的一采样修正）
        self.assertEqual((w1["start_sample"], w1["stop_sample"]), (int(0.08 * self.rate), int(3.8 * self.rate)))
        self.assertEqual(result["windows"]["W2"]["stop_sample"], int(4.1 * self.rate))
        self.assertEqual((int(4.1 * self.rate), ppa.llround(4.1 * self.rate)), (180809, 180810))

    def test_file_absolute_refuses_note_on_origin_and_invalid_timings(self):
        value = self.signal(int(4.2 * self.rate))
        cases = [
            ({"coordinate": ppa.COORDINATE_FILE_ABSOLUTE, "note_on_sample": 10}, "NoteOn origin"),
            ({}, "missing coordinate"),
            ({"coordinate": "relative"}, "unknown coordinate"),
            ({"coordinate": ppa.COORDINATE_NOTE_ON_RELATIVE}, "missing role"),
            ({"coordinate": ppa.COORDINATE_NOTE_ON_RELATIVE, "evidence_role": ppa.ROLE_SYNTHETIC_FIXTURE},
             "missing origin/rate/frames"),
            (self.timing(len(value), 100, 100, sample_rate=48000), "rate mismatch"),
            (self.timing(len(value) + 5, 100, 200), "frames mismatch"),
            (self.timing(len(value), 100, 200, note=71), "note mismatch"),
            (self.timing(len(value), 100, 200, evidence_role="unknown_role"), "unknown role"),
            (self.timing(len(value), 100, 200,
                         evidence_role=ppa.ROLE_REFERENCE_ORIGIN_AUTHENTICATED), "reference origin unsupported"),
            (dict(self.timing(len(value), 100, 200), evidence_role=ppa.ROLE_DEV_RENDER_VERIFICATION),
             "dev render without identity"),
            (self.timing(len(value), 300, 200), "note_on >= note_off"),
            (self.timing(len(value), 100.5, 200), "fractional note_on"),
            (self.timing(len(value), -5, 200), "negative note_on"),
            (self.timing(len(value), 100, len(value) + 1), "release beyond frames"),
        ]
        for timing, label in cases:
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    ppa.analyze_samples(value, value, self.rate, 69, timing=timing)
        with self.assertRaises(ValueError):
            ppa.analyze_samples(value, value, self.rate, 69, timing=None)


class SampleGrid(PpaFixture):
    """NoteOn 网格：llround 半远离零、44.1/48 kHz 实际样本跨度、观测器同段切片。"""

    def test_llround_rounds_half_away_from_zero_on_the_grid(self):
        self.assertEqual(ppa.note_on_relative_bounds((0.25, 1.25), 0, 2), (1, 3))
        self.assertEqual(ppa.note_on_relative_bounds((0.0, 4.1), 0, 44100), (0, 180810))
        self.assertEqual(ppa.note_on_relative_bounds((0.0, 4.1), 0, 48000), (0, 196800))
        # int() 截断在 48000 下会少取一个样本：0.29*48000 = 13919.999999999998
        self.assertEqual(int(0.29 * 48000), 13919)
        self.assertEqual(ppa.note_on_relative_bounds((0.29, 1.79), 100, 48000), (14020, 86020))

    def test_window_spans_match_44k_48k_grid_and_observer_slices(self):
        expected = {44100: {"prefix": 4410, "frames": 191630,
                            "W1": (7938, 171990, 164052), "W2": (26460, 185220, 158760)},
                    48000: {"prefix": 4800, "frames": 208400,
                            "W1": (8640, 187200, 178560), "W2": (28800, 201600, 172800)}}
        for rate, plan in expected.items():
            with self.subTest(rate=rate):
                ppa.NOTES = {69: self.first}
                value = placed_tone(self.first, self.stiffness, rate, plan["frames"], plan["prefix"])
                note_on = plan["prefix"]
                note_off = note_on + ppa.llround(4.2 * rate)
                result = ppa.analyze_samples(value, value, rate, 69, timing={
                    "coordinate": ppa.COORDINATE_NOTE_ON_RELATIVE, "sample_rate": rate,
                    "frames": plan["frames"], "note": 69, "note_on_sample": note_on,
                    "note_off_sample": note_off, "evidence_role": ppa.ROLE_SYNTHETIC_FIXTURE})
                for name in ("W1", "W2"):
                    start, stop, samples = plan[name]
                    window = result["windows"][name]
                    self.assertEqual((window["start_sample"], window["stop_sample"], window["samples"]),
                                     (start, stop, samples))
                    self.assertEqual(window["bounds_s"], list(FROZEN_WINDOWS[name]))
                    self.assertEqual(window["coordinate"], ppa.COORDINATE_NOTE_ON_RELATIVE)
                    self.assertEqual(window["evidence_role"], ppa.ROLE_SYNTHETIC_FIXTURE)
                    observed = window.get("partial_observations") or {}
                    self.assertTrue(observed, f"{name} produced no partial observation evidence")
                    for entry in observed.values():
                        diagnostics = entry["diagnostics"]
                        self.assertEqual(diagnostics["samples"], samples)
                        # 观测器只收秒窗：必须精确还原整数端点，不得因 float*rate 少取样本
                        self.assertEqual(int(diagnostics["bounds_s"][0] * rate), start)
                        self.assertEqual(int(diagnostics["bounds_s"][1] * rate), stop)

    def test_fractional_relative_window_keeps_every_sample(self):
        ppa.WINDOWS = {"W1": (0.29, 1.79), "W2": (1.5, 3.5)}
        rate, note_on, frames = 48000, 100, 170000
        note_off = note_on + ppa.llround(3.5 * rate) + 1000  # 仍晚于 W2 名义窗尾，且在帧内
        value = placed_tone(self.first, self.stiffness, rate, frames, note_on)
        result = ppa.analyze_samples(value, value, rate, 69, timing={
            "coordinate": ppa.COORDINATE_NOTE_ON_RELATIVE, "sample_rate": rate, "frames": frames,
            "note": 69, "note_on_sample": note_on, "note_off_sample": note_off,
            "evidence_role": ppa.ROLE_SYNTHETIC_FIXTURE})
        w1 = result["windows"]["W1"]
        self.assertEqual((w1["start_sample"], w1["stop_sample"]), (14020, 86020))
        self.assertEqual(w1["samples"], 72000)
        self.assertEqual((result["windows"]["W2"]["start_sample"], result["windows"]["W2"]["stop_sample"]),
                         (72100, 168100))
        for entry in (w1.get("partial_observations") or {}).values():
            self.assertEqual(int(entry["diagnostics"]["bounds_s"][0] * rate), 14020)
            self.assertEqual(int(entry["diagnostics"]["bounds_s"][1] * rate), 86020)
            self.assertEqual(entry["diagnostics"]["samples"], 72000)

    def test_translation_invariance_with_nonzero_prefix(self):
        rate, length, prefix = 44100, 190000, 5000
        base = placed_tone(self.first, self.stiffness, rate, length, 0)
        time = np.arange(prefix) / rate
        head = np.concatenate([0.02 * np.cos(2 * math.pi * 311.0 * time), base])  # 非零前缀，非静音
        base_timing = {"coordinate": ppa.COORDINATE_NOTE_ON_RELATIVE, "sample_rate": rate, "frames": length,
                       "note": 69, "note_on_sample": 0, "note_off_sample": 185220,
                       "evidence_role": ppa.ROLE_SYNTHETIC_FIXTURE,
                       "case_id": "translation-invariance-44100", "pcm_sha256": "5" * 64}
        head_timing = dict(base_timing, frames=length + prefix, note_on_sample=prefix, note_off_sample=prefix + 185220)
        base_result = ppa.analyze_samples(base, base, rate, 69, timing=base_timing)
        head_result = ppa.analyze_samples(head, head, rate, 69, timing=head_timing)
        # 输出保留调用方时间轴的全部键（含夹具身份），不改写、不补默认原点
        self.assertEqual(base_result["timing"], base_timing)
        self.assertEqual(head_result["timing"], head_timing)
        for name in ("W1", "W2"):
            base_window, head_window = base_result["windows"][name], head_result["windows"][name]
            self.assertEqual(head_window["start_sample"], base_window["start_sample"] + prefix)
            self.assertEqual(head_window["stop_sample"], base_window["stop_sample"] + prefix)
            self.assertTrue(base_window.get("partial_numbers"), f"{name} produced no matched partial numbers")
            self.assertEqual(head_window["partial_numbers"], base_window["partial_numbers"])
            self.assertEqual(head_window["f1_Hz"], base_window["f1_Hz"])
            self.assertEqual(head_window["effective_B"], base_window["effective_B"])
            self.assertEqual(head_window["residual_cents"], base_window["residual_cents"])


class ReleaseBoundary(PpaFixture):
    """释放样本半开排除：越界窗只失败该窗，W1 结果完整保留。"""

    frames, note_on = 190000, 0
    w2_stop = 180810  # 0 + llround(4.1 * 44100)

    def test_release_sample_itself_is_excluded_from_the_half_open_window(self):
        value = placed_tone(self.first, self.stiffness, self.rate, self.frames, self.note_on)
        result = ppa.analyze_samples(value, value, self.rate, 69, timing=self.timing(self.frames, self.note_on,
                                                                                     self.w2_stop))
        self.assertEqual(result["windows"]["W2"]["stop_sample"], self.w2_stop)
        self.assertEqual(result["windows"]["W2"]["status"], "ok")
        self.assertFalse(result["window_failures"])

    def test_window_that_would_include_release_samples_fails_alone(self):
        value = placed_tone(self.first, self.stiffness, self.rate, self.frames, self.note_on)
        result = ppa.analyze_samples(value, value, self.rate, 69, timing=self.timing(self.frames, self.note_on,
                                                                                     self.w2_stop - 1))
        w1, w2 = result["windows"]["W1"], result["windows"]["W2"]
        self.assertEqual(w2["status"], "failed")
        self.assertEqual(w2["stage"], "bounds")
        self.assertEqual(w2["reason"], "release_boundary_exceeded")
        self.assertEqual((w2["start_sample"], w2["stop_sample"]), (22050, self.w2_stop))
        self.assertEqual(w1["status"], "ok")
        self.assertTrue(w1.get("partial_numbers"))
        self.assertEqual(result["status"], "window_failure")
        self.assertEqual([row["window"] for row in result["window_failures"]], ["W2"])
        self.assertIsNone(result["f1_window_spread_cents"])

    def test_truncated_frames_fail_only_the_unavailable_window(self):
        frames = ppa.llround(3.85 * self.rate)
        value = placed_tone(self.first, self.stiffness, self.rate, frames, self.note_on)
        result = ppa.analyze_samples(value, value, self.rate, 69,
                                     timing=self.timing(frames, self.note_on, frames - 1))
        self.assertEqual(result["windows"]["W1"]["status"], "ok")
        self.assertEqual(result["windows"]["W2"]["status"], "failed")
        self.assertEqual(result["windows"]["W2"]["stage"], "spectrum")
        self.assertEqual((result["windows"]["W2"]["start_sample"], result["windows"]["W2"]["stop_sample"]),
                         (22050, self.w2_stop))
        self.assertTrue(result["windows"]["W1"].get("partial_numbers"))
        self.assertEqual([row["window"] for row in result["window_failures"]], ["W2"])


class WindowIsolation(PpaFixture):
    """绝对窗诊断域：W1 失败不改用 W2 参数，W2 失败不丢弃 W1。"""

    def setUp(self):
        super().setUp()
        self.rate = 44100
        ppa.WINDOWS = {"W1": (0.0, 0.8), "W2": (1.0, 3.9)}
        self.file_timing = {"coordinate": ppa.COORDINATE_FILE_ABSOLUTE}

    def signal(self):
        value = np.zeros(int(4.2 * self.rate))
        value[:] = tone(195.9977, self.stiffness, self.rate, int(4.2 * self.rate))
        return self.rate, value

    def test_failed_first_window_retains_late_window_without_promoting_it(self):
        rate, value = self.signal()
        clipped = value.copy()
        clipped[:int(0.9 * rate)] = 0
        result = ppa.analyze_samples(clipped, clipped, rate, 55, timing=self.file_timing)
        self.assertEqual(result["windows"]["W1"]["status"], "failed")
        self.assertEqual(result["windows"]["W1"]["stage"], "spectrum")
        self.assertEqual(result["windows"]["W2"]["status"], "ok")
        self.assertLess(abs(result["windows"]["W2"]["effective_B"] / self.stiffness - 1), 0.02)
        self.assertIsNone(result["f1_Hz"])
        self.assertIsNone(result["f1_window_spread_cents"])
        self.assertEqual([row["window"] for row in result["window_failures"]], ["W1"])

    def test_unavailable_late_samples_do_not_discard_first_window(self):
        rate, value = self.signal()
        short = value[:int(0.9 * rate)]
        result = ppa.analyze_samples(short, short, rate, 55, timing=self.file_timing)
        self.assertEqual(result["windows"]["W2"]["stage"], "spectrum")
        self.assertEqual(result["windows"]["W2"]["status"], "failed")
        self.assertTrue(result["windows"]["W1"].get("partial_numbers"))
        self.assertIsNone(result["f1_window_spread_cents"])


class TimingReportContract(PpaFixture):
    """A4 independent-verification.json 只能登记为 dev render 契约证据，绝不成为参考认证。"""

    frames, note_on, note_off = 190000, 4410, 185220

    def setUp(self):
        super().setUp()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.wav_path = root / "render.wav"
        value = placed_tone(self.first, self.stiffness, self.rate, self.frames, self.note_on)
        write_wav_stereo(self.wav_path, self.rate, value, value * 0.8)
        self.report_path = root / "independent-verification.json"

    def base_report(self):
        return {"role": ppa.DEV_RENDER_REPORT_ROLE, "passed": True, "failures": [],
                "midi": {"sha256": "0" * 64, "note": 69, "velocity": 70,
                         "events": [{"tick": 0, "kind": "tempo", "microseconds_per_quarter": 500000},
                                    {"tick": 96, "kind": "note_on", "note": 69, "velocity": 70},
                                    {"tick": 4032, "kind": "note_off", "note": 69, "velocity": 0}]},
                "wav": {"rate": self.rate, "channels": 2, "bits": 24, "frames": self.frames},
                "wav_sha256": file_sha256(self.wav_path),
                "receipt_sha256": "1" * 64,
                "first_nonzero_sample": self.note_on, "last_nonzero_sample": self.frames - 1,
                "note_on_sample": self.note_on, "note_off_sample": self.note_off,
                "windows": {"W1": {"start_sample": 7938, "stop_sample": 171990},
                            "W2": {"start_sample": 26460, "stop_sample": 185220}},
                "reference_origin_certified": False, "static_B_qualified": False,
                "formal_evaluation": False, "contract_sha256": "2" * 64}

    def write_report(self, report):
        self.report_path.write_text(json.dumps(report), encoding="utf-8")
        return self.report_path

    def test_dev_render_report_registers_note_on_relative_dev_evidence_only(self):
        timing = ppa.load_timing_report(self.write_report(self.base_report()), self.wav_path)
        self.assertEqual(timing["coordinate"], ppa.COORDINATE_NOTE_ON_RELATIVE)
        self.assertEqual(timing["evidence_role"], ppa.ROLE_DEV_RENDER_VERIFICATION)
        self.assertNotEqual(timing["evidence_role"], ppa.ROLE_REFERENCE_ORIGIN_AUTHENTICATED)
        self.assertFalse(timing["reference_origin_certified"])
        self.assertEqual((timing["sample_rate"], timing["frames"], timing["note_on_sample"],
                          timing["note_off_sample"], timing["note"]), (self.rate, self.frames,
                                                                       self.note_on, self.note_off, 69))
        self.assertEqual(timing["wav_sha256"], file_sha256(self.wav_path))
        self.assertEqual(timing["report_sha256"], file_sha256(self.report_path))
        self.assertEqual(timing["reported_windows"], self.base_report()["windows"])
        self.assertFalse(timing["energy_diagnostics"]["gating"])
        result = ppa.analyze_unit(self.wav_path, 69, timing=timing)
        self.assertEqual((result["windows"]["W1"]["start_sample"], result["windows"]["W1"]["stop_sample"]),
                         (7938, 171990))
        self.assertEqual((result["windows"]["W2"]["start_sample"], result["windows"]["W2"]["stop_sample"]),
                         (26460, 185220))
        self.assertEqual(result["windows"]["W2"]["samples"], 158760)
        self.assertEqual(result["timing"]["evidence_role"], ppa.ROLE_DEV_RENDER_VERIFICATION)

    def test_report_refusals_cover_fields_hash_length_and_origin_grid(self):
        variants = {
            "wrong role": {"role": "reference_origin_certification"},
            "failed verification": {"passed": False},
            "recorded failures": {"failures": ["x"]},
            "origin flipped green": {"reference_origin_certified": True},
            "static B flipped green": {"static_B_qualified": True},
            "formal evaluation flipped green": {"formal_evaluation": True},
            "missing origin": {"note_on_sample": None},
            "reversed origin": {"note_on_sample": self.note_off, "note_off_sample": self.note_on},
            "release beyond frames": {"note_off_sample": self.frames + 1},
            "no MIDI note identity": {"midi": {"sha256": "0" * 64, "events": []}},
            "hash mismatch": {"wav_sha256": "3" * 64},
            "frames mismatch": {"wav": {"rate": self.rate, "channels": 2, "bits": 24, "frames": self.frames - 1}},
            "rate mismatch": {"wav": {"rate": 48000, "channels": 2, "bits": 24, "frames": self.frames}},
            "origin past audio content": {"note_on_sample": self.note_on + 1},
            "window grid inconsistent": {"windows": {"W1": {"start_sample": 7938, "stop_sample": 171989},
                                                     "W2": {"start_sample": 26460, "stop_sample": 185220}}},
            "window grid truncated": {"windows": {"W1": {"start_sample": 7938, "stop_sample": 171990}}},
        }
        for label, override in variants.items():
            with self.subTest(label=label):
                report = dict(self.base_report(), **override)
                with self.assertRaises(ValueError):
                    ppa.load_timing_report(self.write_report(report), self.wav_path)

    def test_analyze_unit_binds_wav_identity_and_length(self):
        timing = dict(self.timing(self.frames, self.note_on, self.note_off), wav_sha256=file_sha256(self.wav_path))
        result = ppa.analyze_unit(self.wav_path, 69, timing=timing)
        self.assertEqual(result["timing"]["wav_sha256"], file_sha256(self.wav_path))
        with self.assertRaises(ValueError):
            ppa.analyze_unit(self.wav_path, 69, timing=dict(timing, wav_sha256="4" * 64))
        with self.assertRaises(ValueError):
            ppa.analyze_unit(self.wav_path, 69, timing=self.timing(self.frames + 1, self.note_on, self.note_off))


class ReferenceOriginTiming(PpaFixture):
    """A5 证书 + 实际 MIDI 事件 + WAV 身份 -> reference_origin_authenticated；不接受自报坐标。"""

    rate = 48000
    frames = 259328
    note_on = 4800
    note_off = 201600
    MIDI_HEX = ("4d546864000000060000000101e04d54726b00000021"
                "00ff510307a12000b0400000b0420000b04300"
                "609045469e608045008740ff2f00")

    def setUp(self):
        super().setUp()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.wav_path = root / "render.wav"
        value = placed_tone(self.first, self.stiffness, self.rate, self.frames, self.note_on)
        write_wav_stereo(self.wav_path, self.rate, value, value * 0.8)
        self.midi_path = root / "n69-v70.mid"
        self.midi_path.write_bytes(bytes.fromhex(self.MIDI_HEX))
        self.certificate_path = root / "origin-certificate-v1.json"
        self.certificate = {
            "schema": ppa.REFERENCE_ORIGIN_CERTIFICATE_SCHEMA,
            "status": "authenticated",
            "midi_origin_sample": 0,
            "rates": {"44100": {"note_on_nominal_sample": 4410},
                      "48000": {"note_on_nominal_sample": 4800}},
        }
        self.write_certificate()
        self.report_path = root / "timing.json"

    def write_certificate(self):
        self.certificate_path.write_text(json.dumps(self.certificate), encoding="utf-8")

    def base_report(self):
        return {
            "schema": ppa.REFERENCE_TIMING_SCHEMA,
            "role": ppa.ROLE_REFERENCE_ORIGIN_AUTHENTICATED,
            "unit": "n69-v70-48000",
            "passed": True,
            "failures": [],
            "reference_origin_certified": True,
            "certificate": {"path": str(self.certificate_path),
                            "sha256": file_sha256(self.certificate_path),
                            "midi_origin_sample": 0},
            "midi": {"path": str(self.midi_path), "sha256": file_sha256(self.midi_path),
                     "ppq": 480, "tempo_us": 500000, "note": 69, "velocity": 70,
                     "note_on_tick": 96, "note_off_tick": 4032,
                     "note_on_seconds": 0.1, "note_off_seconds": 4.2},
            "wav": {"path": str(self.wav_path), "sha256": file_sha256(self.wav_path),
                    "rate": self.rate, "frames": self.frames, "channels": 2, "bits": 24},
            "wav_sha256": file_sha256(self.wav_path),
            "note_on_sample": self.note_on,
            "note_off_sample": self.note_off,
            "windows": {"W1": {"start_sample": 8640, "stop_sample": 187200},
                        "W2": {"start_sample": 28800, "stop_sample": 201600}},
        }

    def write_report(self, report):
        self.report_path.write_text(json.dumps(report), encoding="utf-8")
        return self.report_path

    def test_reference_role_is_supported_and_midi_parses_exact_ticks(self):
        self.assertIn(ppa.ROLE_REFERENCE_ORIGIN_AUTHENTICATED, ppa.SUPPORTED_EVIDENCE_ROLES)
        timeline = ppa.parse_smf_note_timeline(self.midi_path, 69, 70)
        self.assertEqual((timeline["ppq"], timeline["note_on_tick"], timeline["note_off_tick"]),
                         (480, 96, 4032))
        self.assertAlmostEqual(timeline["note_on_seconds"], 0.1, places=12)
        self.assertAlmostEqual(timeline["note_off_seconds"], 4.2, places=12)

    def test_reference_report_registers_certificate_timing(self):
        timing = ppa.load_timing_report(self.write_report(self.base_report()), self.wav_path)
        self.assertEqual(timing["coordinate"], ppa.COORDINATE_NOTE_ON_RELATIVE)
        self.assertEqual(timing["evidence_role"], ppa.ROLE_REFERENCE_ORIGIN_AUTHENTICATED)
        self.assertTrue(timing["reference_origin_certified"])
        self.assertEqual(timing["midi_origin_sample"], 0)
        self.assertEqual((timing["note_on_sample"], timing["note_off_sample"]),
                         (self.note_on, self.note_off))
        self.assertEqual(timing["certificate_sha256"], file_sha256(self.certificate_path))
        self.assertEqual(timing["midi_sha256"], file_sha256(self.midi_path))
        self.assertEqual(timing["reported_windows"], self.base_report()["windows"])
        self.assertFalse(timing["energy_diagnostics"]["gating"])
        result = ppa.analyze_unit(self.wav_path, 69, timing=timing)
        self.assertEqual(result["timing"]["evidence_role"], ppa.ROLE_REFERENCE_ORIGIN_AUTHENTICATED)
        self.assertEqual((result["windows"]["W1"]["start_sample"], result["windows"]["W1"]["stop_sample"]),
                         (8640, 187200))
        self.assertEqual((result["windows"]["W2"]["start_sample"], result["windows"]["W2"]["stop_sample"]),
                         (28800, 201600))

    def test_reference_report_refusals_cover_identity_formula_and_grid(self):
        base = self.base_report()
        variants = {
            "wrong schema": {"schema": "other"},
            "dev role": {"role": ppa.DEV_RENDER_REPORT_ROLE},
            "failed": {"passed": False},
            "recorded failures": {"failures": ["x"]},
            "origin not certified": {"reference_origin_certified": False},
            "certificate hash": {"certificate": dict(base["certificate"], sha256="0" * 64)},
            "midi hash": {"midi": dict(base["midi"], sha256="0" * 64)},
            "midi tick": {"midi": dict(base["midi"], note_off_tick=4033)},
            "midi seconds": {"midi": dict(base["midi"], note_off_seconds=4.3)},
            "wav hash": {"wav_sha256": "0" * 64},
            "wav frames": {"wav": dict(base["wav"], frames=self.frames - 1)},
            "formula on": {"note_on_sample": self.note_on + 1},
            "formula off": {"note_off_sample": self.note_off + 1},
            "window grid": {"windows": {"W1": {"start_sample": 8640, "stop_sample": 187199},
                                        "W2": {"start_sample": 28800, "stop_sample": 201600}}},
        }
        for label, override in variants.items():
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    ppa.load_timing_report(self.write_report(dict(base, **override)), self.wav_path)

    def test_unauthenticated_certificate_is_rejected_even_with_matching_hash(self):
        report = self.base_report()
        self.certificate["status"] = "draft"
        self.write_certificate()
        report["certificate"]["sha256"] = file_sha256(self.certificate_path)
        with self.assertRaisesRegex(ValueError, "not authenticated"):
            ppa.load_timing_report(self.write_report(report), self.wav_path)

    def test_analyze_unit_rejects_reference_timing_without_certificate_binding(self):
        timing = ppa.load_timing_report(self.write_report(self.base_report()), self.wav_path)
        for field in ("wav_sha256", "certificate_sha256", "reference_origin_certified"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    ppa.analyze_unit(self.wav_path, 69, timing=dict(timing, **{field: None}))


if __name__ == "__main__":
    unittest.main()
