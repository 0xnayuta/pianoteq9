#!/usr/bin/env python3
"""Task 39-2 A3 NoteOn 相对坐标方法资格执行器（development / qualification 双角色）。

现行执行器契约（完整有限登记，非 v3 验收协议；已消费登记不得重放）：
- 观察器窗在候选提取前按原始样本界分类；仅登记且实际成立的帧末负例可记录 runner 输入拒绝，
  不裁剪、不补零、不调用该窗的候选或观察器，也不产生分音认证；合法窗上的观察器异常仍失败。
- 合成 24-bit 双声道 PCM：note_on_sample>0 的逐例非零 MIDI 原点偏移，tone 只在
  [note_on_sample, note_off_sample) 合成，前导与 release 之后为静音+噪声；写盘后回读核验实际整数24往返。
- 端到端家族通道只调用共享入口 ppa.analyze_samples(left, right, rate, note, timing=...)：timing 必填、
  coordinate=note_on_relative、evidence_role=synthetic_fixture，样本界 = note_on_sample + llround(rel*rate)
  （半远离零），绝不 int(float*rate) 截断。本执行器独立复核 timing 原样保留、逐窗
  bounds_s/start_sample/stop_sample/samples 与注册整数样本界一致、window_failures 恰为 status!=ok 的窗口、
  ok 窗口不越 release/文件边界，并独立复核频率/编号/B/独立留出/充分性/跨窗展开预算。
- 真值只由本文件内的独立合成公式产生，只在观测完成后核验，从不传入观测器、门禁或 analyze_samples。
- 条件域（AM / 弱边界）：只有“静态条件认证且全部独立义务通过”或“显式弃权（拒绝且理由非空）”是合法结果；
  其它 claim 一律记违例；AM carrier 输出不得进入 B。无 diagnostic 非门禁用例、无全局通过率、无阈值放宽。
- 边界负例：release 越界（W2 stop>note_off 且仍在帧内）保留 W1、W2 逐窗失败；frames 越界保留 W2 窗口级失败；
  note_off_sample>frames 的非法事件绑定必须整体拒绝，不得裁剪/伪造 note_off。
- 角色内跨用例门禁（复用冻结函数，不另建第二评估器）：repeat_group 经 validation-eval.py:repeat_quality
  核验重复稳定性（f1 展开<=1.0 cent、B 相对展开<=0.1）；comparison_pair 经 validation-eval.py:compare_analyses
  核验归一化可比量，并逐项落实登记的基准/候选/非基准数量；单弦策略只由共享比较器判断，多弦 fallback 7/5/1 不变。
- 方法资格包含观测、坐标、静态族、重复/比较和封印绑定的六态评估器回归。
  qualified 仅覆盖本登记合成域；参考原点、真实采集及正式验收属于后续独立放行门禁，
  不是方法资格的前置条件，避免“资格等采集、采集等资格”的循环依赖。
- 静态检查接受严格布尔 false 的角色授权；实际角色仍在创建输出与加载测量模块之前独立拒绝未授权执行。
  批准后仍需外部 --seal 精确绑定本注册与五个源码的 sha256；封印对应一轮完整角色，执行即消费
  （封印旁 <seal>.consumed 独占标记），失败/中断全部保留后停止；无子集/重试/调参/替换路径。
- 旧登记与已消费结果只供归档复核；现行执行要求完整比较输出义务，不提供旧字段缺省兼容路径。

用法：
  python3 meter-qualification.py --registration <registration.json> --check-registration
  python3 meter-qualification.py --registration <registration.json> --out <全新目录> --role development
  python3 meter-qualification.py --registration <registration.json> --out <全新目录> --role qualification --seal <封印.json>
"""

import argparse
import hashlib
import importlib.util
import json
import math
import platform
import subprocess
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

SCHEMA = "devpiano-task39-2-method-qualification-noteon-v3"
REGISTRATION_STATUS = "complete_finite_registration_not_v3_acceptance_protocol"
SEAL_ROLE = "method_qualification_noteon_v3"
TIMING_COORDINATE = "note_on_relative"
EVIDENCE_ROLE = "synthetic_fixture"
STATUS_SINGLE, STATUS_RESOLVED, STATUS_AMBIGUOUS = "single_component_adequate", "resolved_components", "ambiguous"
STATUSES = (STATUS_SINGLE, STATUS_RESOLVED, STATUS_AMBIGUOUS)
CLASS_SINGLE, CLASS_RESOLVED, CLASS_AMBIGUOUS, CLASS_NONSTATIONARY = "single", "resolved", "ambiguous", "nonstationary"
WINDOW_NAMES = ("W1", "W2")
DEFAULT_HALF_WIDTH_HZ = 3.0
ADMISSION_EXPECTATIONS = ("admitted", "rejected", "conditional", "refused")
BOUNDARY_KINDS = ("release_boundary", "frames_boundary", "invalid_timing_refused")
REQUIRED_TIMING_KEYS = ("coordinate", "sample_rate", "frames", "note_on_sample", "note_off_sample", "evidence_role")
REQUIRED_WINDOW_KEYS = ("bounds_s", "start_sample", "stop_sample", "samples", "coordinate", "evidence_role")
REQUIRED_REGISTRATION_KEYS = ("schema", "date", "status", "purpose", "role_semantics", "timing_contract", "generator",
                              "assessment", "candidates", "coverage_requirements", "execution", "stop_policy",
                              "complete_plan_gates", "cases", "regression_controls", "limits")
REQUIRED_STOP_CLAUSES = ("approval_gates_execution", "seal_binds_registration_and_sources",
                         "seal_consumed_by_one_complete_role", "all_failures_retained_then_stop",
                         "no_subset_retry_tuning_replacement", "development_never_qualification",
                         "prior_verdicts_and_archives_unchanged", "no_diagnostic_waiver")
REQUIRED_ENFORCED_CLAUSES = tuple(clause for clause in REQUIRED_STOP_CLAUSES if clause != "prior_verdicts_and_archives_unchanged")
SEALED_SOURCES = ("meter-qualification.py", "pilot-partial-analysis.py", "partial-observer.py",
                  "validation-eval.py", "validation-eval-tests.py")
CONTROL_IDS = ("q34-unresolved_doublet-44100", "q35-unresolved_doublet-48000",
               "q38-unresolved_doublet-44100", "q39-unresolved_doublet-48000")
PAIR_OUTPUT_FIELDS = ("base_partial", "comparable_partials", "nonbase_count")


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        while block := stream.read(1 << 20):
            digest.update(block)
    return digest.hexdigest()


def load_module(path, name):
    path = Path(path)
    if not path.is_file():
        raise SystemExit(f"模块文件不存在: {path}")
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise SystemExit(f"无法加载模块规格: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def nominal(note):
    return 440.0 * 2.0 ** ((note - 69) / 12.0)


def finite(value):
    return (isinstance(value, (int, float, np.integer, np.floating))
            and not isinstance(value, bool) and math.isfinite(float(value)))


def json_ready(value):
    """严格转换模块返回值为 JSON 结构：numpy → 原生；非有限浮点或未知类型显式报错（不静默改写）。"""
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"模块返回值含非有限浮点: {number!r}")
        return number
    if isinstance(value, np.ndarray):
        return json_ready(value.tolist())
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    raise ValueError(f"模块返回值含未知类型: {type(value).__name__}")


def llround(value):
    """半远离零整数取整（用于相对秒 → 样本界）；非负输入等价 floor(x+0.5)。"""
    return int(math.floor(float(value) + 0.5))


def tolerance_hz(hz, tolerances, kind):
    """single 沿用 max(0.005 Hz, 0.05 cents-in-Hz)；resolved 分量用 max(0.01 Hz, 1 cent)。"""
    if kind == "single":
        return max(float(tolerances["single_floor_hz"]), hz * (2.0 ** (float(tolerances["single_cents"]) / 1200.0) - 1.0))
    return max(float(tolerances["component_floor_hz"]), hz * (2.0 ** (float(tolerances["component_cents"]) / 1200.0) - 1.0))


def describe(values):
    if not values:
        return {"count": 0, "max_abs_cents": None, "rms_cents": None, "median_cents": None, "p90_cents": None}
    absolute = np.abs(np.array(values, dtype=np.float64))
    ordered = np.sort(absolute)
    return {"count": int(absolute.size), "max_abs_cents": float(absolute.max()),
            "rms_cents": float(np.sqrt(np.mean(absolute ** 2))), "median_cents": float(np.median(ordered)),
            "p90_cents": float(ordered[min(int(round(0.9 * (ordered.size - 1))), ordered.size - 1)])}


def merged_case(case, defaults):
    return {**dict(defaults), **dict(case)}


def load_registration(path):
    try:
        registration = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"registration 读取失败: {error}")
    for key in REQUIRED_REGISTRATION_KEYS:
        if key not in registration:
            raise SystemExit(f"registration 缺少字段: {key}")
    if registration["schema"] != SCHEMA:
        raise SystemExit(f"registration schema 不匹配: {registration['schema']!r} != {SCHEMA!r}"
                         "（旧 v3/v1 注册没有兼容路径：旧已消费复现留在证据归档）")
    if registration["status"] != REGISTRATION_STATUS:
        raise SystemExit("registration 状态必须是 " + REGISTRATION_STATUS)
    return registration


# --------------------------------------------------------------------------- 几何真值

def half_width_of(case):
    return float(case.get("probe_half_width_hz", DEFAULT_HALF_WIDTH_HZ))


def component_frequency(case, number, cents, hz_offset):
    """独立实现的频率模型：f = n f1 2^(cents/1200) sqrt((1+B n^2)/(1+B)) + hz_offset。"""
    first = nominal(case["note"]) + float(case.get("f1_offset_hz", 0.0))
    stiffness = float(case["b"])
    return first * number * math.sqrt((1.0 + stiffness * number * number) / (1.0 + stiffness)) * 2.0 ** (cents / 1200.0) + hz_offset


def enumerate_components(case):
    """枚举真值分量（弦 + 附加模态），并给出漂移/调频下各分量占据的频段。"""
    ceiling = min(20000.0, 0.98 * float(case["rate"]) / 2.0)
    modulation = case.get("modulation")
    shared_phase = case.get("string_phase_mode") == "shared"
    skipped = {int(value) for value in case.get("skip_partials") or []}
    components = []
    for number in range(1, int(case.get("partials", 12)) + 1):
        if number in skipped:
            continue
        shift = (case.get("partial_offsets") or {}).get(str(number)) or {}
        base_amp = 0.05 / number ** 0.8 * 10.0 ** ((case.get("amp_overrides") or {}).get(str(number), 0.0) / 20.0)
        entries = [("string", index, string) for index, string in enumerate(case.get("strings") or [{}])]
        entries += [("mode", index, {"hz": float(mode["offset_hz"]), "amp_db": mode["amp_db"], "anchor": 1.1 + 0.37 * index})
                    for index, mode in enumerate(case.get("extra_modes") or []) if int(mode["near_partial"]) == number]
        for kind, position, item in entries:
            hz = component_frequency(case, number, float(item.get("cents", 0.0)) + float(shift.get("cents", 0.0)),
                                     float(item.get("hz", 0.0)) + float(shift.get("hz", 0.0)))
            if hz >= ceiling:
                continue
            phase = (float(case.get("phase0", 0.0)) + 0.41 * number + float(item.get("anchor", 0.0))
                     + (0.63 * position if not shared_phase and kind == "string" else 0.0)
                     + math.radians(float(item.get("phase_deg", 0.0))))
            span = 0.0
            if modulation:  # 占据频段：令探针界覆盖整簇/整条漂移线
                key = "span_cents" if modulation["model"] == "drift_linear" else "depth_cents"
                span = hz * (2.0 ** (float(modulation[key]) / 1200.0) - 1.0)
            half = span / 2.0 if modulation and modulation["model"] == "drift_linear" else span
            components.append({"region": number, "kind": kind, "index": position, "hz": hz,
                               "amp": base_amp * 10.0 ** (float(item.get("amp_db", 0.0)) / 20.0), "phase_rad": phase,
                               "span_low_hz": hz - half, "span_high_hz": hz + half, "nonstationary": bool(modulation)})
    return components


def build_regions(components, registration):
    """按注册声明的几何规则定类：非平稳 > 单分量 > 可分辨（分离与电平跨度达标）> 模糊。"""
    rule = registration["assessment"]["region_classification"]
    grouped = {}
    for component in components:
        grouped.setdefault(component["region"], []).append(component)
    regions = []
    for index in sorted(grouped):
        group = grouped[index]
        amp_max = max(item["amp"] for item in group)
        levels = [20.0 * math.log10(item["amp"] / amp_max) for item in group]
        separations = [abs(a["hz"] - b["hz"]) for position, a in enumerate(group) for b in group[position + 1:]]
        if any(item["nonstationary"] for item in group):
            klass = CLASS_NONSTATIONARY
        elif len(group) == 1:
            klass = CLASS_SINGLE
        elif min(separations) >= float(rule["resolvable_separation_hz"]) and max(levels) - min(levels) <= float(rule["max_level_span_db"]):
            klass = CLASS_RESOLVED
        else:
            klass = CLASS_AMBIGUOUS
        regions.append({"index": index, "class": klass, "components": group,
                        "min_separation_hz": min(separations) if separations else None,
                        "span_low_hz": min(item["span_low_hz"] for item in group),
                        "span_high_hz": max(item["span_high_hz"] for item in group)})
    return regions


