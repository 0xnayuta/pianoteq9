#!/usr/bin/env python3
"""NoteOn runner 回归：条件域/完整记账、授权提前拒绝及登记比较输出义务。

覆盖要点（均为纯离线、无资格执行）：
- 条件域（AM/弱边界）只接受“静态条件认证（全部独立义务通过）”或“显式弃权（拒绝且理由非空）”，
  其它 claim 一律违例；不完整记账（拒绝但无理由）必须失败。
- required single 分区未认证（含全体弃权）必须失败，不能被当作通过。
- 注册校验强制 development/qualification 种子与配方互斥、覆盖下限、停止策略完整、旧 schema 拒绝。
- 静态校验不授予执行权；未授权角色或无有效封印时，任何文件/PCM/模块加载前拒绝。
"""
import contextlib
import copy
import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

spec = importlib.util.spec_from_file_location("meter", Path(__file__).with_name("meter-qualification.py"))
meter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(meter)

gate_spec = importlib.util.spec_from_file_location("qualification_gate", Path(__file__).with_name("validation-eval.py"))
gate = importlib.util.module_from_spec(gate_spec)
gate_spec.loader.exec_module(gate)  # 复用冻结门禁函数（repeat_quality / compare_analyses），不另建第二评估器

PILOT = Path(__file__).resolve().parents[1]
REGISTRATION_PATH = PILOT / "method-qualification-a5-v1.json"
CONTROL_REGISTRATION = json.loads((PILOT / "method-qualification-noteon-v3.json").read_text(encoding="utf-8"))
registration = json.loads(REGISTRATION_PATH.read_text(encoding="utf-8"))

# 已消费登记只作测试数据；窗级契约在私有副本中更新，不改写磁盘原件。
registration["execution"]["approval"] = False
registration["execution"]["development"]["authorized"] = False
for _cases in registration["cases"].values():
    for _case in _cases:
        if (_case.get("boundary") or {}).get("kind") == "frames_boundary":
            _case["windows"] = list(meter.WINDOW_NAMES)


def merged(case_id):
    for group in ("development", "qualification"):
        for case in CONTROL_REGISTRATION["cases"][group]:
            if case["id"] == case_id:
                return meter.merged_case(case, CONTROL_REGISTRATION["generator"]["case_defaults"])
    for case in CONTROL_REGISTRATION["regression_controls"]:
        if case["id"] == case_id:
            return meter.merged_case(case, CONTROL_REGISTRATION["generator"]["case_defaults"])
    raise KeyError(case_id)


def region(frequencies, classification, index=1):
    return {"index": index, "class": classification,
            "components": [{"hz": value} for value in frequencies],
            "span_low_hz": min(frequencies), "span_high_hz": max(frequencies),
            "min_separation_hz": min((b - a for a, b in zip(frequencies, frequencies[1:])), default=None)}


def probe(status, frequencies=(), interval=None, center=440.0):
    return {"center_hz": center, "observer_error": None,
            "output": {"status": status,
                       "frequency_hz": frequencies[0] if status == meter.STATUS_SINGLE else None,
                       "interval_hz": interval,
                       "components": [{"frequency_hz": value} for value in frequencies]}}


def window_record(binding, name, status, stage=None, **extra):
    expected = binding["windows"][name]
    record = {"bounds_s": list(expected["relative"]), "start_sample": expected["start"],
              "stop_sample": expected["stop"], "samples": expected["stop"] - expected["start"],
              "coordinate": meter.TIMING_COORDINATE, "evidence_role": meter.EVIDENCE_ROLE, "status": status}
    if stage is not None:
        record["stage"] = stage
    record.update(extra)
    return record


def fake_analysis(case, binding, timing, statuses=("inconclusive", "inconclusive")):
    windows = {name: window_record(binding, name, status) for name, status in zip(meter.WINDOW_NAMES, statuses)}
    failures = [{"window": name, "status": windows[name]["status"]} for name in meter.WINDOW_NAMES
                if windows[name]["status"] != "ok"]
    return {"timing": dict(timing), "theory_Hz": meter.nominal(case["note"]), "windows": windows,
            "window_failures": failures}


def qualified_observation(frequency):
    """通过冻结门禁 observation_qualified 的条件区间观测。"""
    budget = max(0.005, frequency * (2.0 ** (0.05 / 1200.0) - 1.0))
    half = 0.9 * budget
    return {"status": "single_component_adequate", "frequency_hz": frequency,
            "interval_hz": [frequency - half, frequency + half]}


def ok_window(case, binding, name, numbers, f1, stiffness, holdout_status="ok"):
    lines = meter.family_lines_of(case)
    observed = [lines[number] if number in lines else meter.nominal(case["note"]) * number for number in numbers]
    details = []
    for number in (numbers[0], numbers[1]):
        predicted = lines[number] if number in lines else meter.nominal(case["note"]) * number
        details.append({"number": number, "predicted_Hz": predicted, "reidentified_Hz": predicted,
                        "error_cents": 0.0, "observation": qualified_observation(predicted)})
    return window_record(binding, name, "ok",
                         partial_numbers=numbers, observed_peak_Hz=observed,
                         partial_observations={str(number): qualified_observation(value) for number, value in zip(numbers, observed)},
                         independent_prediction={"status": holdout_status, "training_size": 3, "holdout_size": 2,
                                                 "details": details, "max_cents": 0.0},
                         f1_Hz=f1, effective_B=stiffness)


