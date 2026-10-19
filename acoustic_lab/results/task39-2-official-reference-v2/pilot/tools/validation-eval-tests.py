#!/usr/bin/env python3
"""参考拒绝、留出充分性、重复组与归一化分类的纯内存回归；草案/未批准 v3 的执行门禁与准备报告回归。"""
import contextlib
import copy
import importlib.util
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("evaluation", Path(__file__).with_name("validation-eval.py"))
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


def observation(frequency):
    return {"status": "single_component_adequate", "frequency_hz": frequency,
            "interval_hz": [frequency - 0.001, frequency + 0.001]}


def family(numbers=range(1, 11), errors=(0.2, -0.3)):
    numbers = list(numbers)
    frequencies = [100.0 * n * math.sqrt((1 + 0.0001 * n * n) / 1.0001) for n in numbers]
    holdout = [numbers[1], numbers[-2]]
    details = [{"number": n, "predicted_Hz": 100.0 * n,
                "reidentified_Hz": 100.0 * n * 2.0 ** (e / 1200.0), "error_cents": e,
                "observation": observation(100.0 * n * 2.0 ** (e / 1200.0))}
               for n, e in zip(holdout, errors)]
    window = {"status": "ok", "partial_numbers": numbers, "observed_peak_Hz": frequencies,
              "partial_observations": {str(n): observation(f) for n, f in zip(numbers, frequencies)},
              "f1_Hz": 100.0, "effective_B": 0.0001,
              "independent_prediction": {"status": "ok", "training_size": len(numbers) - 2,
                                         "holdout_size": 2, "max_cents": 0.1,
                                         "rms_cents": 0.1, "details": details}}
    return {"windows": {"W1": copy.deepcopy(window), "W2": copy.deepcopy(window)}}


class ReferenceAdmission(unittest.TestCase):
    def test_excluded_multicomponent_candidate_rejects_the_whole_family_and_repeat(self):
        rows = [{"unit": "clean", "repeat": 0}, {"unit": "mixed", "repeat": 1}]
        for name in ("W1", "W2"):
            for number in (4, 9, 17):
                with self.subTest(window=name, excluded_partial=number):
                    data = family(n for n in range(1, 11) if n != number)
                    data["windows"][name]["partial_observations"][str(number)] = {
                        "status": "resolved_components", "frequency_hz": None, "interval_hz": None,
                        "components": [{"frequency_hz": 100.0 * number},
                                       {"frequency_hz": 100.0 * number + 1.7}]}
                    self.assertFalse(evaluation.reference_quality(data)["admitted"])
                    self.assertFalse(evaluation.repeat_quality(
                        rows, {"clean": family(), "mixed": data})["admitted"])

    def test_excluded_structural_abstention_rejects_the_whole_family(self):
        for reason in ("coherent_structure_outside_component_search_bounds",
                       "multiple_component_alternative_unresolved"):
            with self.subTest(reason=reason):
                data = family(n for n in range(1, 11) if n != 4)
                data["windows"]["W1"]["partial_observations"]["4"] = {
                    "status": "ambiguous", "frequency_hz": None,
                    "interval_hz": None, "reasons": [reason]}
                quality = evaluation.reference_quality(data)
                self.assertFalse(quality["admitted"])
                self.assertIn("W1:mixed_partial_observation", quality["reasons"])
                self.assertEqual(quality["windows"]["W1"]["mixed_partials"], ["4"])

    def test_excluded_abstention_or_missing_partial_does_not_establish_a_mixture(self):
        for status, reasons in ((None, None), ("ambiguous", []),
                                ("ambiguous", ["insufficient_local_signal_information"])):
            with self.subTest(excluded_status=status, reasons=reasons):
                data = family(n for n in range(1, 11) if n != 4)
                if status is not None:
                    data["windows"]["W1"]["partial_observations"]["4"] = {
                        "status": status, "frequency_hz": None, "interval_hz": None,
                        "reasons": reasons}
                self.assertTrue(evaluation.reference_quality(data)["admitted"])

    def test_model_ambiguity_and_wide_intervals_cannot_admit_a_static_family(self):
        for mutation in ("ambiguous", "wide", "missing", "heldout", "failed_window"):
            with self.subTest(mutation=mutation):
                data = family()
                window = data["windows"]["W1"]
                if mutation == "ambiguous":
                    window["partial_observations"]["7"]["status"] = "ambiguous"
                elif mutation == "wide":
                    window["partial_observations"]["7"]["interval_hz"] = [650.0, 750.0]
                elif mutation == "missing":
                    del window["partial_observations"]["7"]
                elif mutation == "heldout":
                    window["independent_prediction"]["details"][0]["observation"]["status"] = "ambiguous"
                else:
                    window["status"] = "failed"
                self.assertFalse(evaluation.reference_quality(data)["admitted"])

    def test_ok_status_and_small_reported_residual_do_not_override_observations(self):
        self.assertTrue(evaluation.reference_quality(family())["admitted"])
        for errors in ((2.0, 2.0), (0.0, 4.0)):
            with self.subTest(errors=errors):
                quality = evaluation.reference_quality(family(errors=errors))
                self.assertFalse(quality["admitted"])
                self.assertIn("W1:independent_prediction_error", quality["reasons"])

    def test_missing_or_duplicate_holdout_and_bad_late_window_are_rejected(self):
        for mutation in ("missing", "duplicate", "late_error", "late_absent", "nonfinite"):
            with self.subTest(mutation=mutation):
                data = family()
                details = data["windows"]["W1"]["independent_prediction"]["details"]
                if mutation == "missing":
                    details[1]["reidentified_Hz"] = None
                elif mutation == "duplicate":
                    details[1] = copy.deepcopy(details[0])
                elif mutation == "late_error":
                    data["windows"]["W2"] = family(errors=(2.0, -2.0))["windows"]["W2"]
                elif mutation == "late_absent":
                    del data["windows"]["W2"]
                else:
                    details[1]["reidentified_Hz"] = float("nan")
                self.assertFalse(evaluation.reference_quality(data)["admitted"])

    def test_window_frequency_and_stiffness_spread_reject_unstable_families(self):
        for key, factor, reason in (("f1_Hz", 2.0 ** (1.1 / 1200.0), "window_frequency_spread"),
                                    ("effective_B", 1.2, "window_B_spread")):
            data = family()
            data["windows"]["W2"][key] *= factor
            quality = evaluation.reference_quality(data)
            self.assertFalse(quality["admitted"])
            self.assertIn(reason, quality["reasons"])

    def test_repeat_missing_drift_or_rejected_partner_blocks_whole_family(self):
        rows = [{"unit": "r0", "repeat": 0}, {"unit": "r1", "repeat": 1}]
        good = {"r0": family(), "r1": family()}
        self.assertTrue(evaluation.repeat_quality(rows, good)["admitted"])
        self.assertFalse(evaluation.repeat_quality(rows, {"r0": family()})["admitted"])
        for mutation in ("f1", "B", "holdout", "missing_window"):
            with self.subTest(mutation=mutation):
                data = copy.deepcopy(good)
                if mutation == "f1":
                    for window in data["r1"]["windows"].values():
                        window["f1_Hz"] *= 2.0 ** (1.1 / 1200.0)
                elif mutation == "B":
                    for window in data["r1"]["windows"].values():
                        window["effective_B"] *= 1.2
                elif mutation == "holdout":
                    data["r1"] = family(errors=(2.0, -2.0))
                else:
                    del data["r1"]["windows"]["W1"]
                self.assertFalse(evaluation.repeat_quality(rows, data)["admitted"])