def case_class(components, regions):
    if not components:
        return "negative"
    for klass, name in ((CLASS_NONSTATIONARY, "nonstationary"), (CLASS_AMBIGUOUS, "ambiguous"), (CLASS_RESOLVED, "resolvable")):
        if any(region["class"] == klass for region in regions):
            return name
    return "positive"


def family_lines_of(case):
    return {component["region"]: component["hz"] for component in enumerate_components(case)
            if component["kind"] == "string" and component["index"] == 0}


# --------------------------------------------------------------------------- 注册校验

def expected_binding(case, registration):
    """由注册整数样本固定推定期望事件绑定与逐窗整数样本界（llround 半远离零）。"""
    rate = int(case["rate"])
    window_bounds = {}
    for name, (low, high) in registration["generator"]["windows"].items():
        window_bounds[name] = {"relative": [float(low), float(high)],
                               "start": int(case["note_on_sample"]) + llround(float(low) * rate),
                               "stop": int(case["note_on_sample"]) + llround(float(high) * rate)}
    return {"rate": rate, "note_on_sample": int(case["note_on_sample"]), "note_off_sample": int(case["note_off_sample"]),
            "frames": int(case["frames"]),
            "note_off_expected": int(case["note_on_sample"]) + llround(float(case["note_off_seconds_after_note_on"]) * rate),
            "frames_expected": int(case["note_on_sample"]) + llround(float(case["frames_seconds_after_note_on"]) * rate),
            "windows": window_bounds}


def observer_window_refusal_expected(case, name):
    """窗级拒绝必须来自登记的帧末负例，不能由捕获异常推定。"""
    boundary = case.get("boundary") or {}
    return (case.get("admission_expectation") == "rejected"
            and boundary.get("kind") == "frames_boundary"
            and boundary.get("expected_stage") == "spectrum"
            and (boundary.get("expected_windows") or {}).get(name) == "not_ok")


def check_case_design(case, registration):
    """用例几何/字段/事件绑定自洽：声明类别=几何推导；探针界覆盖整簇；整数样本界与 llround 一致。"""
    components = enumerate_components(case)
    regions = build_regions(components, registration)
    if case_class(components, regions) != case["expected_class"]:
        raise SystemExit(f"{case['id']}: 声明类别 {case['expected_class']!r} 与几何推导不一致")
    if int(case["rate"]) not in [int(rate) for rate in registration["generator"]["rates_hz"]]:
        raise SystemExit(f"{case['id']}: rate 未在 registration 声明")
    obligation = case.get("obligation", "gating")
    if obligation not in ("gating", "control"):
        raise SystemExit(f"{case['id']}: obligation 非法（无 diagnostic 非门禁义务）: {obligation!r}")
    expectation = case.get("admission_expectation", "admitted")
    if expectation not in ADMISSION_EXPECTATIONS:
        raise SystemExit(f"{case['id']}: admission_expectation 非法: {expectation!r}")
    windows = list(case.get("windows") or [])
    if len(windows) != len(set(windows)):
        raise SystemExit(f"{case['id']}: 观测窗不得重复")
    for name in windows:
        if name not in registration["generator"]["windows"]:
            raise SystemExit(f"{case['id']}: 未声明的观测窗 {name!r}")
    boundary = case.get("boundary")
    if expectation == "refused":
        if boundary is None or boundary.get("kind") != "invalid_timing_refused" or windows:
            raise SystemExit(f"{case['id']}: refused 期望必须是 invalid_timing_refused 边界且不声明观测窗")
    elif not windows:
        raise SystemExit(f"{case['id']}: 非 refused 用例必须声明至少一个观测窗")
    conditional = case.get("conditional")
    if (expectation == "conditional") != bool(conditional):
        raise SystemExit(f"{case['id']}: conditional 期望与 conditional 域声明不一致")
    if conditional:
        if case["expected_class"] != "positive" or not str(conditional.get("domain") or "").strip():
            raise SystemExit(f"{case['id']}: conditional 用例必须是 positive 且声明 domain")
        if not finite(conditional.get("band_hz")) or float(conditional["band_hz"]) < 0.0:
            raise SystemExit(f"{case['id']}: conditional.band_hz 非法")
    half_width = half_width_of(case)
    spans = sorted((region["span_low_hz"], region["span_high_hz"], region["index"]) for region in regions)
    for low, high, index in spans:
        if high - low > half_width:
            raise SystemExit(f"{case['id']}: 分区 {index} 跨度 {high - low:.6g} Hz 超过 half_width={half_width:.6g}")
    for (low_a, high_a, index_a), (low_b, _high_b, index_b) in zip(spans, spans[1:]):
        if low_b - high_a < 2.0 * half_width:
            raise SystemExit(f"{case['id']}: 分区 {index_a}/{index_b} 间隔 {low_b - high_a:.6g} Hz 小于 2*half_width")
    binding = expected_binding(case, registration)
    rate = binding["rate"]
    if binding["note_on_sample"] <= 0:
        raise SystemExit(f"{case['id']}: note_on_sample 必须为正（非零 MIDI 原点偏移）")
    if binding["note_off_sample"] != binding["note_off_expected"]:
        raise SystemExit(f"{case['id']}: note_off_sample 与 llround(note_off_seconds*rate) 不一致")
    if binding["frames"] != binding["frames_expected"]:
        raise SystemExit(f"{case['id']}: frames 与 llround(frames_seconds*rate) 不一致")
    if boundary and boundary.get("kind") == "invalid_timing_refused":
        if binding["note_off_sample"] <= binding["frames"]:
            raise SystemExit(f"{case['id']}: refused 边界要求 note_off_sample > frames（非法事件绑定，整体拒绝）")
    else:
        if not (binding["note_on_sample"] < binding["note_off_sample"] <= binding["frames"]):
            raise SystemExit(f"{case['id']}: 事件绑定必须满足 0<note_on<note_off<=frames")
    if boundary and boundary.get("kind") != "invalid_timing_refused":
        w1, w2 = binding["windows"]["W1"], binding["windows"]["W2"]
        kind = boundary.get("kind")
        if boundary.get("expected_stage") not in ("bounds", "spectrum"):
            raise SystemExit(f"{case['id']}: 边界用例必须声明 expected_stage")
        if set(boundary.get("expected_windows") or {}) != set(WINDOW_NAMES):
            raise SystemExit(f"{case['id']}: 边界用例必须声明两个窗口的期望状态")
        if boundary["expected_windows"]["W1"] != "ok":
            raise SystemExit(f"{case['id']}: 边界负例必须保留 W1 正常窗口")
        if kind == "release_boundary":
            if w2["stop"] > binding["frames"]:
                raise SystemExit(f"{case['id']}: release_boundary 要求 W2 stop 仍在帧内")
            if not (w1["stop"] <= binding["note_off_sample"] < w2["stop"]):
                raise SystemExit(f"{case['id']}: release_boundary 要求 W1 stop<=note_off<W2 stop")
            if boundary["expected_stage"] != "bounds" or boundary["expected_windows"]["W2"] != "not_ok":
                raise SystemExit(f"{case['id']}: release_boundary 期望 stage=bounds、W2 非 ok")
        elif kind == "frames_boundary":
            if not (w1["stop"] <= binding["frames"] < w2["stop"]):
                raise SystemExit(f"{case['id']}: frames_boundary 要求 W1 stop<=frames<W2 stop")
            if boundary["expected_stage"] != "spectrum" or boundary["expected_windows"]["W2"] != "not_ok":
                raise SystemExit(f"{case['id']}: frames_boundary 期望 stage=spectrum、W2 非 ok")
            if set(windows) != set(WINDOW_NAMES):
                raise SystemExit(f"{case['id']}: frames_boundary 必须保留两个观察器窗口及 W2 输入拒绝")
        else:
            raise SystemExit(f"{case['id']}: 未知边界类型 {kind!r}")
    elif not boundary:
        if binding["note_off_sample"] - binding["note_on_sample"] < llround(4.1 * rate):
            raise SystemExit(f"{case['id']}: 正常用例 note_off 必须不早于 W2 相对终点")
        if binding["frames"] < binding["note_off_sample"]:
            raise SystemExit(f"{case['id']}: 正常用例 frames 必须覆盖 note_off")
    for name in windows:
        window = binding["windows"][name]
        if window["start"] < 0 or window["stop"] <= window["start"]:
            raise SystemExit(f"{case['id']}: 观察器窗口 {name} 样本界非法")
        if (window["stop"] > binding["frames"]) != observer_window_refusal_expected(case, name):
            raise SystemExit(f"{case['id']}: 观察器窗口 {name} 的帧末拒绝声明与样本界不一致")
    return binding


def check_generator(registration):
    generator = registration["generator"]
    if [int(rate) for rate in generator["rates_hz"]] != [44100, 48000]:
        raise SystemExit("generator.rates_hz 必须精确为 [44100, 48000]")
    windows = generator["windows"]
    if windows.get("W1") != [0.08, 3.8] or windows.get("W2") != [0.5, 4.1]:
        raise SystemExit("generator.windows 必须是合同 W1=[0.08,3.8], W2=[0.5,4.1]（相对 NoteOn）")
    if not finite(generator.get("duration_s")):
        raise SystemExit("generator.duration_s 缺失")
    defaults = generator.get("case_defaults")
    if not isinstance(defaults, dict):
        raise SystemExit("generator.case_defaults 缺失")
    for key in ("obligation", "admission_expectation", "strings", "extra_modes", "skip_partials", "partial_offsets",
                "amp_overrides", "envelope", "modulation", "am", "conditional", "boundary", "noise_sigma", "level",
                "partials", "windows", "required_partials", "forbidden_partials", "string_phase_mode",
                "probe_half_width_hz", "f1_offset_hz", "phase0", "note_off_seconds_after_note_on",
                "frames_seconds_after_note_on"):
        if key not in defaults:
            raise SystemExit(f"generator.case_defaults 缺字段: {key}")


def check_timing_contract(registration):
    contract = registration["timing_contract"]
    if contract.get("coordinate") != TIMING_COORDINATE:
        raise SystemExit("timing_contract.coordinate 必须是 note_on_relative（无默认原点/别名）")
    if contract.get("evidence_role") != EVIDENCE_ROLE:
        raise SystemExit(f"timing_contract.evidence_role 必须是 {EVIDENCE_ROLE}")
    if list(contract.get("window_record_keys") or []) != list(REQUIRED_WINDOW_KEYS):
        raise SystemExit("timing_contract.window_record_keys 与执行器要求的窗口字段不一致")
    for key in ("required_keyword", "sample_mapping", "event_binding_constraints", "window_failure_semantics",
                "timing_retention", "load_timing_report"):
        if not isinstance(contract.get(key), str) or not contract[key].strip():
            raise SystemExit(f"timing_contract 缺字段: {key}")


def check_coverage_requirements(registration, groups):
    coverage = registration["coverage_requirements"]
    if list(coverage.get("roles") or []) != ["development", "qualification"]:
        raise SystemExit("coverage_requirements.roles 必须精确为 [development, qualification]")
    minimum = coverage.get("minimum_required_admission_cases_per_role")
    if not isinstance(minimum, int) or minimum < 1:
        raise SystemExit("coverage_requirements.minimum_required_admission_cases_per_role 非法")
    for role in ("development", "qualification"):
        cases = groups[role]
        missing_classes = set(coverage["required_expected_classes_per_role"]) - {case["expected_class"] for case in cases}
        if missing_classes:
            raise SystemExit(f"{role}: expected_class 覆盖不足，缺少 {sorted(missing_classes)}")
        missing_rates = {int(rate) for rate in coverage["required_rates_per_role"]} - {int(case["rate"]) for case in cases}
        if missing_rates:
            raise SystemExit(f"{role}: rate 覆盖不足，缺少 {sorted(missing_rates)}")
        admitted = [case for case in cases if case["admission_expectation"] == "admitted"]
        if len(admitted) < minimum:
            raise SystemExit(f"{role}: required-admission 用例数 {len(admitted)} 小于下限 {minimum}")
        if any(case["expected_class"] != "positive" for case in admitted):
            raise SystemExit(f"{role}: required-admission 用例必须都是 positive")
        if len([case for case in cases if case["admission_expectation"] == "conditional"]) < int(coverage["minimum_conditional_cases_per_role"]):
            raise SystemExit(f"{role}: conditional 用例数不足")
        missing_boundaries = set(coverage["required_boundary_kinds_per_role"]) - {case["boundary"]["kind"] for case in cases if case.get("boundary")}
        if missing_boundaries:
            raise SystemExit(f"{role}: 边界用例覆盖不足，缺少 {sorted(missing_boundaries)}")
        missing_windows = set(coverage["required_observer_window_names"]) - {name for case in cases for name in case.get("windows") or []}
        if missing_windows:
            raise SystemExit(f"{role}: 观测窗覆盖不足，缺少 {sorted(missing_windows)}")