def admitted_analysis(case, binding, timing, numbers=None, holdout_status="ok", f1=None, stiffness=None):
    """构造一个“全部义务通过”的家族通道分析记录（真值线由注册几何独立生成）。"""
    lines = meter.family_lines_of(case)
    numbers = numbers or sorted(lines)[:5]
    f1 = f1 if f1 is not None else meter.nominal(case["note"]) + float(case.get("f1_offset_hz", 0.0))
    stiffness = stiffness if stiffness is not None else float(case["b"])
    windows = {name: ok_window(case, binding, name, numbers, f1, stiffness, holdout_status) for name in meter.WINDOW_NAMES}
    return {"timing": dict(timing), "theory_Hz": meter.nominal(case["note"]), "windows": windows, "window_failures": []}


def fake_ppa(analysis):
    return types.SimpleNamespace(analyze_samples=lambda left, right, rate, note, timing=None: copy.deepcopy(analysis))


def fake_gate(admitted, reasons):
    return types.SimpleNamespace(reference_quality=lambda payload: {"admitted": admitted, "reasons": list(reasons), "windows": {}})


class ConditionalDomainObligations(unittest.TestCase):
    def score(self, probes, conditional=True, band_hz=0.4):
        case = {"conditional": {"domain": "conditional_am", "band_hz": band_hz}, "probe_half_width_hz": 3.0} if conditional else {}
        return meter.assess_observer_case(case, [region([440.0], "single")], probes, registration)

    def test_conditional_single_certification_requires_interval_truth_coverage(self):
        certified = self.score([probe(meter.STATUS_SINGLE, [440.0], [439.999, 440.001])])
        self.assertEqual(certified["verdict"], "passed")
        self.assertEqual(certified["regions"][0]["detail"], "conditional_static_certified")
        wide = self.score([probe(meter.STATUS_SINGLE, [440.0], [400.0, 480.0])])
        self.assertEqual(wide["verdict"], "failed")

    def test_conditional_explicit_abstention_is_valid(self):
        result = self.score([probe(meter.STATUS_AMBIGUOUS)])
        self.assertEqual(result["verdict"], "passed")
        self.assertEqual(result["regions"][0]["detail"], "conditional_abstained")

    def test_conditional_multiple_components_are_diagnostics_not_static_admission(self):
        result = self.score([probe(meter.STATUS_RESOLVED, [439.7, 440.0, 440.3])])
        self.assertEqual(result["verdict"], "passed")
        self.assertEqual(result["conditional_static_certified"], 0)
        self.assertEqual(result["conditional_abstained"], 1)
        invalid_scalar = self.score([probe(meter.STATUS_SINGLE, [440.2], [440.199, 440.201])])
        self.assertEqual(invalid_scalar["verdict"], "failed")
        mixed = self.score([probe(meter.STATUS_SINGLE, [440.0], [439.999, 440.001]),
                            probe(meter.STATUS_SINGLE, [440.2], [440.199, 440.201])])
        self.assertEqual(mixed["verdict"], "failed")

    def test_required_single_region_abstention_is_failure_not_waiver(self):
        case = {"probe_half_width_hz": 3.0}
        result = meter.assess_observer_case(case, [region([440.0], "single")], [probe(meter.STATUS_AMBIGUOUS)], registration)
        self.assertEqual(result["verdict"], "failed")
        self.assertEqual(result["regions"][0]["detail"], "single_not_certified")
        self.assertIn("single_line_not_certified", [violation["kind"] for violation in result["violations"]])