class ComparisonAccounting(unittest.TestCase):
    def compare(self, note, reference, dev):
        return evaluation.compare_analyses({"note": note, "unit": "u"}, reference, dev, 7)

    def test_monochord_low_only_families_and_multistring_boundary(self):
        for note in (21, 33, 35):
            with self.subTest(note=note):
                result = self.compare(note, family(range(1, 6)), family(range(1, 6)))
                self.assertEqual(result["state"], "comparison_passed")
                self.assertEqual(result["base_partial"], 1)
                self.assertEqual(result["nonbase_count"], 4)
        for note in (36, 47, 48, 71):
            with self.subTest(note=note):
                result = self.compare(note, family(range(1, 6)), family(range(1, 6)))
                self.assertEqual(result["state"], "insufficient_comparable")
                self.assertEqual(result["nonbase_count"], 0)

    def test_monochord_uses_only_common_observed_numbers(self):
        result = self.compare(33, family(range(1, 7)), family(range(2, 8)))
        self.assertEqual(result["state"], "comparison_passed")
        self.assertEqual(result["base_partial"], 2)
        self.assertEqual([row["partial"] for row in result["details"]], [3, 4, 5, 6])
        sparse = self.compare(33, family([1, 2, 3, 4, 5]), family([1, 2, 6, 7, 8]))
        self.assertEqual(sparse["state"], "insufficient_comparable")
        self.assertEqual(sparse["nonbase_count"], 1)

    def test_comparison_cannot_drop_excluded_mixtures_on_either_side(self):
        for note in (33, 67):
            for producer, state in (("reference", "reference_rejected"),
                                    ("devpiano", "insufficient_comparable")):
                for window in ("W1", "W2"):
                    with self.subTest(note=note, producer=producer, window=window):
                        reference, dev = family(), family()
                        target = reference if producer == "reference" else dev
                        target["windows"][window]["partial_observations"]["17"] = {
                            "status": "resolved_components", "frequency_hz": None, "interval_hz": None}
                        result = self.compare(note, reference, dev)
                        self.assertEqual(result["state"], state)
                        self.assertEqual(result["producer"], producer)

    def test_monochord_candidate_does_not_waive_family_sufficiency_or_late_window(self):
        for mutation in ("holdout", "late", "few"):
            with self.subTest(mutation=mutation):
                dev = family()
                if mutation == "holdout":
                    dev["windows"]["W1"]["independent_prediction"]["details"].pop()
                elif mutation == "late":
                    dev["windows"]["W2"]["f1_Hz"] *= 2 ** (2 / 1200)
                else:
                    dev = family(range(1, 5))
                self.assertEqual(self.compare(33, family(), dev)["state"], "insufficient_comparable")

    def test_zero_base_only_and_single_nonbase_are_all_insufficient(self):
        for numbers, expected in ((range(1, 6), 0), (range(1, 8), 0), (range(1, 9), 1)):
            with self.subTest(numbers=list(numbers)):
                result = self.compare(67, family(numbers), family(numbers))
                self.assertEqual(result["state"], "insufficient_comparable")
                self.assertEqual(result["nonbase_count"], expected)
        result = self.compare(67, family(range(1, 10)), family(range(1, 10)))
        self.assertEqual(result["state"], "comparison_passed")
        self.assertEqual(result["base_partial"], 7)
        self.assertEqual(result["nonbase_count"], 2)

    def test_comparable_register_boundary_and_base_normalization(self):
        self.assertEqual(self.compare(71, family(range(1, 8)), family(range(1, 8)))["state"],
                         "insufficient_comparable")
        for note, base in ((72, 5), (95, 5), (96, 1)):
            result = self.compare(note, family(range(1, 8)), family(range(1, 8)))
            self.assertEqual(result["state"], "comparison_passed")
            self.assertEqual(result["base_partial"], base)
        dev = family()
        dev["windows"]["W1"]["observed_peak_Hz"] = [f * 1.01 for f in dev["windows"]["W1"]["observed_peak_Hz"]]
        dev["windows"]["W1"]["partial_observations"] = {
            str(n): observation(f) for n, f in zip(dev["windows"]["W1"]["partial_numbers"],
                                                  dev["windows"]["W1"]["observed_peak_Hz"])}
        result = self.compare(67, family(), dev)
        self.assertEqual(result["state"], "comparison_passed")
        self.assertLess(result["norm_max"], 1e-9)
        dev["windows"]["W1"]["observed_peak_Hz"][-1] *= 2.0 ** (4.0 / 1200.0)
        last = str(dev["windows"]["W1"]["partial_numbers"][-1])
        dev["windows"]["W1"]["partial_observations"][last] = observation(dev["windows"]["W1"]["observed_peak_Hz"][-1])
        self.assertEqual(self.compare(67, family(), dev)["state"], "comparison_failed")

    def test_classified_boundaries_and_errors_cannot_inflate_totals(self):
        rows = []
        for i, numbers in enumerate((range(1, 6), range(1, 8), range(1, 9), range(1, 10))):
            result = self.compare(67, family(numbers), family(numbers))
            result["unit"] = str(i)
            rows.append(result)
        summary = evaluation.summarize(rows)
        self.assertEqual(summary["counts"]["insufficient_comparable"], 3)
        self.assertEqual(summary["counts"]["comparison_passed"], 1)
        self.assertEqual(summary["units"]["insufficient_comparable"], ["0", "1", "2"])
        with self.assertRaises(ValueError):
            evaluation.summarize(rows + [copy.deepcopy(rows[0])])
        with self.assertRaises(ValueError):
            evaluation.summarize([{"unit": "bad", "state": "unknown"}])