def comparison_expectations(registration):
    """预期只来自登记，不在 runner 重新计算候选策略。"""
    review = registration.get("prospective_review")
    entries = review.get("policy_expectations") if isinstance(review, dict) else None
    if not isinstance(entries, list) or not entries:
        raise SystemExit("缺少完整的正向比较输出义务")
    result = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise SystemExit("比较输出义务必须是对象")
        role, pair = entry.get("role"), entry.get("pair")
        if role not in ("development", "qualification") or not isinstance(pair, str) or not pair.strip():
            raise SystemExit("比较输出义务的 role/pair 非法")
        key = (role, pair)
        if key in result:
            raise SystemExit(f"{role}/{pair}: 比较输出义务重复")
        members = entry.get("members")
        if (not isinstance(members, list) or len(members) != 2
                or any(not isinstance(value, str) or not value.strip() for value in members)
                or members[0] == members[1]):
            raise SystemExit(f"{role}/{pair}: 必须按 a/b 顺序绑定两个不同成员")
        fields = ("note", "rate", *(f"expected_{name}" for name in PAIR_OUTPUT_FIELDS))
        if any(type(entry.get(name)) is not int or entry[name] <= 0 for name in fields):
            raise SystemExit(f"{role}/{pair}: 键号/采样率/预期数量必须是正整数，不能是布尔值")
        if (entry.get("expected_state") != "comparison_passed"
                or entry["expected_nonbase_count"] < 2
                or entry["expected_comparable_partials"] != entry["expected_nonbase_count"] + 1):
            raise SystemExit(f"{role}/{pair}: 只支持含基准及至少两个非基准的正向比较")
        result[key] = entry
    return result


def check_cross_case_groups(registration, groups):
    """角色内跨用例义务的注册校验：重复组与可比对必须成对、同角色、同配方且为准入期望。"""
    coverage = registration["coverage_requirements"]
    expectations = comparison_expectations(registration)
    matched_expectations = set()
    for role in ("development", "qualification"):
        cases = groups[role]
        repeats, pairs = {}, {}
        for case in cases:
            spec = case.get("repeat_group")
            if spec is not None:
                if (not isinstance(spec, dict) or not str(spec.get("group") or "").strip()
                        or not isinstance(spec.get("repeat"), int) or isinstance(spec.get("repeat"), bool)):
                    raise SystemExit(f"{case['id']}: repeat_group 声明非法")
                repeats.setdefault(str(spec["group"]), []).append(case)
            spec = case.get("comparison_pair")
            if spec is not None:
                if (not isinstance(spec, dict) or not str(spec.get("pair") or "").strip()
                        or spec.get("producer") not in ("a", "b")):
                    raise SystemExit(f"{case['id']}: comparison_pair 声明非法（producer 必须是 a/b）")
                pairs.setdefault(str(spec["pair"]), []).append(case)
        for name, members in repeats.items():
            if len(members) != 2 or len({member["repeat_group"]["repeat"] for member in members}) != 2:
                raise SystemExit(f"{role}/{name}: 重复组必须恰好两名成员且 repeat 编号互异")
            if len({int(member["seed"]) for member in members}) != 2:
                raise SystemExit(f"{role}/{name}: 重复组成员种子必须互异（仅噪声实现可不同）")
            if any(member["admission_expectation"] != "admitted" for member in members):
                raise SystemExit(f"{role}/{name}: 重复组必须是 admitted 期望")
            stripped = [{key: value for key, value in member.items()
                         if key not in ("id", "seed", "repeat_group")} for member in members]
            if stripped[0] != stripped[1]:
                raise SystemExit(f"{role}/{name}: 重复组配方必须一致（除 seed/id/repeat_group）")
        for name, members in pairs.items():
            if len(members) != 2 or {member["comparison_pair"]["producer"] for member in members} != {"a", "b"}:
                raise SystemExit(f"{role}/{name}: 可比对必须恰好一名 a 与一名 b 成员")
            if any(member["admission_expectation"] != "admitted" for member in members):
                raise SystemExit(f"{role}/{name}: 可比对必须是 admitted 期望")
            stripped = [{key: value for key, value in member.items()
                         if key not in ("id", "seed", "comparison_pair", "level")} for member in members]
            if stripped[0] != stripped[1]:
                raise SystemExit(f"{role}/{name}: 可比对配方必须一致（仅允许 seed/level/身份不同）")
            expectation = expectations.get((role, name))
            by_producer = {member["comparison_pair"]["producer"]: member for member in members}
            if expectation is None:
                raise SystemExit(f"{role}/{name}: 缺少比较输出义务")
            if (expectation["members"] != [by_producer["a"]["id"], by_producer["b"]["id"]]
                    or expectation["note"] != members[0]["note"] or expectation["rate"] != members[0]["rate"]):
                raise SystemExit(f"{role}/{name}: 比较输出义务与成员/键号/采样率不匹配")
            matched_expectations.add((role, name))
        if len(repeats) < int(coverage["minimum_repeat_groups_per_role"]):
            raise SystemExit(f"{role}: 重复组数量低于下限")
        if len(pairs) < int(coverage["minimum_comparison_pairs_per_role"]):
            raise SystemExit(f"{role}: 可比对数量低于下限")
    for case in groups["control"]:
        if case.get("repeat_group") is not None or case.get("comparison_pair") is not None:
            raise SystemExit(f"{case['id']}: 回归对照不得携带重复组/可比对声明")
    if matched_expectations != set(expectations):
        raise SystemExit("比较输出义务包含未登记的 role/pair")
    assessment = registration["assessment"]
    for key in ("repeat_obligation", "comparison"):
        block = assessment.get(key)
        if not isinstance(block, dict) or not str(block.get("gate_function") or "").strip():
            raise SystemExit(f"assessment.{key} 缺失或未声明复用的门禁函数")
    mask = assessment["comparison"].get("existing_mask_unchanged") or {}
    if (int(mask.get("midi_below_72", -1)), int(mask.get("midi_72_through_95", -1)),
            int(mask.get("midi_96_and_above", -1))) != (7, 5, 1):
        raise SystemExit("assessment.comparison.existing_mask_unchanged 必须保留短契约掩码 7/5/1")


def check_complete_plan_gates(registration):
    """方法资格与后续真实验收分离；全部方法门禁必须在本登记内闭合。"""
    block = registration["complete_plan_gates"]
    required = {entry.get("gate"): entry for entry in block.get("required") or [] if isinstance(entry, dict)}
    names = {"repeat_quality", "compare_analyses", "six_state_regression"}
    if set(required) != names or any(required[name].get("covered_by_registration") is not True
                                     for name in names):
        raise SystemExit("complete_plan_gates 必须覆盖重复、归一化比较与六态回归，不得留下未完成方法门禁")
    if set(block.get("downstream_not_method_prerequisites") or []) != {
            "reference_origin_authentication", "real_capture_and_formal_evaluation"}:
        raise SystemExit("参考认证/真实采集必须与方法资格门禁分离")
    regression = registration["execution"].get("evaluator_regression") or {}
    if (regression.get("required") is not True
            or regression.get("script") != "pilot/tools/validation-eval-tests.py"
            or regression.get("timeout_seconds") != 120):
        raise SystemExit("缺少有界、必需的封印评估器回归")


def check_execution(registration):
    execution = registration["execution"]
    if not isinstance(execution.get("approval"), bool):
        raise SystemExit("execution.approval 必须是布尔")
    development = execution.get("development") or {}
    if not isinstance(development.get("authorized"), bool) or development.get("repeatable") is not True \
            or development.get("evidence_role") != EVIDENCE_ROLE:
        raise SystemExit("execution.development 必须声明布尔授权、可重复且 evidence_role=" + EVIDENCE_ROLE)
    qualification = execution.get("qualification") or {}
    if qualification.get("seal_required") is not True:
        raise SystemExit("execution.qualification.seal_required 必须为 true")
    for key in ("seal_convention", "consumption", "on_failure"):
        if not isinstance(qualification.get(key), str) or not qualification[key].strip():
            raise SystemExit(f"execution.qualification 缺字段: {key}")
    if not isinstance(qualification.get("requires"), list) or not qualification["requires"]:
        raise SystemExit("execution.qualification.requires 缺失")


def check_stop_policy(registration):
    policy = registration["stop_policy"]
    clauses = policy.get("clauses")
    if not isinstance(clauses, dict) or set(clauses) != set(REQUIRED_STOP_CLAUSES):
        raise SystemExit(f"stop_policy.clauses 必须精确覆盖 {sorted(REQUIRED_STOP_CLAUSES)}")
    if any(not isinstance(text, str) or not text.strip() for text in clauses.values()):
        raise SystemExit("stop_policy.clauses 存在空条款")
    enforced = set(policy.get("enforced_by_runner") or [])
    if not set(REQUIRED_ENFORCED_CLAUSES) <= enforced <= set(clauses):
        raise SystemExit("stop_policy.enforced_by_runner 必须包含执行器机械落实的条款且不超出 clauses")


def validate_registration(registration):
    check_generator(registration)
    check_timing_contract(registration)
    check_stop_policy(registration)
    check_execution(registration)
    check_complete_plan_gates(registration)
    defaults = registration["generator"]["case_defaults"]
    groups = {"development": [merged_case(case, defaults) for case in registration["cases"]["development"]],
              "qualification": [merged_case(case, defaults) for case in registration["cases"]["qualification"]],
              "control": [merged_case(case, defaults) for case in registration["regression_controls"]]}
    seen = {}
    for cases in groups.values():
        for case in cases:
            if not case.get("id") or case["id"] in seen:
                raise SystemExit(f"用例 id 缺失或重复: {case.get('id')!r}")
            if not finite(case.get("seed")):
                raise SystemExit(f"{case['id']}: seed 缺失")
            seen[case["id"]] = int(case["seed"])
    if len(set(seen.values())) != len(seen):
        raise SystemExit("seed 在注册文件内不唯一")
    development, qualification = groups["development"], groups["qualification"]
    if {case["seed"] for case in development} & {case["seed"] for case in qualification}:
        raise SystemExit("development/qualification 种子不互斥")
    if ({(case["kind"], case["note"], case["rate"]) for case in development}
            & {(case["kind"], case["note"], case["rate"]) for case in qualification}):
        raise SystemExit("development/qualification 配方参数（kind,note,rate）不互斥")
    if {case["id"] for case in groups["control"]} != set(CONTROL_IDS):
        raise SystemExit("regression_controls 必须精确为 q34/q35/q38/q39")
    for case in development + qualification + groups["control"]:
        check_case_design(case, registration)
    for case in groups["control"]:
        if case["obligation"] != "control" or case["admission_expectation"] != "rejected" \
                or case["expected_class"] != "ambiguous" or not case.get("purpose"):
            raise SystemExit(f"{case['id']}: 回归对照字段非法（control/rejected/ambiguous/purpose）")
    check_coverage_requirements(registration, groups)
    check_cross_case_groups(registration, groups)
    if not isinstance(registration["limits"], list) or not registration["limits"]:
        raise SystemExit("registration.limits 缺失")
    return groups


# --------------------------------------------------------------------------- 合成与 PCM

def phase_argument(hz, time, modulation, duration):
    """漂移/调频按解析积分给出连续相位（time 为 NoteOn 相对时间）。"""
    if not modulation:
        return 2.0 * math.pi * hz * time
    if modulation["model"] == "drift_linear":
        span = hz * (2.0 ** (float(modulation["span_cents"]) / 1200.0) - 1.0)
        return 2.0 * math.pi * (hz * time + (span / duration) * (time * time / 2.0 - duration * time / 2.0))
    depth = hz * (2.0 ** (float(modulation["depth_cents"]) / 1200.0) - 1.0)
    rate = float(modulation["freq_hz"])
    return 2.0 * math.pi * (hz * time - (depth / (2.0 * math.pi * rate)) * np.cos(2.0 * math.pi * rate * time))


def synthesize(case, registration):
    """NoteOn 相对时间轴上的合成：tone 只在 [note_on, note_off) 内，前后为静音+噪声。"""
    frames, on, off, rate = int(case["frames"]), int(case["note_on_sample"]), int(case["note_off_sample"]), int(case["rate"])
    index = np.arange(frames)
    time = (index - on) / rate
    active = (index >= on) & (index < off)
    envelope, modulation, am = case.get("envelope") or {"model": "none"}, case.get("modulation"), case.get("am")
    duration = float(registration["generator"]["duration_s"])
    signal = np.zeros(frames, dtype=np.float64)
    for component in enumerate_components(case):
        relative = np.maximum(time, 0.0)
        if envelope["model"] == "exponential":
            env = np.exp(-relative / float(envelope["tau_s"])) if component["region"] >= int(envelope["from_partial"]) else np.ones_like(time)
        elif envelope["model"] == "two_stage":
            weight = float(envelope["fast_weight"])
            env = weight * np.exp(-relative / float(envelope["fast_tau_s"])) + (1.0 - weight) * np.exp(-relative / float(envelope["slow_tau_s"]))
        else:
            env = np.ones_like(time)
        if am:
            env = env * (1.0 + float(am["depth"]) * np.cos(2.0 * math.pi * float(am["freq_hz"]) * relative))
        signal += np.where(active, component["amp"] * env * np.cos(phase_argument(component["hz"], time, modulation, duration)
                                                                     + component["phase_rad"]), 0.0)
    rng = np.random.default_rng(int(case["seed"]))
    sigma, level = float(case.get("noise_sigma", 1e-5)), float(case.get("level", 1.0))
    left = (signal + rng.normal(0.0, sigma, frames)) * level
    right = (signal + rng.normal(0.0, sigma, frames)) * level
    if not (np.isfinite(left).all() and np.isfinite(right).all()) or max(float(np.max(np.abs(left))), float(np.max(np.abs(right)))) >= 0.95:
        raise ValueError("fixture 非有限或存在削波风险；不静默归一化")
    return left, right