class ConditionalFamilyLane(unittest.TestCase):
    """条件域家族通道：准入必须全部义务通过；拒绝必须显式且理由非空。"""

    def setUp(self):
        self.case = merged("dev-amslow-55-44100")
        self.binding = meter.expected_binding(self.case, registration)
        self.timing = meter.build_timing(self.case, registration, self.binding, "0" * 64)

    def run_lane(self, analysis, admitted, reasons):
        return meter.run_ppa_lane(fake_ppa(analysis), fake_gate(admitted, reasons), self.case, registration,
                                  None, None, self.case["rate"], self.timing, self.binding)

    def test_explicit_abstention_with_reasons_passes(self):
        lane = self.run_lane(fake_analysis(self.case, self.binding, self.timing), False, ["W1:window_inconclusive"])
        self.assertEqual(lane["branch"], "conditional_abstained")
        self.assertEqual(lane["verdict"], "passed")

    def test_refusal_without_reasons_is_incomplete_accounting(self):
        lane = self.run_lane(fake_analysis(self.case, self.binding, self.timing), False, [])
        self.assertEqual(lane["verdict"], "failed")
        self.assertIn("incomplete_conditional_accounting", [violation["kind"] for violation in lane["violations"]])

    def test_admission_without_all_obligations_is_false_conditional_admission(self):
        broken = admitted_analysis(self.case, self.binding, self.timing, holdout_status="training_fit_failed")
        lane = self.run_lane(broken, True, [])
        self.assertEqual(lane["verdict"], "failed")
        kinds = [violation["kind"] for violation in lane["violations"]]
        self.assertIn("false_conditional_static_admission", kinds)
        self.assertIn("holdout_status", kinds)

    def test_admission_with_wrong_index_is_false_claim(self):
        lines = meter.family_lines_of(self.case)
        numbers = [1, 2, 3, 4, max(lines) + 3]
        lane = self.run_lane(admitted_analysis(self.case, self.binding, self.timing, numbers=numbers), True, [])
        kinds = [violation["kind"] for violation in lane["violations"]]
        self.assertIn("wrong_index_claim", kinds)
        self.assertIn("false_conditional_static_admission", kinds)

    def test_timing_retention_and_integer_sample_bounds_are_independent_obligations(self):
        missing = fake_analysis(self.case, self.binding, self.timing)
        missing.pop("timing")
        lane = self.run_lane(missing, False, ["W1:window_inconclusive"])
        self.assertIn("timing_not_retained", [violation["kind"] for violation in lane["violations"]])
        mismatch = fake_analysis(self.case, self.binding, self.timing)
        mismatch["windows"]["W2"]["start_sample"] += 1
        lane = self.run_lane(mismatch, False, ["W1:window_inconclusive"])
        self.assertIn("window_sample_bound_mismatch", [violation["kind"] for violation in lane["violations"]])

    def test_ok_window_beyond_release_boundary_is_rejected(self):
        release = merged("dev-release-55-44100")
        binding = meter.expected_binding(release, registration)
        timing = meter.build_timing(release, registration, binding, "0" * 64)
        analysis = fake_analysis(release, binding, timing, statuses=("ok", "ok"))
        violations = meter.check_windows(analysis, release, binding)
        self.assertIn("ok_window_outside_bound_events", [violation["kind"] for violation in violations])

    def test_boundary_failure_is_preserved_per_window(self):
        release = merged("dev-release-55-44100")
        binding = meter.expected_binding(release, registration)
        good = fake_analysis(release, binding, timing := meter.build_timing(release, registration, binding, "0" * 64),
                             statuses=("ok", "failed"))
        good["windows"]["W2"]["stage"] = "bounds"
        self.assertEqual(meter.check_windows(good, release, binding), [])
        wrong_stage = copy.deepcopy(good)
        wrong_stage["windows"]["W2"]["stage"] = "spectrum"
        self.assertIn("boundary_window_stage", [violation["kind"] for violation in meter.check_windows(wrong_stage, release, binding)])
        clipped = copy.deepcopy(good)
        clipped["windows"]["W2"]["status"] = "ok"
        self.assertIn("boundary_window_status", [violation["kind"] for violation in meter.check_windows(clipped, release, binding)])


class InvalidTimingRefusal(unittest.TestCase):
    def test_invalid_binding_requires_refusal_not_clipping(self):
        case = merged("dev-invalid-timing-29-44100")
        binding = meter.expected_binding(case, registration)
        self.assertGreater(binding["note_off_sample"], binding["frames"])
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pcm").mkdir()
            refusing = types.SimpleNamespace(analyze_samples=lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("note_off_sample exceeds frames")))
            record = meter.run_case(None, refusing, None, registration, case, "development", Path(tmp), binding)
            self.assertEqual(record["ppa_lane"]["branch"], "input_refused")
            self.assertEqual(record["verdict"], "passed")
            self.assertEqual(record["observer_lane"]["verdict"], "skipped")
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "pcm").mkdir()
            accepting = types.SimpleNamespace(analyze_samples=lambda *args, **kwargs: fake_analysis(case, binding, kwargs["timing"]))
            record = meter.run_case(None, accepting, None, registration, case, "development", Path(tmp), binding)
            self.assertEqual(record["verdict"], "failed")
            self.assertIn("invalid_timing_not_refused", [violation["kind"] for violation in record["ppa_lane"]["violations"]])