PILOT = Path(__file__).resolve().parents[1]
SHIPPED_DRAFT = PILOT / "validation-v3-preregistration.json"


class MethodEvidenceFixture:
    """构造独立临时证据文件；只测试认证与消费边界，从不执行夹具源码或资格。"""
    def __init__(self, directory):
        self.batch = Path(directory)
        self.output = self.batch / "qualification"
        self.output.mkdir(parents=True)
        self.report_path = self.output / "method-qualification-report.json"
        self.seal_path = self.batch / "qualification-seal.json"
        self.marker_path = self.batch / "qualification-seal.json.consumed"
        self.sources = {}
        identity = {}
        for key, name in evaluation.METHOD_SOURCES.items():
            live = Path(evaluation.__file__).with_name(name)
            snapshot = self.batch / "source-snapshot/pilot/tools" / name
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            snapshot.write_bytes(live.read_bytes())
            self.sources[key] = snapshot
            identity[key] = {"path": str(live.resolve()), "sha256": evaluation.sha256(snapshot)}
        live_registration = PILOT / "method-qualification-noteon-v3.json"
        snapshot = self.batch / "source-snapshot/pilot/method-qualification-noteon-v3.json"
        snapshot.write_bytes(live_registration.read_bytes())
        self.sources["registration"] = snapshot
        identity["registration"] = {"path": str(live_registration.resolve()),
                                    "sha256": evaluation.sha256(snapshot)}
        registration = json.loads(snapshot.read_text(encoding="utf-8"))
        defaults = registration["generator"]["case_defaults"]
        cases = [{**defaults, **row} for row in registration["cases"]["qualification"]]
        controls = [{**defaults, **row} for row in registration["regression_controls"]]
        def records(recipes, role):
            return [{"id": row["id"], "role": role, "verdict": "passed", "recipe": row,
                     "ppa_lane": {"branch": "required_admitted"
                                  if row["admission_expectation"] == "admitted" else "required_rejected"}}
                    for row in recipes]
        positive = sum(row["admission_expectation"] == "admitted" for row in cases)
        self.stdout, self.stderr = self.output / "regression.stdout", self.output / "regression.stderr"
        self.stdout.write_bytes(b"")
        self.stderr.write_bytes(b"fixture regression attestation\n")
        identity.update({"approval": True, "seal": {"path": str(self.seal_path)},
                         "consumption_marker": str(self.marker_path)})
        self.report = {
            "schema": evaluation.METHOD_SCHEMA, "role": "qualification", "status": "complete",
            "identity": identity,
            "qualification_scope": {"scope": evaluation.METHOD_SCOPE, "full_v3_evaluation": False},
            "cases": records(cases, "qualification"),
            "regression_controls": records(controls, "regression_control"),
            "cross_case_gates": {
                "violations": [],
                "repeat_groups": [{"group": name, "admitted": True} for name in sorted({
                    row["repeat_group"]["group"] for row in cases if row.get("repeat_group")})],
                "comparison_pairs": [{"pair": name, "state": "comparison_passed"} for name in sorted({
                    row["comparison_pair"]["pair"] for row in cases if row.get("comparison_pair")})]},
            "summary": {
                "role": "qualification", "outcome": "qualified", "aborted": None,
                "pass_conditions": dict.fromkeys(evaluation.METHOD_PASS_CONDITIONS, True),
                "complete_role": {"complete": True, "expected_cases": len(cases),
                                  "executed_cases": len(cases)},
                "cases_failed": [], "controls_violated": [],
                "positive_coverage": {"satisfied": True, "cases_expected": positive,
                                      "cases_verified_admitted": positive},
                "evaluator_regression": {
                    "passed": True, "exit_code": 0,
                    "script_sha256": identity["evaluator_regression_script"]["sha256"],
                    "stdout": self.stdout.name, "stdout_sha256": evaluation.sha256(self.stdout),
                    "stderr": self.stderr.name, "stderr_sha256": evaluation.sha256(self.stderr)}}}
        self.seal = {"role": "method_qualification_noteon_v3",
                     "files": {row["path"]: row["sha256"] for row in identity.values()
                               if isinstance(row, dict) and "sha256" in row}}
        self.marker = {"role": self.seal["role"], "role_run": "qualification",
                       "seal": str(self.seal_path), "out": str(self.output),
                       "registration_sha256": identity["registration"]["sha256"],
                       "runner_sha256": identity["qualification_script"]["sha256"]}
        self.commit()

    def commit(self):
        for path, document in ((self.seal_path, self.seal), (self.marker_path, self.marker)):
            path.write_text(json.dumps(document), encoding="utf-8")
        self.report["identity"]["seal"]["sha256"] = evaluation.sha256(self.seal_path)
        self.report_path.write_text(json.dumps(self.report), encoding="utf-8")
        members = [self.report_path, self.seal_path, self.marker_path, self.stdout, self.stderr,
                   *self.sources.values()]
        manifest = {"files": [{"dst_win": str(path.resolve()), "sha256": evaluation.sha256(path),
                               "verified": True} for path in members],
                    "totals": {"files": len(members), "verified": len(members),
                               "missing": 0, "mismatch": 0}}
        manifest_path = self.batch / "evidence-manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        self.evidence = {"canonical_report": str(self.report_path),
                         "report_sha256": evaluation.sha256(self.report_path),
                         "manifest_sha256": evaluation.sha256(manifest_path),
                         "seal_sha256": evaluation.sha256(self.seal_path),
                         "consumption_marker_sha256": evaluation.sha256(self.marker_path)}