def write_pcm(path, rate, samples):
    values = np.rint(samples.reshape(-1) * 8388608.0).astype(np.int32)
    packed = np.stack([(values >> shift) & 255 for shift in (0, 8, 16)], axis=1).astype(np.uint8)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(3)
        handle.setframerate(rate)
        handle.writeframes(packed.tobytes())


def read_pcm(path):
    """本文件内的独立 24-bit 双声道读取；与冻结读取器同编码约定。"""
    with wave.open(str(path), "rb") as handle:
        if handle.getnchannels() != 2 or handle.getsampwidth() != 3:
            raise ValueError(f"意外的 PCM 格式: {handle.getnchannels()}ch/{handle.getsampwidth() * 8}bit")
        rate, frames, raw = handle.getframerate(), handle.getnframes(), handle.readframes(handle.getnframes())
    data = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
    value = (data[:, 0] | (data[:, 1] << 8) | (data[:, 2] << 16)).astype(np.int64)
    value = np.where(value >= (1 << 23), value - (1 << 24), value).astype(np.float64).reshape(-1, 2) / 8388608.0
    return rate, value[:, 0].copy(), value[:, 1].copy()


def truth_payload(case, components, regions):
    return {"class": case_class(components, regions), "f1_hz": nominal(case["note"]) + float(case.get("f1_offset_hz", 0.0)),
            "b": float(case["b"]),
            "family_lines_hz": {component["region"]: component["hz"] for component in components
                                if component["kind"] == "string" and component["index"] == 0},
            "regions": [{"index": region["index"], "class": region["class"],
                         "lines_hz": [component["hz"] for component in region["components"]],
                         "min_separation_hz": region["min_separation_hz"],
                         "level_span_db": round(20.0 * math.log10(min(c["amp"] for c in region["components"])
                                                                  / max(c["amp"] for c in region["components"])), 3)}
                        for region in regions],
            "role": "post-observation only; never passed to observe_partial / analyze_samples / reference_quality"}


# --------------------------------------------------------------------------- 观测器通道

def spectral_candidates(left, right, rate, start, stop, band, registration):
    """候选只从实际 PCM 的整数样本界 Hann 窗频谱导出（本文件独立实现，不依赖 PPA 内部）。"""
    rule = registration["candidates"]
    start, stop = int(start), int(stop)
    if start < 0 or stop <= start or stop > min(int(left.size), int(right.size)):
        raise ValueError("candidate window exceeds available samples or has invalid bounds")
    if stop - start < 64:
        return []
    hann = np.hanning(stop - start)
    power = np.abs(np.fft.rfft(left[start:stop] * hann)) ** 2 + np.abs(np.fft.rfft(right[start:stop] * hann)) ** 2
    frequency = np.fft.rfftfreq(stop - start, 1.0 / rate)
    ceiling = float(np.max(power))
    if ceiling <= 0.0:
        return []
    relative = power / ceiling
    interior = np.flatnonzero((relative[1:-1] > relative[:-2]) & (relative[1:-1] >= relative[2:])) + 1
    interior = interior[(frequency[interior] >= band[0]) & (frequency[interior] <= band[1])]
    step = float(frequency[1] - frequency[0])
    scored = []
    for index in interior:
        logs = np.log(relative[index - 1:index + 2] + 1e-300)
        denominator = logs[0] - 2.0 * logs[1] + logs[2]
        hz = float(frequency[index] + (0.5 * (logs[0] - logs[2]) / denominator if denominator < 0.0 else 0.0) * step)
        i0, i1 = max(int(np.searchsorted(frequency, hz * 0.97)), 0), max(int(np.searchsorted(frequency, hz * 1.03)), 1)
        keep = np.ones(i1 - i0, dtype=bool)
        keep[max(int(np.searchsorted(frequency, hz * 0.998)) - i0, 0):max(int(np.searchsorted(frequency, hz * 1.002)) - i0, 0)] = False
        floor = float(np.median(power[i0:i1][keep])) if keep.any() else float(np.median(power[i0:i1]))
        if not finite(floor) or floor <= 0.0:
            floor = 1e-300
        scored.append({"hz": hz, "rel": float(relative[index]),
                       "snr_db": 10.0 * math.log10(max(float(power[index]), 1e-300) / max(floor, 1e-300))})
    kept = {round(item["hz"], 6): item for item in scored
            if item["rel"] >= float(rule["rel_power_floor"]) and item["snr_db"] >= float(rule["min_local_snr_db"])}
    for item in sorted(scored, key=lambda entry: -entry["rel"])[:int(rule["force_top"])]:
        kept.setdefault(round(item["hz"], 6), item)
    return sorted(sorted(kept.values(), key=lambda item: -item["rel"])[:int(rule["max_candidates"])], key=lambda item: item["hz"])


def exact_seconds(sample, rate):
    """返回 float 秒值使 int(seconds*rate) == sample（观测器按 int(x*rate) 切窗，必须精确往返）。"""
    base = float(sample) / float(rate)
    for step in (1.0, -1.0):
        candidate = base
        for _ in range(8):
            if int(candidate * rate) == sample:
                return candidate
            candidate = math.nextafter(candidate, math.inf if step > 0 else -math.inf)
    raise ValueError(f"无法为样本 {sample}@{rate} 构造精确秒值")


def extract_claims(output):
    """观测器返回 → 可评估声明：single/resolved 均只读共享 API 的 frequency_hz / interval_hz。"""
    def interval(value):
        if isinstance(value, (list, tuple)) and len(value) == 2 and finite(value[0]) and finite(value[1]) and float(value[0]) < float(value[1]):
            return [float(value[0]), float(value[1])]
        return None
    if output.get("status") == STATUS_SINGLE and finite(output.get("frequency_hz")):
        return [{"kind": "single", "hz": float(output["frequency_hz"]), "interval": interval(output.get("interval_hz"))}]
    claims = []
    if output.get("status") == STATUS_RESOLVED:
        for component in output.get("components") or []:
            if isinstance(component, dict) and finite(component.get("frequency_hz")):
                claims.append({"kind": "component", "hz": float(component["frequency_hz"]),
                               "interval": interval(component.get("interval_hz"))})
    return claims


def match_claim(hz, kind, regions, tolerances):
    """声明 → 容差内最近真值分量；ambiguous 分区按半个真实分离放宽。"""
    best = None
    for region in regions:
        for component in region["components"]:
            tolerance = tolerance_hz(component["hz"], tolerances, kind)
            if region["class"] == CLASS_AMBIGUOUS and region["min_separation_hz"]:
                tolerance = max(tolerance, 0.5 * float(region["min_separation_hz"]))
            distance = abs(hz - component["hz"])
            if distance <= tolerance and (best is None or distance < best[0]):
                best = (distance, region, component, tolerance)
    return best


def conditional_band_match(hz, covering, band_hz, tolerances):
    """条件域：band 内的 claim 记录为条件观测（不构成静态认证），band 外才算错误声明。"""
    best = None
    for region in covering:
        for component in region["components"]:
            limit = band_hz + tolerance_hz(component["hz"], tolerances, "component")
            distance = abs(hz - component["hz"])
            if distance <= limit and (best is None or distance < best[0]):
                best = (distance, region, component, limit)
    return best


def assess_observer_case(case, regions, probes, registration):
    """观测器通道事后评估：分区类别驱动，真值只在事后核验；条件域允许显式弃权。"""
    tolerances = registration["assessment"]["tolerances"]
    half_width = half_width_of(case)
    conditional = case.get("conditional")
    band_hz = float(conditional["band_hz"]) if conditional else 0.0
    violations, matched = [], []
    interval = {"single_claims": 0, "covered": 0, "widths_cents": []}
    for region in regions:
        region.update({"covered": False, "single": False, "resolved": False, "bad": False,
                       "probes": 0, "ambiguous_probes": 0, "nonstatic_probes": 0,
                       "claims": [], "band_claims": [], "diagnostic_components": []})
    for probe_index, probe in enumerate(probes):
        covering = [region for region in regions
                    if probe["center_hz"] + half_width >= region["span_low_hz"]
                    and probe["center_hz"] - half_width <= region["span_high_hz"]]
        for region in covering:
            region["covered"] = True
            region["probes"] += 1
        output = probe["output"]
        status = output.get("status") if isinstance(output, dict) else None
        if probe["observer_error"] is not None:
            violations.append({"kind": "observer_exception", "center_hz": probe["center_hz"], "detail": probe["observer_error"][:300]})
            continue
        if not isinstance(output, dict) or status not in STATUSES:
            violations.append({"kind": "invalid_status", "center_hz": probe["center_hz"], "status": status})
            continue
        if status == STATUS_AMBIGUOUS:
            if output.get("frequency_hz") is not None or output.get("interval_hz") is not None:
                violations.append({"kind": "ambiguous_scalar_claim", "center_hz": probe["center_hz"]})
            else:
                for region in covering:
                    region["ambiguous_probes"] += 1
                    region["nonstatic_probes"] += 1
            continue
        if conditional and status == STATUS_RESOLVED:
            diagnostics = extract_claims(output)
            if (not diagnostics or output.get("frequency_hz") is not None
                    or output.get("interval_hz") is not None):
                violations.append({"kind": "invalid_nonstatic_diagnostic", "center_hz": probe["center_hz"]})
                continue
            for claim in diagnostics:
                found = conditional_band_match(claim["hz"], covering, band_hz, tolerances)
                if found is None:
                    violations.append({"kind": "unmatched_diagnostic_component", "claim_hz": claim["hz"]})
                else:
                    _, region, _, _ = found
                    region["diagnostic_components"].append(claim["hz"])
            for region in covering:
                region["nonstatic_probes"] += 1
            continue
        claims = extract_claims(output)
        if not claims:
            violations.append({"kind": "missing_claim_fields", "status": status, "center_hz": probe["center_hz"]})
            continue
        for claim in claims:
            found = match_claim(claim["hz"], claim["kind"], regions, tolerances)
            if found is None:
                band_found = conditional_band_match(claim["hz"], covering, band_hz, tolerances) if conditional else None
                if band_found is not None:
                    _, region, component, limit = band_found
                    region["claims"].append({**claim, "probe_index": probe_index, "band": True,
                                             "nearest_hz": component["hz"], "band_limit_hz": limit})
                    region["band_claims"].append({"claim_hz": claim["hz"], "nearest_hz": component["hz"], "band_limit_hz": limit})
                    if claim["kind"] == "single":
                        region["bad"] = True
                        violations.append({"kind": "conditional_scalar_out_of_budget",
                                           "region": region["index"], "claim_hz": claim["hz"]})
                    continue
                violations.append({"kind": "unmatched_claim", "claim_kind": claim["kind"], "claim_hz": claim["hz"]})
                continue
            _, region, component, tolerance = found
            matched.append({"claim_kind": claim["kind"], "claim_hz": claim["hz"], "truth_hz": component["hz"],
                            "region": region["index"], "region_class": region["class"],
                            "error_hz": claim["hz"] - component["hz"],
                            "error_cents": 1200.0 * math.log2(claim["hz"] / component["hz"]), "tolerance_hz": tolerance})
            if claim["kind"] == "component":
                if region["class"] == CLASS_NONSTATIONARY:
                    violations.append({"kind": "component_claim_on_nonstationary_region", "region": region["index"], "claim_hz": claim["hz"]})
                    region["bad"] = True
                else:
                    region["claims"].append({**claim, "probe_index": probe_index})
            elif region["class"] not in (CLASS_SINGLE,):
                violations.append({"kind": ("single_claim_on_nonstationary_region" if region["class"] == CLASS_NONSTATIONARY
                                            else "single_claim_on_multi_component_region"),
                                   "region": region["index"], "claim_hz": claim["hz"]})
                region["bad"] = True
            else:
                region["claims"].append({**claim, "probe_index": probe_index})
                if claim["interval"] is None:
                    violations.append({"kind": "missing_interval", "region": region["index"], "claim_hz": claim["hz"]})
                    region["bad"] = True
                elif max(claim["hz"] - claim["interval"][0], claim["interval"][1] - claim["hz"]) > tolerance_hz(claim["hz"], tolerances, "single"):
                    violations.append({"kind": "interval_too_wide", "region": region["index"]})
                    region["bad"] = True
                elif claim["interval"][0] <= component["hz"] <= claim["interval"][1]:
                    region["single"] = True
                    interval["single_claims"] += 1
                    interval["covered"] += 1
                    interval["widths_cents"].append(1200.0 * math.log2(claim["interval"][1] / claim["interval"][0]))
                else:
                    violations.append({"kind": "interval_miss", "region": region["index"], "truth_hz": component["hz"],
                                       "low_hz": claim["interval"][0], "high_hz": claim["interval"][1]})
                    region["bad"] = True
    for region in regions:
        if region["class"] != CLASS_RESOLVED:
            continue
        claims = [claim for claim in region["claims"] if not claim.get("band") and claim["kind"] == "component"]
        for probe_index in {claim["probe_index"] for claim in claims}:
            one_probe = [claim for claim in claims if claim["probe_index"] == probe_index]
            used = set()
            for component in region["components"]:
                tolerance = tolerance_hz(component["hz"], tolerances, "component")
                for position, claim in enumerate(one_probe):
                    if position not in used and abs(claim["hz"] - component["hz"]) <= tolerance:
                        used.add(position)
                        break
            if len(used) == len(region["components"]) == len(one_probe):
                region["resolved"] = True
                break
    reports, failed = [], False
    for region in regions:
        claims = region.get("claims") or []
        if not region["covered"]:
            ok, detail = False, "region_not_probed"
            violations.append({"kind": "region_not_probed", "region": region["index"]})
        elif region["class"] == CLASS_SINGLE:
            if conditional:
                if region["single"] and not region["bad"]:
                    ok, detail = True, "conditional_static_certified"
                elif not region["single"] and region["bad"] is False and region["nonstatic_probes"] == region["probes"]:
                    ok, detail = True, "conditional_abstained"
                else:
                    ok, detail = False, "conditional_not_satisfied"
                    violations.append({"kind": ("conditional_claims_without_static_certification" if claims
                                                else "conditional_not_established"), "region": region["index"]})
            else:
                ok = region["single"] and not region["bad"]
                detail = "single_certified" if ok else "single_not_certified"
                if not ok:
                    violations.append({"kind": "single_line_not_certified", "region": region["index"],
                                       "class": region["class"], "detail": detail})
        elif region["class"] == CLASS_RESOLVED:
            ok = region["resolved"] and not region["bad"]
            detail = "resolved" if ok else "components_not_resolved"
        else:
            ok, detail = not region["bad"], "abstained" if not region["bad"] else "false_claim"
        failed = failed or not ok
        reports.append({"index": region["index"], "class": region["class"],
                        "components_hz": [component["hz"] for component in region["components"]],
                        "status": "satisfied" if ok else "violated", "detail": detail,
                        "band_claims": region.get("band_claims") or [],
                        "noncertified_diagnostic_components_hz": region.get("diagnostic_components") or []})
    return {"verdict": "failed" if (violations or failed) else "passed", "violations": violations, "matched_claims": matched,
            "interval": interval, "regions": reports,
            "conditional_static_certified": sum(1 for report in reports if report["detail"] == "conditional_static_certified"),
            "conditional_abstained": sum(1 for report in reports if report["detail"] == "conditional_abstained"),
            "claims": sum(1 for probe in probes if extract_claims(probe["output"]))}