class ObserverWindowInputContract(unittest.TestCase):
    """非法窗不进入候选或拟合；合法窗异常仍失败，拒绝本身不构成分音认证。"""

    def setUp(self):
        self.registration = copy.deepcopy(registration)
        self.registration["generator"]["windows"] = {"W1": [0.0, 0.1], "W2": [0.1, 0.3]}
        self.case = meter.merged_case({
            "id": "unit-observer-window", "kind": "frames_boundary", "note": 69, "rate": 44100,
            "b": 0.0003, "partials": 1, "expected_class": "positive", "admission_expectation": "rejected",
            "windows": list(meter.WINDOW_NAMES), "note_on_sample": 16,
            "note_off_seconds_after_note_on": 0.18, "frames_seconds_after_note_on": 0.2,
            "note_off_sample": 7954, "frames": 8836,
            "boundary": {"kind": "frames_boundary", "expected_stage": "spectrum",
                         "expected_windows": {"W1": "ok", "W2": "not_ok"}}},
            self.registration["generator"]["case_defaults"])
        self.binding = meter.expected_binding(self.case, self.registration)
        self.samples = np.zeros(self.case["frames"])
        start, stop = self.case["note_on_sample"], self.case["note_off_sample"]
        self.samples[start:stop] = 0.05 * np.cos(2.0 * np.pi * 440.0 * np.arange(stop - start) / self.case["rate"])

    def lane(self, case=None, left=None, right=None):
        case = self.case if case is None else case
        return meter.run_observer_lane(
            gate.ppa.observer, case, self.registration,
            self.samples if left is None else left, self.samples if right is None else right,
            case["rate"], meter.expected_binding(case, self.registration))

    def windows(self):
        return {name: {
            "bounds_s": list(value["relative"]), "start_sample": value["start"], "stop_sample": value["stop"],
            "samples": value["stop"] - value["start"], "frames": self.case["frames"],
            "coordinate": meter.TIMING_COORDINATE, "evidence_role": meter.EVIDENCE_ROLE,
            "source": "runner_window_bounds", "stage": "input",
            "status": "input_refused" if name == "W2" else "input_accepted",
            "reason": "window_exceeds_available_samples" if name == "W2" else None}
            for name, value in self.binding["windows"].items()}

    def test_candidate_bounds_are_strict_and_exact_end_keeps_the_peak(self):
        rate, count = 44100, 44100
        signal = 0.05 * np.cos(2.0 * np.pi * 440.0 * np.arange(count) / rate)
        for start, stop in ((-1, count), (0, count + 1), (1, 1)):
            with self.subTest(start=start, stop=stop), self.assertRaises(ValueError):
                meter.spectral_candidates(signal, signal, rate, start, stop, (400.0, 480.0), registration)
        candidates = meter.spectral_candidates(signal, signal, rate, 0, count, (400.0, 480.0), registration)
        self.assertLess(min(abs(row["hz"] - 440.0) for row in candidates), 0.005)

    def test_declared_invalid_window_is_refused_without_probes_or_certification(self):
        lane = self.lane()
        self.assertEqual(lane["windows"]["W2"]["status"], "input_refused")
        self.assertEqual(lane["windows"]["W2"]["stop_sample"], self.binding["windows"]["W2"]["stop"])
        self.assertGreater(lane["windows"]["W2"]["stop_sample"], lane["windows"]["W2"]["frames"])
        self.assertEqual({item["window"] for item in lane["probes"]}, {"W1"})
        self.assertEqual(meter.check_observer_windows(self.case, self.registration, lane["windows"], lane["probes"]), [])
        self.assertEqual(lane["verdict"], "failed")
        self.assertIn("single_line_not_certified", [item["kind"] for item in lane["violations"]])
        self.assertNotIn("observer_exception", [item["kind"] for item in lane["violations"]])

    def test_undeclared_bounds_or_wrong_PCM_length_cannot_be_expected_refusal(self):
        undeclared = copy.deepcopy(self.case)
        undeclared["boundary"] = None
        lane = self.lane(undeclared)
        self.assertEqual(lane["windows"]["W2"]["status"], "failed")
        self.assertIn("observer_window_refusal_contract", [item["kind"] for item in lane["violations"]])
        for left, right in ((self.samples[:-1], self.samples[:-1]), (self.samples, self.samples[:-1])):
            with self.assertRaises(ValueError):
                self.lane(left=left, right=right)

    def test_window_scoring_rejects_missing_clipped_and_forged_refusals(self):
        valid = self.windows()
        self.assertEqual(meter.check_observer_windows(self.case, self.registration, valid, []), [])
        for name, kind in (("missing", "observer_window_missing"),
                           ("clipped", "observer_window_binding"),
                           ("wrong_frames", "observer_window_binding"),
                           ("valid_refused", "observer_window_status"),
                           ("exception_hidden", "observer_window_error"),
                           ("scalar_claim", "observer_refusal_with_claim")):
            with self.subTest(name=name):
                windows = copy.deepcopy(valid)
                if name == "missing":
                    del windows["W2"]
                elif name == "clipped":
                    windows["W2"]["stop_sample"] = self.case["frames"]
                    windows["W2"]["samples"] = self.case["frames"] - windows["W2"]["start_sample"]
                elif name == "wrong_frames":
                    windows["W2"]["frames"] -= 1
                elif name == "valid_refused":
                    windows["W1"]["status"] = "input_refused"
                elif name == "exception_hidden":
                    windows["W2"]["error"] = "ValueError: injected unexpected failure"
                else:
                    windows["W2"]["frequency_hz"] = 440.0
                failures = meter.check_observer_windows(self.case, self.registration, windows, [])
                self.assertIn(kind, [item["kind"] for item in failures])
        missing = copy.deepcopy(self.case)
        missing["windows"] = ["W1"]
        failures = meter.check_observer_windows(missing, self.registration, {"W1": valid["W1"]}, [])
        self.assertIn("observer_refusal_coverage_missing", [item["kind"] for item in failures])

    def test_a_probe_on_a_refused_window_invalidates_the_refusal(self):
        item = {**probe(meter.STATUS_AMBIGUOUS), "window": "W2"}
        failures = meter.check_observer_windows(self.case, self.registration, self.windows(), [item])
        self.assertIn("observer_probe_without_valid_window", [row["kind"] for row in failures])

    def test_valid_window_observer_error_is_not_a_refusal(self):
        with mock.patch.object(gate.ppa.observer, "observe_partial", side_effect=ValueError("injected valid-window failure")):
            lane = self.lane()
        self.assertEqual(lane["verdict"], "failed")
        self.assertEqual(lane["windows"]["W1"]["status"], "input_accepted")
        self.assertIn("observer_exception", [item["kind"] for item in lane["violations"]])
        self.assertEqual({item["window"] for item in lane["probes"] if item["observer_error"]}, {"W1"})

    def test_registration_requires_cross_lane_coverage_and_actual_invalid_bounds(self):
        meter.check_case_design(self.case, self.registration)
        for mutation in ("missing_W2", "duplicate", "W1_not_ok", "not_rejected"):
            with self.subTest(mutation=mutation):
                case = copy.deepcopy(self.case)
                if mutation == "missing_W2":
                    case["windows"] = ["W1"]
                elif mutation == "duplicate":
                    case["windows"].append("W2")
                elif mutation == "W1_not_ok":
                    case["boundary"]["expected_windows"]["W1"] = "not_ok"
                else:
                    case["admission_expectation"] = "admitted"
                with self.assertRaises(SystemExit):
                    meter.check_case_design(case, self.registration)