class CompletedMethodEvidence(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fixture = MethodEvidenceFixture(Path(temporary.name) / "batch")

    def test_valid_consumed_proof_is_verified_for_its_actual_snapshot(self):
        result = evaluation.verify_completed_method_evidence(self.fixture.evidence)
        self.assertTrue(result["verified"], result["reasons"])
        self.assertEqual(result["outcome"], "qualified")
        self.assertEqual(result["scope"], evaluation.METHOD_SCOPE)
        self.assertTrue(result["current_sources_match"])

    def test_unrelated_input_path_is_refused_before_reading_its_bytes(self):
        evidence = {**self.fixture.evidence, "canonical_report": str(self.fixture.batch / "input.wav")}
        with patch.object(Path, "read_bytes", side_effect=AssertionError("producer bytes reached")):
            result = evaluation.verify_completed_method_evidence(evidence)
        self.assertFalse(result["verified"])

    def test_valid_original_snapshot_does_not_qualify_changed_current_dependencies(self):
        fixture = self.fixture
        snapshot = fixture.sources["evaluator"]
        snapshot.write_bytes(snapshot.read_bytes() + b"\n# original snapshot variant\n")
        identity = fixture.report["identity"]["evaluator"]
        identity["sha256"] = evaluation.sha256(snapshot)
        fixture.seal["files"][identity["path"]] = identity["sha256"]
        fixture.commit()
        result = evaluation.verify_completed_method_evidence(fixture.evidence)
        self.assertTrue(result["verified"], result["reasons"])
        self.assertFalse(result["current_sources_match"])
        self.assertEqual([row["dependency"] for row in result["identity_differences"]], ["evaluator"])
        data = fully_flipped_preregistration()
        data["qualification"] = {"completed_method_evidence": fixture.evidence}
        report = evaluation.plan_report(data, SHIPPED_DRAFT)
        self.assertTrue(report["method_qualification"]["completed_evidence"]["verified"])
        self.assertFalse(report["method_qualification"]["current_snapshot_qualified"])
        self.assertIn("method_qualification:current_snapshot_changed", report["blockers"])

    def test_artifact_hashes_and_missing_consumption_are_enforced(self):
        for key in ("report_sha256", "manifest_sha256", "seal_sha256", "consumption_marker_sha256"):
            with self.subTest(key=key):
                evidence = {**self.fixture.evidence, key: "0" * 64}
                self.assertFalse(evaluation.verify_completed_method_evidence(evidence)["verified"])
        self.fixture.marker_path.unlink()
        self.assertFalse(evaluation.verify_completed_method_evidence(self.fixture.evidence)["verified"])

    def test_self_declared_qualification_without_proof_is_not_authority(self):
        result = evaluation.verify_completed_method_evidence({"outcome": "qualified", "status": "qualified"})
        self.assertFalse(result["verified"])
        report = evaluation.plan_report(fully_flipped_preregistration(), SHIPPED_DRAFT)
        self.assertFalse(report["method_qualification"]["current_snapshot_qualified"])
        self.assertIn("method_qualification:evidence_not_verified", report["blockers"])

    def test_resealed_wrong_role_scope_or_incomplete_attestation_is_rejected(self):
        original = copy.deepcopy(self.fixture.report)
        mutations = (
            lambda r: r.update(role="development"),
            lambda r: r["qualification_scope"].update(scope="real_reference_origin"),
            lambda r: r["summary"].update(outcome="not_qualified"),
            lambda r: r["cases"].pop(),
            lambda r: r["cases"].append(copy.deepcopy(r["cases"][0])),
            lambda r: r["regression_controls"].pop(),
            lambda r: r["cross_case_gates"]["repeat_groups"].clear(),
            lambda r: r["cross_case_gates"]["comparison_pairs"][0].update(state="comparison_failed"),
            lambda r: r["summary"]["evaluator_regression"].update(passed=False),
            lambda r: r["summary"]["pass_conditions"].update(controls_clean=False),
        )
        for mutation in mutations:
            with self.subTest(mutation=mutations.index(mutation)):
                self.fixture.report = copy.deepcopy(original)
                mutation(self.fixture.report)
                self.fixture.commit()
                self.assertFalse(evaluation.verify_completed_method_evidence(self.fixture.evidence)["verified"])

    def test_consumed_role_and_snapshot_bytes_cannot_be_substituted(self):
        self.fixture.marker["role_run"] = "development"
        self.fixture.commit()
        self.assertFalse(evaluation.verify_completed_method_evidence(self.fixture.evidence)["verified"])
        self.fixture.marker["role_run"] = "qualification"
        original_output = self.fixture.marker["out"]
        self.fixture.marker["out"] = str(self.fixture.batch / "another-run")
        self.fixture.commit()
        self.assertFalse(evaluation.verify_completed_method_evidence(self.fixture.evidence)["verified"])
        self.fixture.marker["out"] = original_output
        self.fixture.sources["analysis_tool"].write_bytes(b"changed snapshot")
        self.fixture.commit()
        self.assertFalse(evaluation.verify_completed_method_evidence(self.fixture.evidence)["verified"])

    def test_valid_method_evidence_does_not_override_v3_formal_readiness(self):
        data = fully_flipped_preregistration()
        data["qualification"] = {"completed_method_evidence": self.fixture.evidence}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frequency.json"
            path.write_text(json.dumps({"limits": {"v3_formal_method_ready": False}}), encoding="utf-8")
            data["contracts"] = {"frequency_observable": {"path": str(path)}}
            report = evaluation.plan_report(data, SHIPPED_DRAFT)
        self.assertTrue(report["method_qualification"]["current_snapshot_qualified"])
        self.assertIn("v3_formal_method_not_ready", report["blockers"])
        self.assertFalse(report["execution_allowed"])


def draft_preregistration(**changes):
    """与 pilot/validation-v3-preregistration.json 同形状的内存草案；不含任何通过/失败数字。"""
    data = {
        "schema": evaluation.V3_SCHEMA,
        "status": "draft_pending_review",
        "contracts": {},
        "authorizations": {key: False for key in evaluation.V3_REQUIRED_AUTHORIZATIONS},
        "unresolved_prerequisites": [{"id": "method_qualification", "current": "not_qualified"}],
        "qualification": {},
        "reference_origin": {"status": "requires_authenticated_export_origin_before_v3_freeze"},
        "evaluation": {"matrix": None, "velocities": None},
        "entry_gate_frozen": {"preregistered_before_any_rendering_or_inspection": False,
                              "analysis_tool": {"sha256": None}, "evaluator": {"sha256": None},
                              "partial_observer": {"sha256": None}},
    }
    data.update(changes)
    return data


def fully_flipped_preregistration():
    """伪造 frozen 状态并把声明前提全部翻绿；用于验证门禁仍要求真实绑定与契约。"""
    data = draft_preregistration(status=evaluation.EXECUTABLE_STATUS, unresolved_prerequisites=[],
                                 qualification={"status": "qualified"},
                                 reference_origin={"status": "authenticated"})
    data["authorizations"] = {key: True for key in evaluation.V3_REQUIRED_AUTHORIZATIONS}
    data["evaluation"] = {"matrix": [{"note": 69, "rate": 48000, "repeat": 0, "session": "s"}]}
    data["entry_gate_frozen"]["preregistered_before_any_rendering_or_inspection"] = True
    return data


def run_cli(argv, trap_file_reads=True):
    """运行 main() 并隔离音频分析与（可选）文件散列调用；返回 (退出码, stdout, stderr)。"""
    original_argv = sys.argv
    original_analyze = evaluation.ppa.analyze_unit
    original_sha256 = evaluation.sha256

    def trap(*_args, **_kwargs):
        raise AssertionError("gate let the run reach audio or tool inputs")

    sys.argv = ["validation-eval.py"] + list(argv)
    evaluation.ppa.analyze_unit = trap
    if trap_file_reads:
        evaluation.sha256 = trap
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                evaluation.main()
                code = 0
            except SystemExit as signal:
                code = signal.code
    finally:
        sys.argv = original_argv
        evaluation.ppa.analyze_unit = original_analyze
        evaluation.sha256 = original_sha256
    return code, stdout.getvalue(), stderr.getvalue()


class PreregistrationGate(unittest.TestCase):
    """草案/未批准 v3 在任何音频或输出之前被拒绝；--diagnostic-only 不是 v3 绕过。"""

    def test_non_frozen_status_is_refused_for_v3_and_for_existing_schemas(self):
        for schema in (evaluation.V3_SCHEMA, "devpiano-task39-2-preregistration-validation-interp2"):
            for status in ("draft_pending_review", "draft_pending_user_approval", "approved", None):
                with self.subTest(schema=schema, status=status):
                    blockers = evaluation.execution_blockers({"schema": schema, "status": status})
                    self.assertIn(f"status:{status}", blockers)

    def test_frozen_non_v3_status_remains_executable_under_the_gate(self):
        for schema in ("devpiano-task39-2-preregistration-validation-interp",
                       "devpiano-task39-2-preregistration-validation-interp2"):
            with self.subTest(schema=schema):
                self.assertEqual(evaluation.execution_blockers(
                    {"schema": schema, "status": evaluation.EXECUTABLE_STATUS}), [])

    def test_forged_frozen_status_alone_does_not_authorize_a_run(self):
        for data, expected in (
                (draft_preregistration(status=evaluation.EXECUTABLE_STATUS),
                 ("unresolved_prerequisites", "matrix_not_selected",
                  "entry_gate_not_frozen_before_rendering",
                  "reference_origin:requires_authenticated_export_origin_before_v3_freeze")),
                (draft_preregistration(status=evaluation.EXECUTABLE_STATUS, authorizations=None),
                 ("authorizations:missing",)),
                (draft_preregistration(status=evaluation.EXECUTABLE_STATUS, authorizations={}),
                 tuple(f"authorization:{key}" for key in evaluation.V3_REQUIRED_AUTHORIZATIONS))):
            with self.subTest(expected=expected[0]):
                blockers = evaluation.execution_blockers(data)
                for entry in expected:
                    self.assertIn(entry, blockers)

    def test_each_required_authorization_is_enforced_individually(self):
        self.assertEqual(evaluation.execution_blockers(fully_flipped_preregistration()), [])
        for key in evaluation.V3_REQUIRED_AUTHORIZATIONS:
            with self.subTest(key=key):
                data = fully_flipped_preregistration()
                data["authorizations"][key] = False
                self.assertIn(f"authorization:{key}", evaluation.execution_blockers(data))



class PlanReport(unittest.TestCase):
    """check-plan 只报告准备阻塞；不读音频、不写输出、不声称就绪或冻结。"""

    def test_report_never_claims_readiness_and_flags_unbound_tools(self):
        report = evaluation.plan_report(fully_flipped_preregistration(), SHIPPED_DRAFT)
        self.assertTrue(report["preparation_only"])
        self.assertFalse(report["readiness_or_freeze_asserted"])
        self.assertFalse(report["execution_allowed"])
        for name in ("analysis_tool", "evaluator", "partial_observer"):
            self.assertIn(f"tool_identity_unbound:{name}", report["blockers"])


    def test_missing_declared_contract_is_reported_as_a_blocker(self):
        data = draft_preregistration()
        data["contracts"] = {"frequency_observable": {"path": "pilot/no-such-contract-v3.json",
                                                      "sha256": None}}
        report = evaluation.plan_report(data, SHIPPED_DRAFT)
        self.assertIn("contract_missing:frequency_observable", report["blockers"])
        self.assertFalse(report["contracts"][0]["present"])
        self.assertFalse(report["execution_allowed"])

    def test_declared_contract_digest_mismatch_is_a_blocker(self):
        data = draft_preregistration()
        data["contracts"] = {"input_render": {"path": "pilot/input-render-contract-v3.json",
                                              "sha256": "0" * 64}}
        report = evaluation.plan_report(data, SHIPPED_DRAFT)
        self.assertIn("contract_hash_mismatch:input_render", report["blockers"])



class PreregistrationCli(unittest.TestCase):
    """CLI 层面的拒绝与准备报告：不读音频、不写输出、不覆盖既有证据。"""

    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary.cleanup)
        self.tmp = Path(self._temporary.name)
        self.prereg = self.tmp / "draft.json"
        self.prereg.write_text(json.dumps(draft_preregistration()))
        self.out = self.tmp / "result.json"
        self.reference = self.tmp / "reference"
        self.dev = self.tmp / "dev"
        self.reference.mkdir()
        self.dev.mkdir()
        (self.reference / "sentinel.wav").write_bytes(b"must never be read")
        self.entries = ["dev", "draft.json", "reference"]

    def evaluation_argv(self, prereg=None):
        return ["--preregistration", str(prereg or self.prereg), "--reference-batch", str(self.reference),
                "--dev-render", str(self.dev), "--out", str(self.out)]

    def test_draft_evaluation_is_refused_before_audio_or_output(self):
        for extra in ([], ["--diagnostic-only"]):
            with self.subTest(extra=extra):
                code, _, stderr = run_cli(self.evaluation_argv() + extra)
                self.assertNotEqual(code, 0)
                self.assertFalse(self.out.exists())
                self.assertEqual(sorted(entry.name for entry in self.tmp.iterdir()), self.entries)

    def test_forged_frozen_draft_is_refused_before_audio_or_output(self):
        forged = self.tmp / "forged.json"
        forged.write_text(json.dumps(draft_preregistration(status=evaluation.EXECUTABLE_STATUS)))
        code, _, stderr = run_cli(self.evaluation_argv(forged) + ["--diagnostic-only"])
        self.assertNotEqual(code, 0)
        self.assertFalse(self.out.exists())

    def test_frozen_v3_cannot_bypass_a_conflicting_contract(self):
        data = fully_flipped_preregistration()
        frequency = self.tmp / "frequency.json"
        frequency.write_text(json.dumps({"limits": {"v3_formal_method_ready": False}}))
        timing = self.tmp / "timing.json"
        timing.write_text(json.dumps({"reference_origin": {"status": "not_authenticated"}}))
        data["contracts"] = {"frequency_observable": {"path": str(frequency)},
                             "input_render": {"path": str(timing)}}
        for name, digest in evaluation.actual_tool_hashes().items():
            data["entry_gate_frozen"][name] = {"sha256": digest}
        forged = self.tmp / "conflicting-contract.json"
        forged.write_text(json.dumps(data))
        for extra in ([], ["--diagnostic-only"]):
            with self.subTest(extra=extra):
                code, _, stderr = run_cli(self.evaluation_argv(forged) + extra,
                                           trap_file_reads=False)
                self.assertEqual(code, 2)
                self.assertFalse(self.out.exists())

    def test_utf8_protocol_and_contract_are_read_independently_of_windows_locale(self):
        contract = self.tmp / "utf8-contract.json"
        contract.write_text(json.dumps({"reference_origin": {"status": "not_authenticated"},
                                         "description": "\u266f"}, ensure_ascii=False),
                            encoding="utf-8-sig")
        data = draft_preregistration()
        data["description"] = "\u266f"
        data["contracts"] = {"input_render": {"path": str(contract)}}
        self.prereg.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8-sig")
        code, stdout, _ = run_cli(["--check-plan", "--preregistration", str(self.prereg)],
                                  trap_file_reads=False)
        self.assertEqual(code, evaluation.PLAN_BLOCKED_EXIT)
        report = json.loads(stdout)
        self.assertFalse(report["execution_allowed"])
        self.assertEqual(report["cross_check"]["contract_reference_origin_status"], "not_authenticated")

    def test_check_plan_reports_blocked_plan_without_outputs(self):
        code, stdout, stderr = run_cli(["--check-plan", "--preregistration", str(self.prereg)],
                                       trap_file_reads=False)
        self.assertEqual(code, evaluation.PLAN_BLOCKED_EXIT)
        report = json.loads(stdout)
        self.assertTrue(report["preparation_only"])
        self.assertFalse(report["execution_allowed"])
        self.assertFalse(report["readiness_or_freeze_asserted"])
        self.assertTrue(report["blockers"])
        self.assertFalse(self.out.exists())
        self.assertEqual(sorted(entry.name for entry in self.tmp.iterdir()), self.entries)

    def test_check_plan_accepts_no_producer_inputs_or_diagnostic_role(self):
        for extra in (["--out", str(self.out)], ["--reference-batch", str(self.reference)],
                      ["--dev-render", str(self.dev)], ["--diagnostic-only"]):
            with self.subTest(extra=extra):
                code, _, stderr = run_cli(["--check-plan", "--preregistration", str(self.prereg)] + extra,
                                          trap_file_reads=False)
                self.assertNotEqual(code, 0)
                self.assertFalse(self.out.exists())

    def test_frozen_protocol_still_requires_explicit_producer_inputs(self):
        frozen = self.tmp / "frozen.json"
        frozen.write_text(json.dumps({"schema": "devpiano-task39-2-preregistration-validation-interp2",
                                      "status": evaluation.EXECUTABLE_STATUS}))
        code, _, stderr = run_cli(["--preregistration", str(frozen)])
        self.assertNotEqual(code, 0)
        self.assertFalse(self.out.exists())

    def test_existing_output_protection_still_fires_before_any_input_read(self):
        self.out.write_text("previous evidence")
        frozen = self.tmp / "frozen.json"
        frozen.write_text(json.dumps({"schema": "devpiano-task39-2-preregistration-validation-interp2",
                                      "status": evaluation.EXECUTABLE_STATUS}))
        code, _, stderr = run_cli(self.evaluation_argv(frozen))
        self.assertNotEqual(code, 0)
        self.assertEqual(self.out.read_text(), "previous evidence")