def check_observer_windows(case, registration, windows, probes):
    """独立核对窗级记账；受控输入拒绝不能遮蔽缺行、伪造界或真实调用异常。"""
    if not isinstance(windows, dict):
        return [{"kind": "observer_windows_missing"}]
    names = list(case.get("windows") or [])
    violations = []
    if len(names) != len(set(names)) or set(windows) != set(names):
        violations.append({"kind": "observer_windows_incomplete", "expected": names, "actual": sorted(windows)})
    if (case.get("boundary") or {}).get("kind") == "frames_boundary" and set(names) != set(WINDOW_NAMES):
        violations.append({"kind": "observer_refusal_coverage_missing"})
    binding = expected_binding(case, registration)
    for name in names:
        record = windows.get(name)
        if not isinstance(record, dict):
            violations.append({"kind": "observer_window_missing", "window": name})
            continue
        expected = binding["windows"][name]
        for key, value in (("bounds_s", expected["relative"]), ("start_sample", expected["start"]),
                           ("stop_sample", expected["stop"]), ("samples", expected["stop"] - expected["start"]),
                           ("frames", binding["frames"]), ("coordinate", TIMING_COORDINATE),
                           ("evidence_role", EVIDENCE_ROLE), ("source", "runner_window_bounds")):
            if record.get(key) != value:
                violations.append({"kind": "observer_window_binding", "window": name, "field": key,
                                   "expected": value, "actual": record.get(key)})
        outside = expected["stop"] > binding["frames"]
        refusal = observer_window_refusal_expected(case, name)
        if expected["start"] < 0 or expected["stop"] <= expected["start"] or outside != refusal:
            violations.append({"kind": "observer_window_refusal_contract", "window": name})
        wanted = "input_refused" if outside and refusal else "input_accepted"
        if record.get("status") != wanted or record.get("stage") != "input":
            violations.append({"kind": "observer_window_status", "window": name,
                               "expected": wanted, "actual": record.get("status")})
        if record.get("error") is not None:
            violations.append({"kind": "observer_window_error", "window": name, "error": record["error"]})
        if wanted == "input_refused":
            if record.get("reason") != "window_exceeds_available_samples":
                violations.append({"kind": "observer_window_refusal_reason", "window": name})
            if any(record.get(key) is not None for key in ("frequency_hz", "interval_hz", "components")):
                violations.append({"kind": "observer_refusal_with_claim", "window": name})
    for probe in probes:
        name = probe.get("window")
        record = windows.get(name)
        if not isinstance(record, dict) or record.get("status") != "input_accepted":
            violations.append({"kind": "observer_probe_without_valid_window", "window": name})
    return violations



def run_observer_lane(observer, case, registration, left, right, rate, binding):
    if (left.ndim != 1 or right.ndim != 1 or left.size != right.size
            or left.size != case["frames"] or left.size != binding["frames"]
            or rate != case["rate"] or rate != binding["rate"]):
        raise ValueError("observer PCM channels, frame count or rate do not match the registered binding")
    band = (float(registration["candidates"]["band_low_factor"]) * nominal(case["note"]),
            min(float(registration["candidates"]["band_high_factor"]) * rate / 2.0, 20000.0))
    probes, windows = [], {}
    for name in case.get("windows") or []:
        window = binding["windows"][name]
        start, stop = window["start"], window["stop"]
        record = {"bounds_s": list(window["relative"]), "start_sample": start, "stop_sample": stop,
                  "samples": stop - start, "frames": int(left.size), "coordinate": TIMING_COORDINATE,
                  "evidence_role": EVIDENCE_ROLE, "source": "runner_window_bounds",
                  "status": "input_accepted", "stage": "input", "reason": None}
        windows[name] = record
        outside = start < 0 or stop <= start or stop > left.size
        refusal = observer_window_refusal_expected(case, name)
        if outside or refusal:
            if (start >= 0 and stop > start and stop > left.size and refusal):
                record.update({"status": "input_refused", "reason": "window_exceeds_available_samples"})
            else:
                record.update({"status": "failed", "reason": "window_refusal_contract_mismatch"})
            continue
        try:
            candidates = spectral_candidates(left, right, int(rate), start, stop, band, registration)
        except Exception as exc:
            record.update({"status": "failed", "stage": "candidates",
                           "error": f"{type(exc).__name__}: {exc}"})
            continue
        seconds = (exact_seconds(start, rate), exact_seconds(stop, rate))
        for candidate in candidates:
            try:
                output = json_ready(observer.observe_partial(left, right, int(rate), seconds, float(candidate["hz"]), half_width_of(case)))
                error = None
            except Exception as exc:  # 合法窗上的异常仍为界面失败，不变成受控拒绝或弃权。
                output, error = {"status": "observer_error"}, f"{type(exc).__name__}: {exc}"
            if not isinstance(output, dict):
                output, error = {"status": "observer_invalid_output"}, f"非字典返回值: {type(output).__name__}"
            probes.append({"window": name, "center_hz": float(candidate["hz"]), "candidate_rel": candidate["rel"],
                           "candidate_snr_db": candidate["snr_db"], "output": output, "observer_error": error})
    components = enumerate_components(case)
    assessment = assess_observer_case(case, build_regions(components, registration), probes, registration)
    window_violations = check_observer_windows(case, registration, windows, probes)
    assessment["violations"].extend(window_violations)
    if window_violations:
        assessment["verdict"] = "failed"
    return {"probes_executed": len(probes), "probes": probes, "windows": windows, **assessment}


# --------------------------------------------------------------------------- pa family 通道

def ppa_settings(ppa, note):
    """冻结的音符阈值规则：theory 用本设计名义频率（写入 ppa.NOTES），seeds/局部 SNR 用模块阈值。"""
    min_snr = ppa.SNR_ADMISSION_DB if (ppa.SNR_ADMISSION_DB is not None and note >= ppa.SNR_MIN_NOTE) else None
    return nominal(note), tuple(ppa.EXTENDED_SEEDS if note >= ppa.SNR_MIN_NOTE else ppa.DEFAULT_SEEDS), min_snr


def check_holdout(record, sufficiency):
    """独立复核留出充分性与误差预算（不只依赖门禁结论）。"""
    violations = []
    prediction = record.get("independent_prediction") or {}
    numbers = [int(number) for number in record.get("partial_numbers") or []]
    if prediction.get("status") != "ok":
        violations.append({"kind": "holdout_status", "status": prediction.get("status")})
    if not finite(prediction.get("training_size")) or int(prediction["training_size"]) < int(sufficiency["minimum_training_partials"]):
        violations.append({"kind": "insufficient_training", "training_size": prediction.get("training_size")})
    holdout = prediction.get("holdout_size")
    details = prediction.get("details") or []
    if not finite(holdout) or int(holdout) < int(sufficiency["minimum_independently_reidentified_holdouts"]) or len(details) != int(holdout or -1):
        violations.append({"kind": "incomplete_holdout", "holdout_size": holdout, "details": len(details)})
    errors, held = [], set()
    for detail in details:
        predicted, actual, number = detail.get("predicted_Hz"), detail.get("reidentified_Hz"), detail.get("number")
        if (not finite(predicted) or not finite(actual) or float(predicted) <= 0.0 or float(actual) <= 0.0
                or number not in numbers or number in held):
            violations.append({"kind": "invalid_holdout_observation", "number": number})
            continue
        held.add(number)
        errors.append(1200.0 * math.log2(float(actual) / float(predicted)))
    if len(errors) < int(sufficiency["minimum_independently_reidentified_holdouts"]):
        violations.append({"kind": "insufficient_independent_holdout", "count": len(errors)})
    rms = maximum = None
    if errors:
        rms = float(np.sqrt(np.mean(np.square(errors))))
        maximum = float(np.max(np.abs(errors)))
        if rms > float(sufficiency["independent_prediction_rms_cents_max"]) or maximum > float(sufficiency["independent_prediction_max_cents_max"]):
            violations.append({"kind": "independent_prediction_error", "rms_cents": rms, "max_cents": maximum})
    if finite(prediction.get("max_cents")) and maximum is not None and abs(float(prediction["max_cents"]) - maximum) > 1e-6:
        violations.append({"kind": "holdout_accounting_mismatch", "stated_max_cents": prediction["max_cents"], "recomputed": maximum})
    return {"status": prediction.get("status"), "holdout_size": prediction.get("holdout_size"),
            "training_size": prediction.get("training_size"), "observed_holdouts": len(errors),
            "rms_cents": rms, "max_cents": maximum, "violations": violations}


def assess_family_window(case, family_lines, record, tolerances, sufficiency):
    numbers, observed = list(record.get("partial_numbers") or []), list(record.get("observed_peak_Hz") or [])
    observations = []
    for number, value in zip(numbers, observed):
        truth_hz = family_lines.get(int(number))
        tolerance = tolerance_hz(truth_hz, tolerances, "single") if truth_hz else None
        error = abs(float(value) - truth_hz) if truth_hz else None
        observations.append({"partial": int(number), "observed_hz": float(value), "truth_hz": truth_hz, "error_hz": error,
                             "tolerance_hz": tolerance, "qualified": error is not None and error <= tolerance})
    stiffness, prediction = record.get("effective_B"), record.get("independent_prediction") or {}
    b_error = abs(float(stiffness) - float(case["b"])) / float(case["b"]) if finite(stiffness) else None
    return {"status": record.get("status"), "stage": record.get("stage"), "identified_partials": len(numbers),
            "observations": observations, "f1_Hz": record.get("f1_Hz"),
            "B_effective": float(stiffness) if finite(stiffness) else None, "B_relative_error": b_error,
            "B_qualified": b_error is not None and b_error <= float(tolerances["b_relative"]),
            "holdout_size": prediction.get("holdout_size"), "prediction_status": prediction.get("status"),
            "holdout": check_holdout(record, sufficiency)}


def check_timing_retention(analysis, timing):
    retained = analysis.get("timing")
    if not isinstance(retained, dict):
        return [{"kind": "timing_not_retained"}]
    violations = []
    for key, value in timing.items():
        if key not in retained:
            violations.append({"kind": "timing_key_missing", "key": key})
        elif retained[key] != value:
            violations.append({"kind": "timing_key_mismatch", "key": key, "expected": value, "actual": json_ready(retained[key])})
    return violations