class RegistrationValidation(unittest.TestCase):

    def test_overlapping_role_seed_or_recipe_is_rejected(self):
        for mutate in ("seed", "recipe"):
            broken = copy.deepcopy(registration)
            dev_case, qual_case = broken["cases"]["development"][0], broken["cases"]["qualification"][0]
            if mutate == "seed":
                qual_case["seed"] = dev_case["seed"]
            else:
                qual_case["kind"], qual_case["note"], qual_case["rate"] = dev_case["kind"], dev_case["note"], dev_case["rate"]
            with self.assertRaises(SystemExit):
                meter.validate_registration(broken)

    def test_diagnostic_obligation_and_duplicate_seed_are_rejected(self):
        broken = copy.deepcopy(registration)
        broken["cases"]["development"][0]["obligation"] = "diagnostic"
        with self.assertRaises(SystemExit):
            meter.validate_registration(broken)
        broken = copy.deepcopy(registration)
        broken["cases"]["development"][1]["seed"] = broken["cases"]["development"][0]["seed"]
        with self.assertRaises(SystemExit):
            meter.validate_registration(broken)

    def test_stop_policy_and_coverage_minimum_are_enforced(self):
        broken = copy.deepcopy(registration)
        broken["stop_policy"]["clauses"].pop("seal_consumed_by_one_complete_role")
        with self.assertRaises(SystemExit):
            meter.validate_registration(broken)
        broken = copy.deepcopy(registration)
        broken["coverage_requirements"]["minimum_required_admission_cases_per_role"] = 999
        with self.assertRaises(SystemExit):
            meter.validate_registration(broken)

    def test_execution_permissions_require_strict_booleans(self):
        for value in (None, 0, 1, "false"):
            for permission in ("approval", "development"):
                with self.subTest(value=value, permission=permission):
                    broken = copy.deepcopy(registration)
                    if permission == "approval":
                        broken["execution"]["approval"] = value
                    else:
                        broken["execution"]["development"]["authorized"] = value
                    with self.assertRaises(SystemExit):
                        meter.check_execution(broken)

    def test_comparison_expectations_must_be_complete_unique_objects(self):
        broken = copy.deepcopy(registration)
        broken["prospective_review"].pop("policy_expectations")
        with self.assertRaises(SystemExit):
            meter.validate_registration(broken)
        for review in (None, [], ["not-an-object"]):
            with self.subTest(review=review):
                broken = copy.deepcopy(registration)
                broken["prospective_review"] = review
                with self.assertRaises(SystemExit):
                    meter.validate_registration(broken)
        for entries in (None, {}, [], [None]):
            with self.subTest(entries=entries):
                broken = copy.deepcopy(registration)
                broken["prospective_review"]["policy_expectations"] = entries
                with self.assertRaises(SystemExit):
                    meter.validate_registration(broken)
        broken = copy.deepcopy(registration)
        entries = broken["prospective_review"]["policy_expectations"]
        entries.append(copy.deepcopy(entries[0]))
        with self.assertRaises(SystemExit):
            meter.validate_registration(broken)

    def test_malformed_or_unmatched_comparison_expectations_are_rejected(self):
        for field, value in (
                ("role", "control"), ("role", "development"), ("pair", "not-registered"), ("pair", ""),
                ("note", 22), ("rate", 48000), ("members", ["missing-a", "missing-b"]),
                ("members", ["same", "same"]), ("expected_state", "insufficient_comparable"),
                ("expected_base_partial", True), ("expected_comparable_partials", 5.0),
                ("expected_nonbase_count", 0), ("expected_nonbase_count", 3)):
            with self.subTest(field=field, value=value):
                broken = copy.deepcopy(registration)
                broken["prospective_review"]["policy_expectations"][0][field] = value
                with self.assertRaises(SystemExit):
                    meter.validate_registration(broken)
        broken = copy.deepcopy(registration)
        broken["prospective_review"]["policy_expectations"][0]["members"].reverse()
        with self.assertRaises(SystemExit):
            meter.validate_registration(broken)


    def test_unsupported_registration_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {**registration, "schema": "unsupported"}
            path = Path(tmp) / "registration.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(SystemExit):
                meter.load_registration(path)