class V3TimingBinding(unittest.TestCase):
    def test_missing_bound_timing_cannot_fall_back_to_absolute_analysis(self):
        with patch.object(evaluation.ppa, "analyze_unit",
                          side_effect=AssertionError("unsafe audio analysis reached")):
            for producer in ("reference", "devpiano"):
                with self.subTest(producer=producer), self.assertRaisesRegex(
                        ValueError, "Missing bound NoteOn"):
                    evaluation.analyze_registered_input(
                        Path("unused.wav"), 69, {"schema": evaluation.V3_SCHEMA}, "unit", producer)

    def test_changed_timing_evidence_is_rejected_before_audio_analysis(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "timing.json"
            report.write_text("{}", encoding="utf-8")
            prereg = {"schema": evaluation.V3_SCHEMA,
                      "timing_evidence": {"devpiano": {"unit": {"path": str(report),
                                                                  "sha256": "0" * 64}}}}
            with patch.object(evaluation.ppa, "analyze_unit",
                              side_effect=AssertionError("unsafe audio analysis reached")):
                with self.assertRaisesRegex(ValueError, "Timing-evidence hash mismatch"):
                    evaluation.analyze_registered_input(Path("unused.wav"), 69, prereg, "unit", "devpiano")

    def test_dev_timing_report_cannot_authorize_a_reference_origin(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "timing.json"
            report.write_text("{}", encoding="utf-8")
            binding = {"path": str(report), "sha256": evaluation.sha256(report)}
            prereg = {"schema": evaluation.V3_SCHEMA, "timing_evidence": {"reference": {"unit": binding}}}
            with patch.object(evaluation.ppa, "load_timing_report",
                              return_value={"coordinate": "note_on_relative",
                                            "evidence_role": "dev_render_verification"}):
                with patch.object(evaluation.ppa, "analyze_unit",
                                  side_effect=AssertionError("unsafe audio analysis reached")):
                    with self.assertRaisesRegex(ValueError, "cannot authorize reference"):
                        evaluation.analyze_registered_input(Path("unused.wav"), 69, prereg, "unit", "reference")


class V3ReferenceTiming(unittest.TestCase):
    """A5 reference-origin 角色可授权 reference，且不能改标为 dev，也不能绕过绑定散列。"""

    @staticmethod
    def binding(report):
        return {"path": str(report), "sha256": evaluation.sha256(report)}

    def test_reference_timing_report_authorizes_reference_producer(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "timing.json"
            report.write_text("{}", encoding="utf-8")
            prereg = {"schema": evaluation.V3_SCHEMA,
                      "timing_evidence": {"reference": {"unit": self.binding(report)}}}
            timing = {"coordinate": "note_on_relative",
                      "evidence_role": "reference_origin_authenticated"}
            with patch.object(evaluation.ppa, "load_timing_report", return_value=timing):
                with patch.object(evaluation.ppa, "analyze_unit", return_value={"accepted": True}) as analyze:
                    result = evaluation.analyze_registered_input(
                        Path("unused.wav"), 69, prereg, "unit", "reference")
        self.assertEqual(result, {"accepted": True})
        analyze.assert_called_once()

    def test_reference_timing_role_cannot_authorize_devpiano(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "timing.json"
            report.write_text("{}", encoding="utf-8")
            prereg = {"schema": evaluation.V3_SCHEMA,
                      "timing_evidence": {"devpiano": {"unit": self.binding(report)}}}
            timing = {"coordinate": "note_on_relative",
                      "evidence_role": "reference_origin_authenticated"}
            with patch.object(evaluation.ppa, "load_timing_report", return_value=timing):
                with patch.object(evaluation.ppa, "analyze_unit",
                                  side_effect=AssertionError("unsafe audio analysis reached")):
                    with self.assertRaisesRegex(ValueError, "cannot authorize devpiano"):
                        evaluation.analyze_registered_input(
                            Path("unused.wav"), 69, prereg, "unit", "devpiano")

    def test_plan_report_exposes_the_reference_timing_verifier(self):
        self.assertIn("reference_origin_authenticated", evaluation.ppa.SUPPORTED_EVIDENCE_ROLES)
        report = evaluation.plan_report(fully_flipped_preregistration(), SHIPPED_DRAFT)
        self.assertTrue(report["reference_timing_verifier_available"])
        self.assertNotIn("reference_timing_verifier_not_available", report["blockers"])


if __name__ == "__main__":
    unittest.main()