def check_windows(analysis, case, binding):
    violations = []
    windows = analysis.get("windows")
    if not isinstance(windows, dict):
        return [{"kind": "windows_missing"}]
    for name in WINDOW_NAMES:
        record = windows.get(name)
        expected = binding["windows"][name]
        if not isinstance(record, dict):
            violations.append({"kind": "window_missing", "window": name})
            continue
        bounds = record.get("bounds_s")
        if not (isinstance(bounds, list) and len(bounds) == 2 and all(finite(value) for value in bounds)
                and abs(float(bounds[0]) - expected["relative"][0]) <= 1e-12
                and abs(float(bounds[1]) - expected["relative"][1]) <= 1e-12):
            violations.append({"kind": "window_relative_bounds_mismatch", "window": name,
                               "expected": expected["relative"], "actual": json_ready(bounds)})
        for key, want in (("start_sample", expected["start"]), ("stop_sample", expected["stop"]),
                          ("samples", expected["stop"] - expected["start"])):
            if record.get(key) != want:
                violations.append({"kind": "window_sample_bound_mismatch", "window": name, "key": key,
                                   "expected": want, "actual": json_ready(record.get(key))})
        if record.get("coordinate") != TIMING_COORDINATE or record.get("evidence_role") != EVIDENCE_ROLE:
            violations.append({"kind": "window_timing_coordinate_mismatch", "window": name,
                               "coordinate": record.get("coordinate"), "evidence_role": record.get("evidence_role")})
        if record.get("status") == "ok" and (expected["stop"] > binding["note_off_sample"] or expected["stop"] > binding["frames"]):
            violations.append({"kind": "ok_window_outside_bound_events", "window": name, "stop_sample": expected["stop"]})
    failures = analysis.get("window_failures")
    if not isinstance(failures, list):
        violations.append({"kind": "window_failures_missing"})
    else:
        listed = [entry.get("window") for entry in failures if isinstance(entry, dict)]
        expected_non_ok = [name for name in WINDOW_NAMES if (windows.get(name) or {}).get("status") != "ok"]
        if sorted(listed) != sorted(expected_non_ok):
            violations.append({"kind": "window_failures_inconsistent", "listed": listed, "expected_non_ok": expected_non_ok})
    boundary = case.get("boundary")
    if boundary and boundary["kind"] in ("release_boundary", "frames_boundary"):
        for name, want in boundary["expected_windows"].items():
            status = (windows.get(name) or {}).get("status")
            if (want == "ok" and status != "ok") or (want == "not_ok" and status == "ok"):
                violations.append({"kind": "boundary_window_status", "window": name, "expected": want, "actual": status})
        stage = (windows.get("W2") or {}).get("stage")
        if stage != boundary.get("expected_stage"):
            violations.append({"kind": "boundary_window_stage", "window": "W2",
                               "expected": boundary.get("expected_stage"), "actual": stage})
    return violations


def run_ppa_lane(ppa, gate, case, registration, left, right, rate, timing, binding):
    tolerances = registration["assessment"]["tolerances"]
    sufficiency = registration["assessment"]["sufficiency"]
    expectation = case["admission_expectation"]
    family_lines = family_lines_of(case)
    violations = []
    try:
        analysis = json_ready(ppa.analyze_samples(left, right, int(rate), int(case["note"]), timing=timing))
    except Exception as exc:
        return {"verdict": "failed", "branch": "entry_failed", "admission_expectation": expectation,
                "violations": [{"kind": "analyze_samples_entry_failed", "error": f"{type(exc).__name__}: {exc}"}],
                "admitted": None, "gate_reasons": None, "gate_windows": None, "windows": {},
                "matched_lines": [], "observed_lines": [], "analysis_record": None}
    if not isinstance(analysis, dict):
        return {"verdict": "failed", "branch": "entry_failed", "admission_expectation": expectation,
                "violations": [{"kind": "analyze_samples_invalid_output", "type": type(analysis).__name__}],
                "admitted": None, "gate_reasons": None, "gate_windows": None, "windows": {},
                "matched_lines": [], "observed_lines": [], "analysis_record": None}
    violations.extend(check_timing_retention(analysis, timing))
    violations.extend(check_windows(analysis, case, binding))
    windows = analysis.get("windows") if isinstance(analysis.get("windows"), dict) else {}
    quality = gate.reference_quality({"windows": {name: windows[name] for name in WINDOW_NAMES if name in windows}})
    admitted = bool(quality.get("admitted"))
    reports, matched_lines, observed_lines = {}, [], []
    for name in WINDOW_NAMES:
        record = windows.get(name)
        if not isinstance(record, dict):
            continue
        report = assess_family_window(case, family_lines, record, tolerances, sufficiency)
        reports[name] = report
        for observation in report["observations"]:
            if observation["truth_hz"] is None:
                continue
            entry = {"window": name, **observation,
                     "error_cents": 1200.0 * math.log2(observation["observed_hz"] / observation["truth_hz"])}
            observed_lines.append(entry)
            if observation["qualified"]:
                matched_lines.append(entry)

    def admitted_obligations():
        """准入（含条件静态认证）时必须全部通过的独立义务。"""
        local, claimed = [], set()
        for name, report in reports.items():
            if report["status"] != "ok" or report["identified_partials"] < int(sufficiency["minimum_identified_partials"]):
                local.append({"kind": "gate_incoherent_window", "window": name, "status": report["status"],
                              "identified": report["identified_partials"]})
            for violation in report["holdout"]["violations"]:
                local.append({**violation, "window": name})
            for observation in report["observations"]:
                claimed.add(observation["partial"])
                if observation["truth_hz"] is None:
                    local.append({"kind": "wrong_index_claim", "window": name, "partial": observation["partial"],
                                  "observed_hz": observation["observed_hz"]})
                elif not observation["qualified"]:
                    local.append({"kind": "frequency_out_of_tolerance", "window": name, "partial": observation["partial"],
                                  "observed_hz": observation["observed_hz"], "truth_hz": observation["truth_hz"],
                                  "error_hz": observation["error_hz"], "tolerance_hz": observation["tolerance_hz"]})
            if report["B_relative_error"] is None or not report["B_qualified"]:
                local.append({"kind": "B_out_of_tolerance", "window": name, "relative_error": report["B_relative_error"]})
        if all(reports.get(name, {}).get("status") == "ok" for name in WINDOW_NAMES):
            firsts = [reports[name]["f1_Hz"] for name in WINDOW_NAMES]
            stiffness = [reports[name]["B_effective"] for name in WINDOW_NAMES]
            if all(finite(value) and float(value) > 0 for value in firsts):
                spread = abs(1200.0 * math.log2(float(firsts[0]) / float(firsts[1])))
                if spread > float(sufficiency["window_frequency_spread_cents_max"]):
                    local.append({"kind": "window_frequency_spread_out_of_tolerance", "spread_cents": spread})
            if all(finite(value) and float(value) >= 0 for value in stiffness) and max(float(value) for value in stiffness) > 0:
                spread = abs(float(stiffness[0]) - float(stiffness[1])) / max(float(value) for value in stiffness)
                if spread > float(sufficiency["window_B_relative_spread_max"]):
                    local.append({"kind": "window_B_spread_out_of_tolerance", "relative_spread": spread})
        for number in case.get("required_partials") or []:
            if int(number) not in claimed:
                local.append({"kind": "required_partial_missing", "partial": int(number)})
        for number in case.get("forbidden_partials") or []:
            if int(number) in claimed:
                local.append({"kind": "forbidden_partial_claimed", "partial": int(number)})
        return local

    branch = None
    if expectation == "admitted":
        if admitted:
            branch = "required_admitted"
            violations.extend(admitted_obligations())
        else:
            branch = "required_admission_missed"
            violations.append({"kind": "expected_admission_but_rejected", "gate_reasons": quality.get("reasons")})
    elif expectation == "rejected":
        branch = "required_rejected"
        if admitted:
            violations.append({"kind": "false_static_admission", "gate_reasons": quality.get("reasons")})
    elif expectation == "conditional":
        if admitted:
            branch = "conditional_static_accepted"
            obligations = admitted_obligations()
            if obligations:
                violations.append({"kind": "false_conditional_static_admission", "details": obligations})
                violations.extend(obligations)
        else:
            branch = "conditional_abstained"
            if not quality.get("reasons"):
                violations.append({"kind": "incomplete_conditional_accounting"})
    else:
        raise ValueError(f"非法 admission_expectation 进入家族通道: {expectation!r}")
    return {"verdict": "failed" if violations else "passed", "branch": branch, "admission_expectation": expectation,
            "admitted": admitted, "gate_reasons": quality.get("reasons"), "gate_windows": quality.get("windows"),
            "windows": reports, "matched_lines": matched_lines, "observed_lines": observed_lines,
            "violations": violations,
            "analysis_record": analysis}


# --------------------------------------------------------------------------- 用例执行

def build_timing(case, registration, binding, pcm_sha256):
    return {"coordinate": TIMING_COORDINATE, "sample_rate": int(case["rate"]), "frames": int(binding["frames"]),
            "note_on_sample": int(binding["note_on_sample"]), "note_off_sample": int(binding["note_off_sample"]),
            "evidence_role": EVIDENCE_ROLE, "source": "method-qualification-noteon-v3 synthetic fixture",
            "case_id": case["id"], "pcm_sha256": pcm_sha256,
            "note_off_seconds_after_note_on": float(case["note_off_seconds_after_note_on"]),
            "frames_seconds_after_note_on": float(case["frames_seconds_after_note_on"])}


def run_case(observer, ppa, gate, registration, case, role, out_dir, binding):
    started = time.time()
    record = {"id": case["id"], "role": role, "kind": case["kind"], "expected_class": case["expected_class"],
              "obligation": case.get("obligation", "gating"), "recipe": case,
              "truth_role": "post-observation only; never passed to observers, gates or analyze_samples"}
    try:
        left, right = synthesize(case, registration)
        path = out_dir / "pcm" / f"{case['id']}.wav"
        write_pcm(path, case["rate"], np.stack([left, right], axis=1))
        rate_read, left_read, right_read = read_pcm(path)
        error = float(np.max(np.abs(np.stack([left_read, right_read], axis=1) - np.stack([left, right], axis=1))))
        if rate_read != int(case["rate"]) or error > 0.5 / 8388608.0 + 1e-12:
            raise ValueError(f"24-bit PCM 往返异常（rate={rate_read}, max_abs_error={error:.3e}）")
        components = enumerate_components(case)
        record["pcm"] = {"path": f"pcm/{case['id']}.wav", "sha256": sha256_file(path), "bytes": path.stat().st_size,
                         "frames": left.size, "lsb": 1.0 / 8388608.0, "max_roundtrip_abs_error": error}
        record["truth"] = truth_payload(case, components, build_regions(components, registration))
        timing = build_timing(case, registration, binding, record["pcm"]["sha256"])
        record["timing"] = timing
        if case["admission_expectation"] == "refused":
            try:
                ppa.analyze_samples(left_read, right_read, int(case["rate"]), int(case["note"]), timing=timing)
                refusal = {"refused": False, "detail": "analyze_samples_returned"}
            except Exception as exc:  # 非法事件绑定必须整体拒绝：异常即为要求的结果
                refusal = {"refused": True, "error_type": type(exc).__name__, "error": str(exc)[:500]}
            violations = [] if refusal["refused"] else [{"kind": "invalid_timing_not_refused", "detail": refusal["detail"]}]
            record["ppa_lane"] = {"verdict": "failed" if violations else "passed", "branch": "input_refused" if refusal["refused"] else "input_not_refused",
                                  "admission_expectation": "refused", "violations": violations, "refusal": refusal,
                                  "admitted": None, "gate_reasons": None, "gate_windows": None, "windows": {},
                                  "matched_lines": [], "observed_lines": [], "analysis_record": None}
            record["observer_lane"] = {"verdict": "skipped", "reason": "input_refused_before_analysis", "probes_executed": 0,
                                       "probes": [], "violations": [], "matched_claims": [], "regions": [],
                                       "interval": {"single_claims": 0, "covered": 0, "widths_cents": []}, "claims": 0,
                                       "conditional_static_certified": 0, "conditional_abstained": 0}
        else:
            record["observer_lane"] = run_observer_lane(observer, case, registration, left_read, right_read, rate_read, binding)
            record["ppa_lane"] = run_ppa_lane(ppa, gate, case, registration, left_read, right_read, rate_read, timing, binding)
        record["verdict"] = "passed" if (record["observer_lane"]["verdict"] != "failed"
                                         and record["ppa_lane"]["verdict"] == "passed") else "failed"
    except Exception as exc:  # 用例级失败保留证据并继续
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["verdict"] = "failed"
    record["elapsed_s"] = round(time.time() - started, 3)
    return record


# --------------------------------------------------------------------------- 跨用例门禁（复用冻结函数）

def min_comparable_for(note, registration):
    """短契约掩码原样保留：<72 → 7；72..95 → 5；>=96 → 1。"""
    mask = registration["assessment"]["comparison"]["existing_mask_unchanged"]
    if note < 72:
        return int(mask["midi_below_72"])
    if note < 96:
        return int(mask["midi_72_through_95"])
    return int(mask["midi_96_and_above"])