class UnauthorizedQualification(unittest.TestCase):
    def setUp(self):
        self.argv = sys.argv
        self.addCleanup(lambda: setattr(sys, "argv", self.argv))
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.registration_path = Path(temporary.name) / "registration.json"
        self.registration_path.write_text(json.dumps(registration, ensure_ascii=False), encoding="utf-8")

    def run_main(self, *arguments):
        sys.argv = ["meter-qualification.py", *arguments]
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            with self.assertRaises(SystemExit) as raised:
                meter.main()
        return raised.exception.code, captured.getvalue()

    def test_qualification_is_refused_before_files_or_synthesis(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "qualification-out"
            with mock.patch.object(meter, "load_module", side_effect=AssertionError("模块加载必须发生在拒绝之后")), \
                 mock.patch.object(meter, "synthesize", side_effect=AssertionError("PCM 合成必须发生在拒绝之后")):
                code, message = self.run_main("--registration", str(self.registration_path), "--out", str(out), "--role", "qualification")
            self.assertNotEqual(code, 0)
            self.assertFalse(out.exists())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_development_is_refused_before_files_or_synthesis(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "development-out"
            with mock.patch.object(meter, "load_module", side_effect=AssertionError("未授权不得加载模块")), \
                 mock.patch.object(meter, "synthesize", side_effect=AssertionError("未授权不得合成PCM")):
                code, message = self.run_main("--registration", str(self.registration_path), "--out", str(out),
                                              "--role", "development")
            self.assertNotEqual(code, 0)
            self.assertFalse(out.exists())
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_qualification_with_missing_or_wrong_seal_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            approved = copy.deepcopy(registration)
            approved["execution"]["approval"] = True
            approved_path = Path(tmp) / "approved-registration.json"
            approved_path.write_text(json.dumps(approved, ensure_ascii=False), encoding="utf-8")
            out = Path(tmp) / "out"
            code, message = self.run_main("--registration", str(approved_path), "--out", str(out), "--role", "qualification")
            self.assertNotEqual(code, 0)
            self.assertFalse(out.exists())
            seal = Path(tmp) / "seal.json"
            seal.write_text(json.dumps({"role": meter.SEAL_ROLE, "files": {"wrong": "0" * 64}}), encoding="utf-8")
            code, message = self.run_main("--registration", str(approved_path), "--out", str(out), "--role", "qualification",
                                          "--seal", str(seal))
            self.assertNotEqual(code, 0)
            self.assertFalse(out.exists())
            self.assertFalse((Path(tmp) / "seal.json.consumed").exists())

    def test_check_registration_generates_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path.cwd()
            try:
                import os
                os.chdir(tmp)
                with mock.patch.object(meter, "load_module", side_effect=AssertionError("只读校验不得加载分析模块")), \
                     mock.patch.object(meter, "synthesize", side_effect=AssertionError("只读校验不得合成 PCM")):
                    code, message = self.run_main("--registration", str(self.registration_path), "--check-registration")
                self.assertEqual(code, 0)
                self.assertEqual(list(Path(tmp).iterdir()), [])
            finally:
                os.chdir(cwd)


class CrossCaseGates(unittest.TestCase):
    """角色内跨用例门禁：复用 repeat_quality / compare_analyses，失败即硬性违例。"""

    def setUp(self):
        # 只使用已消费的控制配方；新登记仅参与静态校验，不构造其观察或PCM。
        self.registration = copy.deepcopy(registration)
        self.registration["cases"] = copy.deepcopy(CONTROL_REGISTRATION["cases"])
        self.registration["prospective_review"]["policy_expectations"] = [
            {"role": "development", "pair": "dev-compare-83-48000", "note": 83, "rate": 48000,
             "members": ["dev-compare-83-48000-a", "dev-compare-83-48000-b"],
             "expected_state": "comparison_passed", "expected_base_partial": 5,
             "expected_comparable_partials": 4, "expected_nonbase_count": 3},
            {"role": "qualification", "pair": "qual-compare-90-44100", "note": 90, "rate": 44100,
             "members": ["qual-compare-90-44100-a", "qual-compare-90-44100-b"],
             "expected_state": "comparison_passed", "expected_base_partial": 5,
             "expected_comparable_partials": 8, "expected_nonbase_count": 7}]

    def member(self, case_id, numbers=None, f1=None, stiffness=None):
        case = merged(case_id)
        binding = meter.expected_binding(case, registration)
        timing = meter.build_timing(case, registration, binding, "0" * 64)
        analysis = admitted_analysis(case, binding, timing, numbers=numbers, f1=f1, stiffness=stiffness)
        return {"id": case_id, "role": "development", "recipe": case, "ppa_lane": {"analysis_record": analysis}}

    def test_repeat_group_and_comparison_pair_pass_when_realizations_agree(self):
        rows = [self.member("dev-repeat-71-48000-a"), self.member("dev-repeat-71-48000-b"),
                self.member("dev-compare-83-48000-a", numbers=[1, 2, 3, 4, 5, 6, 7, 8]),
                self.member("dev-compare-83-48000-b", numbers=[1, 2, 3, 4, 5, 6, 7, 8])]
        result = meter.evaluate_group_gates(gate, self.registration, rows)
        self.assertEqual(result["violations"], [])
        self.assertTrue(result["repeat_groups"][0]["admitted"])
        self.assertEqual(result["comparison_pairs"][0]["state"], "comparison_passed")
        self.assertTrue(result["comparison_pairs"][0]["output_obligation_satisfied"])

    def test_destabilized_repeat_realization_is_a_violation(self):
        case = merged("dev-repeat-71-48000-b")
        binding = meter.expected_binding(case, registration)
        timing = meter.build_timing(case, registration, binding, "0" * 64)
        shifted = admitted_analysis(case, binding, timing, f1=(meter.nominal(71) + 0.085) * 2.0 ** (2.0 / 1200.0))
        rows = [self.member("dev-repeat-71-48000-a"),
                {"id": "dev-repeat-71-48000-b", "recipe": case, "ppa_lane": {"analysis_record": shifted}}]
        result = meter.evaluate_group_gates(gate, self.registration, rows)
        self.assertFalse(result["repeat_groups"][0]["admitted"])
        self.assertEqual([violation["kind"] for violation in result["violations"]], ["repeat_group_not_admitted"])

    def test_comparison_requires_two_nonbase_partials_beyond_base(self):
        for numbers in ([1, 2, 3, 4, 5], [1, 2, 3, 5, 6]):
            with self.subTest(numbers=numbers):
                rows = [self.member("dev-compare-83-48000-a", numbers=numbers),
                        self.member("dev-compare-83-48000-b", numbers=numbers)]
                for row in rows:
                    self.assertTrue(gate.reference_quality(row["ppa_lane"]["analysis_record"])["admitted"])
                result = meter.evaluate_group_gates(gate, self.registration, rows)
                self.assertEqual(result["comparison_pairs"][0]["state"], "insufficient_comparable")
                self.assertEqual([violation["kind"] for violation in result["violations"]],
                                 ["comparison_pair_not_passed"])

    def test_missing_member_analysis_cannot_pass(self):
        rows = [self.member("dev-repeat-71-48000-a"),
                {"id": "dev-repeat-71-48000-b", "recipe": merged("dev-repeat-71-48000-b"), "ppa_lane": {}}]
        result = meter.evaluate_group_gates(gate, self.registration, rows)
        self.assertFalse(result["repeat_groups"][0]["admitted"])
        self.assertIn("incomplete_repeat_group", result["repeat_groups"][0]["reasons"])

    def comparison_rows(self):
        return [self.member("dev-compare-83-48000-a", numbers=list(range(1, 9))),
                self.member("dev-compare-83-48000-b", numbers=list(range(1, 9)))]

    def test_passed_comparison_with_wrong_registered_output_is_rejected(self):
        for changes in ({"expected_base_partial": 6},
                        {"expected_comparable_partials": 5, "expected_nonbase_count": 4}):
            with self.subTest(changes=changes):
                local = copy.deepcopy(self.registration)
                local["prospective_review"]["policy_expectations"][0].update(changes)
                result = meter.evaluate_group_gates(gate, local, self.comparison_rows())
                pair = result["comparison_pairs"][0]
                self.assertEqual(pair["state"], "comparison_passed")
                self.assertFalse(pair["output_obligation_satisfied"])
                self.assertEqual(set(pair["output_mismatches"]),
                                 {name.removeprefix("expected_") for name in changes})
                self.assertIn("comparison_pair_not_passed", [row["kind"] for row in result["violations"]])

    def test_missing_or_noninteger_output_cannot_satisfy_the_contract(self):
        for field, value in (("base_partial", None), ("comparable_partials", 4.0), ("base_partial", True)):
            with self.subTest(field=field, value=value):
                def faulty_comparison(*args):
                    output = gate.compare_analyses(*args)
                    output[field] = value
                    return output
                adapter = types.SimpleNamespace(repeat_quality=gate.repeat_quality, compare_analyses=faulty_comparison)
                result = meter.evaluate_group_gates(adapter, self.registration, self.comparison_rows())
                self.assertEqual(result["comparison_pairs"][0]["state"], "comparison_passed")
                self.assertFalse(result["comparison_pairs"][0]["output_obligation_satisfied"])
                self.assertIn("comparison_pair_not_passed", [row["kind"] for row in result["violations"]])

    def test_unmatched_runtime_role_or_members_cannot_pass(self):
        for change in ("role", "members"):
            with self.subTest(change=change):
                rows = self.comparison_rows()
                if change == "role":
                    rows[1]["role"] = "qualification"
                else:
                    rows[1]["id"] = "unregistered-member"
                result = meter.evaluate_group_gates(gate, self.registration, rows)
                self.assertFalse(result["comparison_pairs"][0]["output_obligation_satisfied"])
                self.assertIn("identity", result["comparison_pairs"][0]["output_mismatches"])

    def test_wrong_output_contract_prevents_qualification_outcome(self):
        rows = [self.member("dev-repeat-71-48000-a"), self.member("dev-repeat-71-48000-b"),
                *self.comparison_rows()]
        local = copy.deepcopy(self.registration)
        local["cases"] = {"qualification": [row["recipe"] for row in rows]}
        local["coverage_requirements"]["minimum_required_admission_cases_per_role"] = len(rows)
        local["regression_controls"] = [{"id": "control"}]
        for row in rows:
            row.update({"expected_class": "positive", "verdict": "passed",
                        "observer_lane": {"regions": [], "matched_claims": [], "violations": [], "interval": {}}})
            row["ppa_lane"].update({"branch": "required_admitted", "violations": [], "matched_lines": []})
        def score(group_result):
            return meter.summarize("qualification", rows, [{"id": "control", "verdict": "passed"}], local,
                                   {"registration": {"path": "memory-control", "sha256": "0" * 64}},
                                   None, 0.0, len(rows), group_result, {"passed": True})
        valid = meter.evaluate_group_gates(gate, self.registration, rows)
        self.assertEqual(score(valid)["outcome"], "qualified")
        local["prospective_review"]["policy_expectations"][0]["expected_base_partial"] = 6
        wrong = meter.evaluate_group_gates(gate, local, rows)
        self.assertEqual(wrong["comparison_pairs"][0]["state"], "comparison_passed")
        self.assertEqual(score(wrong)["outcome"], "not_qualified")


class PlanScopeAndOutcome(unittest.TestCase):
    def test_missing_method_gate_or_circular_capture_requirement_is_rejected(self):
        missing = copy.deepcopy(registration)
        missing["complete_plan_gates"]["required"] = [
            row for row in missing["complete_plan_gates"]["required"]
            if row["gate"] != "six_state_regression"]
        with self.assertRaises(SystemExit):
            meter.validate_registration(missing)
        circular = copy.deepcopy(registration)
        circular["complete_plan_gates"]["required"].append({
            "gate": "real_capture_and_formal_evaluation", "covered_by_registration": True})
        with self.assertRaises(SystemExit):
            meter.validate_registration(circular)

    def test_incomplete_role_controls_groups_or_failed_regression_never_qualify(self):
        local = copy.deepcopy(registration)
        definitions = [
            {"id": "a", "repeat_group": {"group": "repeat"}},
            {"id": "b", "repeat_group": {"group": "repeat"}},
            {"id": "c", "comparison_pair": {"pair": "comparison"}},
            {"id": "d", "comparison_pair": {"pair": "comparison"}}]
        local["cases"] = {"qualification": definitions}
        local["regression_controls"] = [{"id": "control"}]
        local["coverage_requirements"]["minimum_required_admission_cases_per_role"] = 4
        rows = [{"id": item["id"], "expected_class": "positive", "verdict": "passed",
                 "recipe": {"admission_expectation": "admitted"},
                 "ppa_lane": {"branch": "required_admitted", "violations": [], "matched_lines": []},
                 "observer_lane": {"regions": [], "matched_claims": [], "violations": [], "interval": {}}}
                for item in definitions]
        controls = [{"id": "control", "verdict": "passed"}]
        groups = {"repeat_groups": [{"group": "repeat"}],
                  "comparison_pairs": [{"pair": "comparison"}], "violations": []}
        identity = {"registration": {"path": "memory", "sha256": "0" * 64}}

        def score(records, control_rows, group_rows, regression_passed=True, aborted=None):
            return meter.summarize("qualification", records, control_rows, local, identity, aborted,
                                   0.0, 4, group_rows, {"passed": regression_passed})

        clean = score(rows, controls, groups)
        self.assertEqual(clean["outcome"], "qualified")
        self.assertFalse(clean["qualification_scope"]["full_v3_evaluation"])
        for name, result in (
                ("omitted_case", score(rows[:-1], controls, groups)),
                ("duplicate_case", score(rows[:3] + [rows[0]], controls, groups)),
                ("omitted_control", score(rows, [], groups)),
                ("omitted_groups", score(rows, controls, {"violations": []})),
                ("failed_regression", score(rows, controls, groups, regression_passed=False))):
            with self.subTest(name=name):
                self.assertEqual(result["outcome"], "not_qualified")
        self.assertEqual(score(rows, controls, groups, aborted="KeyboardInterrupt")["outcome"], "aborted")


if __name__ == "__main__":
    unittest.main()