def evaluate_group_gates(gate, registration, records):
    """复用冻结门禁函数核验角色内跨用例义务（repeat_quality / compare_analyses），不另建第二评估器。"""
    expectations = comparison_expectations(registration)
    analyses = {}
    for row in records:
        record = (row.get("ppa_lane") or {}).get("analysis_record")
        if isinstance(record, dict):
            analyses[row["id"]] = record
    repeat_members, pair_members = {}, {}
    for row in records:
        spec = (row.get("recipe") or {}).get("repeat_group")
        if spec:
            repeat_members.setdefault(str(spec["group"]), []).append(row)
        spec = (row.get("recipe") or {}).get("comparison_pair")
        if spec:
            pair_members.setdefault(str(spec["pair"]), []).append(row)
    violations, repeat_reports, pair_reports = [], [], []
    for name, rows in sorted(repeat_members.items()):
        entries = [{"unit": row["id"], "repeat": int((row["recipe"] or {})["repeat_group"]["repeat"])} for row in rows]
        available = {row["id"]: analyses[row["id"]] for row in rows if row["id"] in analyses}
        try:
            result = json_ready(gate.repeat_quality(entries, available))
        except Exception as exc:  # 门禁异常按违例保留，不当作通过
            result = {"admitted": False, "reasons": [f"repeat_gate_error: {type(exc).__name__}: {exc}"]}
        repeat_reports.append({"group": name, "members": [row["id"] for row in rows], **result})
        if not result.get("admitted"):
            violations.append({"kind": "repeat_group_not_admitted", "group": name, "reasons": result.get("reasons")})
    for name, rows in sorted(pair_members.items()):
        def member(producer):
            return next((row for row in rows if (row.get("recipe") or {})["comparison_pair"]["producer"] == producer), None)
        reference, dev = member("a"), member("b")
        report = {"pair": name, "reference": reference["id"] if reference else None, "dev": dev["id"] if dev else None}
        if reference is None or dev is None or reference["id"] not in analyses or dev["id"] not in analyses:
            report.update({"state": "missing_analysis", "norm_rms": None, "norm_max": None, "nonbase_count": None})
        else:
            note = int((reference.get("recipe") or {})["note"])
            entry = {"unit": name, "note": note}
            try:
                result = json_ready(gate.compare_analyses(entry, analyses[reference["id"]], analyses[dev["id"]],
                                                          min_comparable_for(note, registration)))
                report.update({key: result.get(key) for key in ("state", "norm_rms", "norm_max", "nonbase_count",
                                                                "common_partials", "comparable_partials", "base_partial",
                                                                "f1_cents", "ref_B", "dev_B", "B_rel_pct")})
            except Exception as exc:
                report.update({"state": "gate_error", "error": f"{type(exc).__name__}: {exc}",
                               "norm_rms": None, "norm_max": None, "nonbase_count": None})
        expectation = expectations.get((rows[0].get("role"), name))
        actual_members = [reference["id"] if reference else None, dev["id"] if dev else None]
        mismatches = {}
        if (expectation is None or len(rows) != 2
                or actual_members != expectation["members"]
                or any(row.get("role") != expectation["role"] for row in rows)):
            mismatches["identity"] = {"actual_members": actual_members, "role": rows[0].get("role")}
        if expectation is not None:
            report["expected_output"] = {field: expectation[f"expected_{field}"] for field in PAIR_OUTPUT_FIELDS}
            for field, expected in report["expected_output"].items():
                actual = report.get(field)
                if type(actual) is not int or actual != expected:
                    mismatches[field] = {"expected": expected, "actual": actual}
        report["output_mismatches"] = mismatches
        report["output_obligation_satisfied"] = report.get("state") == "comparison_passed" and not mismatches
        pair_reports.append(report)
        if not report["output_obligation_satisfied"]:
            violations.append({"kind": "comparison_pair_not_passed", "pair": name, "state": report.get("state"),
                               "norm_rms": report.get("norm_rms"), "norm_max": report.get("norm_max"),
                               "nonbase_count": report.get("nonbase_count"), "output_mismatches": mismatches})
    return {"repeat_groups": repeat_reports, "comparison_pairs": pair_reports, "violations": violations,
            "gate_functions": ["validation-eval.py:repeat_quality", "validation-eval.py:compare_analyses"]}


# --------------------------------------------------------------------------- 汇总与 CLI

def run_evaluator_regression(tools_dir, out_dir):
    """独立运行同封印的评估器回归；真实输入/正式评估不是该门禁的前提。"""
    script = Path(tools_dir) / "validation-eval-tests.py"
    command = [sys.executable, str(script)]
    try:
        result = subprocess.run(command, capture_output=True, timeout=120)
        code, stdout, stderr = result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as error:
        code, stdout, stderr = 124, error.stdout or b"", error.stderr or b""
    stdout_path = Path(out_dir) / "evaluator-regression.stdout"
    stderr_path = Path(out_dir) / "evaluator-regression.stderr"
    stdout_path.write_bytes(stdout)
    stderr_path.write_bytes(stderr)
    return {"passed": code == 0, "command": command, "exit_code": code,
            "script_sha256": sha256_file(script),
            "stdout": stdout_path.name, "stdout_sha256": sha256_file(stdout_path),
            "stderr": stderr_path.name, "stderr_sha256": sha256_file(stderr_path)}


def summarize(role, records, controls, registration, identity, aborted, elapsed_s, expected_cases,
              group_gates, evaluator_regression):
    failed_gating = [row["id"] for row in records if row["verdict"] != "passed"]
    controls_violated = [row["id"] for row in controls if row["verdict"] != "passed"]
    single_errors, component_errors, widths, ppa_lines, missed_positives = [], [], [], [], []
    false_claim_kinds = set()
    single_claims = covered = 0
    regions_expected = {key: 0 for key in (CLASS_SINGLE, CLASS_RESOLVED, CLASS_AMBIGUOUS, CLASS_NONSTATIONARY)}
    regions_satisfied = dict.fromkeys(regions_expected, 0)
    required_single_expected = required_single_certified = 0
    conditional_certified = conditional_abstained = 0
    for row in records:
        lane = row.get("observer_lane") or {}
        conditional_case = bool((row.get("recipe") or {}).get("conditional"))
        for claim in lane.get("matched_claims", []):
            (single_errors if claim["claim_kind"] == "single" else component_errors).append(claim["error_cents"])
        interval = lane.get("interval") or {}
        single_claims += int(interval.get("single_claims", 0))
        covered += int(interval.get("covered", 0))
        widths.extend(interval.get("widths_cents", []))
        for region in lane.get("regions", []):
            regions_expected[region["class"]] = regions_expected.get(region["class"], 0) + 1
            if region["status"] == "satisfied":
                regions_satisfied[region["class"]] += 1
                if region["detail"] == "conditional_static_certified":
                    conditional_certified += 1
                elif region["detail"] == "conditional_abstained":
                    conditional_abstained += 1
            elif region["class"] in (CLASS_SINGLE, CLASS_RESOLVED):
                missed_positives.append({"case": row["id"], "region": region["index"], "class": region["class"], "detail": region["detail"]})
            if region["class"] == CLASS_SINGLE:
                if conditional_case:
                    pass
                else:
                    required_single_expected += 1
                    if region["detail"] == "single_certified":
                        required_single_certified += 1
        for violation in lane.get("violations", []):
            if violation["kind"] not in ("region_not_probed", "missing_interval", "interval_miss"):
                false_claim_kinds.add(violation["kind"])
        ppa = row.get("ppa_lane") or {}
        ppa_lines.extend(entry["error_cents"] for entry in ppa.get("matched_lines", []))

    def collect(*patterns):
        """收集 ppa_lane 违例：pattern 完全匹配或作为前缀匹配。"""
        rows = []
        for row in records:
            for violation in (row.get("ppa_lane") or {}).get("violations", []):
                kind = violation["kind"]
                if any(kind == pattern or kind.startswith(pattern) for pattern in patterns):
                    rows.append({"case": row["id"], **violation})
        return rows

    holdout_kinds = ("holdout_status", "insufficient_training", "incomplete_holdout", "invalid_holdout_observation",
                     "insufficient_independent_holdout", "independent_prediction_error", "holdout_accounting_mismatch")
    window_kinds = ("window_missing", "window_relative_bounds_mismatch", "window_sample_bound_mismatch",
                    "window_timing_coordinate_mismatch", "window_failures_missing", "window_failures_inconsistent",
                    "window_frequency_spread_out_of_tolerance", "window_B_spread_out_of_tolerance",
                    "gate_incoherent_window", "ok_window_outside_bound_events")

    positive_expected = [row["id"] for row in records if (row.get("recipe") or {}).get("admission_expectation") == "admitted"]
    positive_verified = [row["id"] for row in records if (row.get("ppa_lane") or {}).get("branch") == "required_admitted" and row["verdict"] == "passed"]
    minimum = int(registration["coverage_requirements"]["minimum_required_admission_cases_per_role"])
    admission_misses = collect("expected_admission_but_rejected")
    false_static = collect("false_static_admission")
    positive_coverage = {"minimum_admitted_required": minimum, "cases_expected": len(positive_expected),
                         "cases_verified_admitted": len(positive_verified),
                         "admission_misses": admission_misses,
                         "satisfied": len(positive_verified) >= minimum and not admission_misses}
    conditional_rows = [row for row in records if (row.get("recipe") or {}).get("admission_expectation") == "conditional"]
    conditional_summary = {
        "cases": [row["id"] for row in conditional_rows],
        "static_accepted": [row["id"] for row in conditional_rows if (row.get("ppa_lane") or {}).get("branch") == "conditional_static_accepted"],
        "abstained": [row["id"] for row in conditional_rows if (row.get("ppa_lane") or {}).get("branch") == "conditional_abstained"],
        "false_admissions": collect("false_conditional_static_admission"),
        "incomplete_accounting": collect("incomplete_conditional_accounting"),
        "observer_conditional": {"static_certified": conditional_certified, "explicit_abstained": conditional_abstained},
        "am_carrier_never_in_B": "准入 B 相对误差义务即该约束的检查（AM carrier 输出不得进入 B）",
    }
    boundary_cases = [row["id"] for row in records if (row.get("recipe") or {}).get("boundary")]
    refused_rows = [row["id"] for row in records if (row.get("recipe") or {}).get("admission_expectation") == "refused"]
    group_violations = list((group_gates or {}).get("violations") or [])
    registered = registration["cases"][role]
    expected_ids = {case["id"] for case in registered}
    control_ids = {case["id"] for case in registration["regression_controls"]}
    repeat_ids = {(case.get("repeat_group") or {})["group"] for case in registered
                  if case.get("repeat_group")}
    pair_ids = {(case.get("comparison_pair") or {})["pair"] for case in registered
                if case.get("comparison_pair")}
    repeat_reports = (group_gates or {}).get("repeat_groups") or []
    pair_reports = (group_gates or {}).get("comparison_pairs") or []
    pass_conditions = {
        "complete_registered_role": expected_cases == len(registered) == len(records)
            and {row["id"] for row in records} == expected_ids,
        "complete_controls": len(controls) == len(control_ids)
            and {row["id"] for row in controls} == control_ids,
        "complete_group_gates": len(repeat_reports) == len(repeat_ids)
            and {row["group"] for row in repeat_reports} == repeat_ids
            and len(pair_reports) == len(pair_ids)
            and {row["pair"] for row in pair_reports} == pair_ids,
        "evaluator_regression_passed": evaluator_regression.get("passed") is True,
        "no_failed_gating_cases": not failed_gating, "controls_clean": not controls_violated,
        "positive_coverage_satisfied": positive_coverage["satisfied"],
        "repeat_groups_admitted": not any(v["kind"] == "repeat_group_not_admitted" for v in group_violations),
        "comparison_pairs_passed": not any(v["kind"] == "comparison_pair_not_passed" for v in group_violations)}
    passed = all(pass_conditions.values())
    outcome = ("aborted" if aborted else
               ("qualified" if passed and role == "qualification" else
                ("development_passed" if passed and role == "development" else
                 ("not_qualified" if role == "qualification" else "development_failed"))))
    return {
        "role": role, "outcome": outcome, "aborted": aborted, "elapsed_s": round(elapsed_s, 3),
        "criterion": "每个 gating 用例必须满足声明的真实结果（含条件域与边界）；controls 不得违反；角色内重复组与归一化可比对必须经冻结门禁函数通过；硬性正向准入覆盖达到下限；无全局通过率、无阈值放宽、无 diagnostic 下移",
        "cases_total": len(records), "cases_failed": [row["id"] for row in records if row["verdict"] != "passed"],
        "gating_failed": failed_gating,
        "cross_case_gates": {**(group_gates or {"repeat_groups": [], "comparison_pairs": [], "violations": [],
                                                "gate_functions": []}), "violations": group_violations},
        "qualification_scope": {
            "scope": "complete_method_in_registered_synthetic_domain",
            "includes": ["观测器", "NoteOn 坐标", "静态族", "repeat_quality", "compare_analyses",
                         "封印绑定的六态评估器回归"],
            "full_v3_evaluation": False,
            "reference_origin_authentication": "independent_downstream_gate",
            "downstream_release_gates": ["reference_origin_authentication",
                                         "real_capture_and_formal_evaluation"]},
        "evaluator_regression": evaluator_regression,
        "complete_role": {"expected_cases": expected_cases, "executed_cases": len(records),
                          "complete": pass_conditions["complete_registered_role"] and aborted is None},
        "controls": [{"id": row["id"], "verdict": row["verdict"]} for row in controls], "controls_violated": controls_violated,
        "expected_class_counts": {name: sum(1 for row in records if row["expected_class"] == name)
                                  for name in sorted({row["expected_class"] for row in records})},
        "pass_conditions": pass_conditions,
        "observer_lane": {
            "single_claims": single_claims, "interval_coverage_fraction": (covered / single_claims) if single_claims else None,
            "interval_width": describe(widths), "single_claim_error": describe(single_errors),
            "component_claim_error": describe(component_errors), "regions_expected": regions_expected,
            "regions_satisfied": regions_satisfied, "missed_positives": missed_positives,
            "false_claim_kinds": sorted(false_claim_kinds),
            "required_single_regions": required_single_expected, "required_single_regions_certified": required_single_certified,
            "single_regions_certified": required_single_expected > 0 and required_single_certified == required_single_expected,
            "blanket_abstention": required_single_expected > 0 and required_single_certified == 0,
            "conditional_static_certified_regions": conditional_certified,
            "conditional_explicit_abstained_regions": conditional_abstained,
        },
        "ppa_lane": {
            "admission_expected": len(positive_expected), "admission_misses": admission_misses,
            "rejection_expected": sum(1 for row in records if (row.get("recipe") or {}).get("admission_expectation") == "rejected"),
            "false_static_admissions": false_static, "line_error_accepted": describe(ppa_lines),
            "wrong_index_claims": collect("wrong_index_claim"), "frequency_violations": collect("frequency_out_of_tolerance"),
            "B_budget_violations": collect("B_out_of_tolerance"), "holdout_violations": collect(*holdout_kinds),
            "timing_violations": collect("timing"), "window_violations": collect(*window_kinds),
            "boundary_violations": collect("boundary_"),
        },
        "positive_coverage": positive_coverage,
        "conditional_domain": conditional_summary,
        "boundary_cases": {"cases": boundary_cases, "violations": collect("boundary_")},
        "input_rejections": {"cases": refused_rows, "violations": collect("invalid_timing_not_refused")},
        "all_cases_gating": True, "no_diagnostic_obligations": True, "no_global_pass_rate": True,
        "identity": identity,
        "registration": {"path": identity["registration"]["path"], "sha256": identity["registration"]["sha256"],
                         "schema": registration["schema"], "status": registration["status"]},
        "limits": list(registration["limits"]),
    }


def check_registration_summary(registration, path, groups):

    def role_summary(cases):
        repeats, pairs = {}, {}
        for case in cases:
            if case.get("repeat_group"):
                repeats.setdefault(case["repeat_group"]["group"], []).append(case["id"])
            if case.get("comparison_pair"):
                pairs.setdefault(case["comparison_pair"]["pair"], []).append(case["id"])
        return {"cases": len(cases),
                "rates": sorted({int(case["rate"]) for case in cases}),
                "expected_classes": sorted({case["expected_class"] for case in cases}),
                "required_admission_cases": sum(1 for case in cases if case["admission_expectation"] == "admitted"),
                "conditional_cases": sum(1 for case in cases if case["admission_expectation"] == "conditional"),
                "refused_cases": sum(1 for case in cases if case["admission_expectation"] == "refused"),
                "boundary_kinds": sorted({case["boundary"]["kind"] for case in cases if case.get("boundary")}),
                "note_on_offsets": sorted({int(case["note_on_sample"]) for case in cases}),
                "observer_window_names": sorted({name for case in cases for name in case["windows"]}),
                "repeat_groups": {name: members for name, members in sorted(repeats.items())},
                "comparison_pairs": {name: members for name, members in sorted(pairs.items())}}

    return {"schema": registration["schema"], "status": "valid",
            "registration": {"path": str(Path(path).resolve()), "sha256": sha256_file(path)},
            "development": role_summary(groups["development"]), "qualification": role_summary(groups["qualification"]),
            "regression_controls": {"cases": len(groups["control"]), "ids": [case["id"] for case in groups["control"]],
                                    "verdict_expectation": "rejected（consumed regression only）"},
            "roles_disjoint": True, "seeds_disjoint": True, "recipes_disjoint": True,
            "all_cases_gating": True, "diagnostic_obligations": [],
            "cross_case_gates": {"repeat_obligation": registration["assessment"]["repeat_obligation"]["obligation"],
                                 "comparison": registration["assessment"]["comparison"]["obligation"],
                                 "gate_functions": [registration["assessment"]["repeat_obligation"]["gate_function"],
                                                    registration["assessment"]["comparison"]["gate_function"]]},
            "complete_plan_gates": registration["complete_plan_gates"]["required"],
            "positive_coverage_minimum": registration["coverage_requirements"]["minimum_required_admission_cases_per_role"],
            "execution": {"approval": registration["execution"]["approval"],
                          "development_authorized": registration["execution"]["development"]["authorized"],
                          "qualification_authorized": registration["execution"]["approval"] is True,
                          "seal_required": registration["execution"]["qualification"]["seal_required"]},
            "stop_policy_clauses": sorted(registration["stop_policy"]["clauses"]),
            "pcm_generated": False, "roles_consumed": False}


def prepare_ppa(ppa, cases):
    notes = {}
    for case in cases:
        notes[int(case["note"])] = nominal(int(case["note"]))
    if not hasattr(ppa, "NOTES"):
        raise SystemExit("分析工具缺少 NOTES 映射，无法注入名义理论频率")
    ppa.NOTES.update(notes)
    return notes


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--registration", type=Path, required=True, help="当前完整登记（实际执行另需授权；已消费登记不得重放）")
    parser.add_argument("--check-registration", action="store_true",
                        help="只读校验新注册的完整性/互斥性/停止策略；不生成 PCM、不消费任何角色")
    parser.add_argument("--out", type=Path, help="全新输出目录（已存在即拒绝）")
    parser.add_argument("--role", choices=("development", "qualification"), help="development 可反复调试；qualification 需 approval+seal")
    parser.add_argument("--seal", type=Path, help="qualification 外部封印 JSON（绑定注册与源码精确 sha256）")
    args = parser.parse_args()
    if not args.registration.is_file():
        raise SystemExit(f"registration 文件不存在: {args.registration}")
    registration = load_registration(args.registration)
    groups = validate_registration(registration)
    if args.check_registration:
        print("CHECK " + json.dumps(check_registration_summary(registration, args.registration, groups),
                                    ensure_ascii=True, sort_keys=True), flush=True)
        raise SystemExit(0)
    if args.out is None or args.role is None:
        parser.error("执行模式需要 --out 与 --role（或用 --check-registration 只读校验）")
    tools_dir = Path(__file__).resolve().parent
    dependency_paths = [tools_dir / name for name in SEALED_SOURCES] + [args.registration.resolve()]
    identities = {str(path.resolve()): sha256_file(path) for path in dependency_paths}
    marker = None
    if args.role == "qualification":
        if registration["execution"]["approval"] is not True:
            raise SystemExit("qualification 被拒绝：execution.approval=false（本轮硬性阻断；仅显式批准后改写该字段，执行器不自行改写）"
                             "——拒绝发生在创建输出目录与加载任何模块之前")
        if args.seal is None or not args.seal.is_file():
            raise SystemExit("qualification 被拒绝：缺少外部 --seal 封印（必须精确绑定本注册与五个源码的 sha256）")
        try:
            seal = json.loads(args.seal.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise SystemExit(f"qualification 被拒绝：封印读取失败: {error}")
        if seal.get("role") != SEAL_ROLE or seal.get("files") != identities:
            raise SystemExit("qualification 被拒绝：封印未精确绑定本注册与五个源码的实际散列")
        marker = args.seal.with_name(args.seal.name + ".consumed")
        if marker.exists():
            raise SystemExit(f"qualification 被拒绝：封印已被消费（{marker}）；无子集/重试/换目录重跑")
    elif registration["execution"]["development"]["authorized"] is not True:
        raise SystemExit("development 未授权")
    out_dir = args.out.resolve()
    if out_dir.exists():
        raise SystemExit(f"--out 目录已存在，按规范拒绝覆盖: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=False)
    (out_dir / "pcm").mkdir()
    if marker is not None:
        try:  # 执行即消费：封印对应一轮完整角色，失败/中断也不得重跑
            with marker.open("x", encoding="utf-8") as handle:
                json.dump({"role": SEAL_ROLE, "role_run": args.role,
                           "registration_sha256": identities[str(args.registration.resolve())],
                           "runner_sha256": identities[str(Path(__file__).resolve())], "seal": str(args.seal),
                           "out": str(out_dir), "started_utc": datetime.now(timezone.utc).isoformat()},
                          handle, ensure_ascii=False)
                handle.write("\n")
        except FileExistsError:
            raise SystemExit(f"qualification 被拒绝：封印已被消费（{marker}）")
    observer = load_module(tools_dir / "partial-observer.py", "qualification_observer")
    ppa = load_module(tools_dir / "pilot-partial-analysis.py", "qualification_ppa")
    gate = load_module(tools_dir / "validation-eval.py", "qualification_gate")
    for module, attribute, label in ((observer, "observe_partial", "观测器"), (ppa, "analyze_samples", "分析工具"),
                                     (gate, "reference_quality", "评估器")):
        if not hasattr(module, attribute):
            raise SystemExit(f"{label} 缺少共享接口: {attribute}")
    role_cases = list(groups[args.role])
    control_cases = list(groups["control"])
    bindings = {case["id"]: expected_binding(case, registration) for case in role_cases + control_cases}
    injected = prepare_ppa(ppa, role_cases + control_cases)
    digest = lambda path: {"path": str(Path(path).resolve()), "sha256": sha256_file(path)}
    identity = {"qualification_script": digest(Path(__file__).resolve()),
                "analysis_tool": digest(tools_dir / "pilot-partial-analysis.py"),
                "observer": digest(tools_dir / "partial-observer.py"), "evaluator": digest(tools_dir / "validation-eval.py"),
                "evaluator_regression_script": digest(tools_dir / "validation-eval-tests.py"),
                "registration": digest(args.registration), "seal": digest(args.seal) if args.seal else None,
                "consumption_marker": str(marker) if marker else None,
                "python": sys.version, "platform": platform.platform(), "numpy": np.__version__,
                "run_started_utc": datetime.now(timezone.utc).isoformat(),
                "rng": "numpy.random.default_rng(seed)/PCG64，每用例按左、右声道顺序抽取高斯噪声",
                "fixture_pcm": "24-bit signed stereo；round-to-nearest sample*8388608；无归一化、无削波；写盘回读核验",
                "timing_coordinate": TIMING_COORDINATE, "evidence_role": EVIDENCE_ROLE,
                "ppa_notes_injected": {str(key): value for key, value in sorted(injected.items())},
                "approval": registration["execution"]["approval"],
                "sealed_identities": {name: sha256_file(tools_dir / name) for name in SEALED_SOURCES} if args.role == "qualification" else None,
                "stop_policy": "封印对应一轮完整角色，执行即消费；失败/中断全部保留后停止；无子集/重试/调参/替换"}
    print(f"ROLE {args.role} out={out_dir} cases={len(role_cases)} controls={len(control_cases)} "
          f"registration={identity['registration']['sha256'][:16]} analysis={identity['analysis_tool']['sha256'][:16]} "
          f"observer={identity['observer']['sha256'][:16]} evaluator={identity['evaluator']['sha256'][:16]} "
          f"approval={registration['execution']['approval']}", flush=True)
    started, records, control_records, aborted = time.time(), [], [], None
    evaluator_regression = {"passed": False, "reason": "not_executed"}
    try:
        evaluator_regression = run_evaluator_regression(tools_dir, out_dir)
        if not evaluator_regression["passed"]:
            raise RuntimeError("evaluator_regression_failed; synthetic role not executed")
        for case, role in [(case, args.role) for case in role_cases] + [(case, "regression_control") for case in control_cases]:
            record = run_case(observer, ppa, gate, registration, case, role, out_dir, bindings[case["id"]])
            (control_records if role == "regression_control" else records).append(record)
            (out_dir / (case["id"] + ".json")).write_text(
                json.dumps(record, indent=1, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
            print(f"CASE {record['id']} role={role} verdict={record['verdict']} "
                  f"branch={(record.get('ppa_lane') or {}).get('branch')} "
                  f"observer={(record.get('observer_lane') or {}).get('verdict')} "
                  f"ppa={(record.get('ppa_lane') or {}).get('verdict')} elapsed={record['elapsed_s']:.1f}s", flush=True)
        if len(records) != len(role_cases) or len(control_records) != len(control_cases):
            aborted = "incomplete_role"
    except BaseException as error:  # 保留已产出的证据，随后以非零退出
        aborted = f"{type(error).__name__}: {error}"
        print(f"ABORT {aborted}", flush=True)
    group_gates = evaluate_group_gates(gate, registration, records)
    for report in group_gates["repeat_groups"]:
        print(f"REPEAT {report['group']} admitted={report.get('admitted')} "
              f"f_spread={report.get('frequency_spread_cents')} b_spread={report.get('B_relative_spread')}", flush=True)
    for report in group_gates["comparison_pairs"]:
        print(f"COMPARE {report['pair']} state={report.get('state')} nonbase={report.get('nonbase_count')} "
              f"norm_rms={report.get('norm_rms')} norm_max={report.get('norm_max')}", flush=True)
    summary = summarize(args.role, records, control_records, registration, identity, aborted, time.time() - started,
                        len(role_cases), group_gates, evaluator_regression)
    report = {"schema": SCHEMA, "role": args.role, "status": "aborted" if aborted else "complete",
              "registration": summary["registration"], "identity": identity, "summary": summary,
              "cross_case_gates": summary["cross_case_gates"], "qualification_scope": summary["qualification_scope"],
              "cases": records, "regression_controls": control_records}
    (out_dir / "method-qualification-report.json").write_text(
        json.dumps(report, indent=1, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print("SUMMARY " + json.dumps(summary, ensure_ascii=True), flush=True)
    print(f"REPORT {out_dir / 'method-qualification-report.json'}", flush=True)
    raise SystemExit(0 if summary["outcome"] in ("qualified", "development_passed") else 1)


if __name__ == "__main__":
    main()
