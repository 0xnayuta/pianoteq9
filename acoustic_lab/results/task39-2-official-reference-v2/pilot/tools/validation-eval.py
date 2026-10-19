#!/usr/bin/env python3
"""后继批次对照评估：参考族数值准入、完整分类与冻结依赖门禁（只读输入）。

已消耗批次只允许显式 --diagnostic-only 输出；方法资格修订不改写历史判决。
矩阵与条件仍读取原预登记，参考族不足不得进入生产者误差的通过统计。
草案/未批准 v3 预登记（如 pilot/validation-v3-preregistration.json）在任何音频读取或输出写入前
被拒绝，--diagnostic-only 不是 v3 绕过；即使伪造 frozen 状态，缺少授权、未选矩阵、未解决前提、
未绑定工具身份或资格/参考来源未认证仍不可执行。

判据（原数值预算与整族门禁保持）：
- 两侧完整族均准入后，单弦 MIDI21–35 允许 n>=1 候选；
- 多弦 MIDI36–71 用 n>=min_comparable_below_72，72–95 用 n>=5，>=96 用 n>=1；
- 基准 m = 可比较集最小共同分音，不计入样本；
- err(n) = 1200 * log2( (dev(n)/dev(m)) / (ref(n)/ref(m)) )；
- 判据：RMS(err) <= 1 cent 且 max|err| <= 3 cents，且非基准样本 >= 2。

用法：
  python3 validation-eval.py --preregistration <prereg.json> \
    --reference-batch <batch root> --dev-render <render root> --out <result.json> \
    [--refinement-guard-db 20|off] [--diagnostic-only]
  python3 validation-eval.py --check-plan --preregistration <prereg.json>

--check-plan 为准备级模式：只读预登记与声明的契约文件，报告真实阻塞，不读生产者输入、不写输出、
不声称就绪或冻结；存在阻塞时退出码 3。
"""

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parents[2]
ANALYSIS_TOOL = str(BASE / "pilot/tools/pilot-partial-analysis.py")

spec = importlib.util.spec_from_file_location("ppa", ANALYSIS_TOOL)
ppa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ppa)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


STATES = ("missing_input", "analysis_error", "reference_rejected",
          "insufficient_comparable", "comparison_failed", "comparison_passed")

EXECUTABLE_STATUS = "frozen_before_validation_rendering_or_inspection"
V3_SCHEMA = "devpiano-task39-2-preregistration-validation-v3"
V3_REQUIRED_AUTHORIZATIONS = ("protocol_approved", "matrix_approved", "capture_authorized",
                              "freeze_authorized", "formal_evaluation_authorized")
PLAN_BLOCKED_EXIT = 3
METHOD_SCHEMA = "devpiano-task39-2-method-qualification-noteon-v3"
METHOD_SCOPE = "complete_method_in_registered_synthetic_domain"
METHOD_SOURCES = {
    "qualification_script": "meter-qualification.py",
    "analysis_tool": "pilot-partial-analysis.py",
    "observer": "partial-observer.py",
    "evaluator": "validation-eval.py",
    "evaluator_regression_script": "validation-eval-tests.py",
}
METHOD_PASS_CONDITIONS = (
    "complete_registered_role", "complete_controls", "complete_group_gates",
    "evaluator_regression_passed", "no_failed_gating_cases", "controls_clean",
    "positive_coverage_satisfied", "repeat_groups_admitted", "comparison_pairs_passed",
)


def finite(value):
    return (isinstance(value, (int, float, np.integer, np.floating))
            and not isinstance(value, bool) and math.isfinite(value))


def actual_tool_hashes():
    return {"analysis_tool": sha256(ANALYSIS_TOOL), "evaluator": sha256(__file__),
            "partial_observer": sha256(ppa.OBSERVER_PATH)}


def bound_digest(entry_gate, name):
    entry = entry_gate.get(name) if isinstance(entry_gate, dict) else None
    digest = entry.get("sha256") if isinstance(entry, dict) else None
    return digest if isinstance(digest, str) and digest else None


def verify_completed_method_evidence(evidence):
    """认证已消费原快照；当前源码差异单独报告，不能转记为新资格。"""
    result = {"verified": False, "outcome": None, "scope": None, "reasons": [],
              "current_sources_match": False, "identity_differences": []}

    def require(condition, reason):
        if not condition:
            raise ValueError(reason)

    def read_bound(path, digest):
        data = path.read_bytes()
        require(isinstance(digest, str) and len(digest) == 64
                and hashlib.sha256(data).hexdigest() == digest, f"artifact_identity:{path.name}")
        document = json.loads(data.decode("utf-8-sig"))
        require(isinstance(document, dict), f"artifact_not_object:{path.name}")
        return document

    try:
        require(isinstance(evidence, dict), "completed_method_evidence_missing")
        report_path = Path(evidence["canonical_report"])
        if not report_path.is_absolute():
            report_path = BASE / report_path
        report_path = report_path.resolve()
        require(report_path.name == "method-qualification-report.json"
                and report_path.parent.name == "qualification", "qualification_report_layout")
        batch = report_path.parent.parent
        report = read_bound(report_path, evidence["report_sha256"])
        manifest = read_bound(batch / "evidence-manifest.json", evidence["manifest_sha256"])
        seal = read_bound(batch / "qualification-seal.json", evidence["seal_sha256"])
        marker = read_bound(batch / "qualification-seal.json.consumed",
                            evidence["consumption_marker_sha256"])
        records = manifest["files"]
        totals = manifest["totals"]
        require(totals["files"] == totals["verified"] == len(records)
                and totals["missing"] == totals["mismatch"] == 0, "manifest_incomplete")
        members = {}
        for row in records:
            relative = Path(row["dst_win"]).resolve().relative_to(batch)
            require(relative not in members and row["verified"] is True,
                    "manifest_duplicate_or_unverified")
            members[relative] = row["sha256"]

        def member(path, digest):
            require(members.get(path.resolve().relative_to(batch)) == digest,
                    f"manifest_binding:{path.name}")

        for path, field in ((report_path, "report_sha256"),
                            (batch / "qualification-seal.json", "seal_sha256"),
                            (batch / "qualification-seal.json.consumed", "consumption_marker_sha256")):
            member(path, evidence[field])
        identity, summary = report["identity"], report["summary"]
        result["outcome"] = summary.get("outcome")
        result["scope"] = report["qualification_scope"].get("scope")
        require(report["schema"] == METHOD_SCHEMA and report["role"] == "qualification"
                and report["status"] == "complete" and summary["role"] == "qualification"
                and summary["outcome"] == "qualified" and summary["aborted"] is None,
                "qualification_role_or_outcome")
        require(result["scope"] == METHOD_SCOPE
                and report["qualification_scope"]["full_v3_evaluation"] is False,
                "qualification_scope")
        require(all(summary["pass_conditions"].get(key) is True for key in METHOD_PASS_CONDITIONS),
                "mandatory_method_gate_failed")
        require(identity["approval"] is True and seal["role"] == marker["role"]
                == "method_qualification_noteon_v3" and marker["role_run"] == "qualification",
                "approval_or_consumed_role")
        require(identity["seal"]["sha256"] == evidence["seal_sha256"]
                and identity["seal"]["path"] == marker["seal"]
                and identity["consumption_marker"] == marker["seal"] + ".consumed"
                and Path(marker["out"]) == Path(marker["seal"]).parent / "qualification",
                "consumption_marker_binding")
        sealed = {identity[key]["path"]: identity[key]["sha256"] for key in METHOD_SOURCES}
        sealed[identity["registration"]["path"]] = identity["registration"]["sha256"]
        require(len(sealed) == 6 and seal["files"] == sealed, "six_sealed_identities")
        require(marker["registration_sha256"] == identity["registration"]["sha256"]
                and marker["runner_sha256"] == identity["qualification_script"]["sha256"],
                "consumed_snapshot_identity")
        original_registration_name = identity["registration"]["path"].replace("\\", "/").rsplit("/", 1)[-1]
        registration_path = batch / "source-snapshot/pilot" / original_registration_name
        registration = read_bound(registration_path, identity["registration"]["sha256"])
        member(registration_path, identity["registration"]["sha256"])
        require(registration["schema"] == METHOD_SCHEMA
                and registration["execution"]["approval"] is True, "sealed_registration")
        live = {key: Path(__file__).with_name(name) for key, name in METHOD_SOURCES.items()}
        live["registration"] = BASE / "pilot" / original_registration_name
        for key, name in METHOD_SOURCES.items():
            snapshot = batch / "source-snapshot/pilot/tools" / name
            require(sha256(snapshot) == identity[key]["sha256"], f"source_snapshot:{name}")
            member(snapshot, identity[key]["sha256"])
        for key, path in live.items():
            current = sha256(path) if path.is_file() else None
            if current != identity[key]["sha256"]:
                result["identity_differences"].append(
                    {"dependency": key, "path": str(path), "evidence_sha256": identity[key]["sha256"],
                     "current_sha256": current})
        defaults = registration["generator"]["case_defaults"]
        cases = [{**defaults, **row} for row in registration["cases"]["qualification"]]
        controls = [{**defaults, **row} for row in registration["regression_controls"]]
        for declared, observed, role in ((cases, report["cases"], "qualification"),
                                        (controls, report["regression_controls"], "regression_control")):
            require(declared and [row["id"] for row in declared] == [row["id"] for row in observed]
                    and len({row["id"] for row in declared}) == len(declared),
                    f"incomplete_registered_role:{role}")
            require(all(row["role"] == role and row["verdict"] == "passed"
                        and row["recipe"] == recipe for recipe, row in zip(declared, observed)),
                    f"failed_or_replaced_case:{role}")
        require(summary["complete_role"]["complete"] is True
                and summary["complete_role"]["expected_cases"]
                == summary["complete_role"]["executed_cases"] == len(cases)
                and not summary["cases_failed"] and not summary["controls_violated"],
                "incomplete_role_summary")
        positive_ids = {row["id"] for row in cases if row["admission_expectation"] == "admitted"}
        admitted_ids = {row["id"] for row in report["cases"]
                        if row["ppa_lane"]["branch"] == "required_admitted"}
        coverage = summary["positive_coverage"]
        require(positive_ids == admitted_ids and coverage["satisfied"] is True
                and coverage["cases_expected"] == coverage["cases_verified_admitted"] == len(positive_ids)
                and len(positive_ids) >= registration["coverage_requirements"][
                    "minimum_required_admission_cases_per_role"], "positive_coverage")
        groups = report["cross_case_gates"]
        require(not groups["violations"], "cross_case_gate_failed")
        for field, declaration, identifier, verdict in (
                ("repeat_groups", "repeat_group", "group", lambda row: row.get("admitted") is True),
                ("comparison_pairs", "comparison_pair", "pair",
                 lambda row: row.get("state") == "comparison_passed")):
            expected_ids = {row[declaration][identifier] for row in cases if row.get(declaration)}
            observed_ids = [row[identifier] for row in groups[field]]
            require(expected_ids and set(observed_ids) == expected_ids
                    and len(observed_ids) == len(expected_ids) and all(verdict(row) for row in groups[field]),
                    f"incomplete_or_failed_group:{field}")
        regression = summary["evaluator_regression"]
        require(regression["passed"] is True and regression["exit_code"] == 0
                and regression["script_sha256"] == identity["evaluator_regression_script"]["sha256"],
                "evaluator_regression_failed")
        for field in ("stdout", "stderr"):
            path = report_path.parent / regression[field]
            require(sha256(path) == regression[field + "_sha256"], f"regression_log:{field}")
            member(path, regression[field + "_sha256"])
        result["verified"] = True
        result["current_sources_match"] = not result["identity_differences"]
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        result["reasons"].append(f"{type(error).__name__}: {error}")
    return result




def execution_blockers(prereg):
    """草案/未批准协议在读取音频或写出前拒绝；v3 伪造 frozen 状态仍需授权、矩阵与前提全部就绪。"""
    blockers = []
    status = prereg.get("status")
    if status != EXECUTABLE_STATUS:
        blockers.append(f"status:{status}")
    if prereg.get("schema") != V3_SCHEMA:
        return blockers
    unresolved = prereg.get("unresolved_prerequisites")
    if not isinstance(unresolved, list) or unresolved:
        blockers.append("unresolved_prerequisites")
    authorizations = prereg.get("authorizations")
    if not isinstance(authorizations, dict):
        blockers.append("authorizations:missing")
    else:
        blockers.extend(f"authorization:{key}" for key in V3_REQUIRED_AUTHORIZATIONS
                        if authorizations.get(key) is not True)
    evaluation = prereg.get("evaluation")
    matrix = evaluation.get("matrix") if isinstance(evaluation, dict) else None
    if not isinstance(matrix, list) or not matrix:
        blockers.append("matrix_not_selected")
    entry_gate = prereg.get("entry_gate_frozen")
    if (not isinstance(entry_gate, dict)
            or entry_gate.get("preregistered_before_any_rendering_or_inspection") is not True):
        blockers.append("entry_gate_not_frozen_before_rendering")
    origin = prereg.get("reference_origin")
    origin_status = origin.get("status") if isinstance(origin, dict) else None
    if origin_status != "authenticated":
        blockers.append(f"reference_origin:{origin_status}")
    return blockers


def analyze_registered_input(path, note, prereg, unit, producer):
    """v3 输入必须绑定同一 WAV 的时序证据；旧数据诊断显式使用文件绝对坐标。"""
    if prereg.get("schema") != V3_SCHEMA:
        return ppa.analyze_unit(path, note, timing={"coordinate": "file_absolute"})
    if producer not in ("reference", "devpiano"):
        raise ValueError("Unknown timing-evidence producer")
    binding = prereg.get("timing_evidence", {}).get(producer, {}).get(unit)
    if not isinstance(binding, dict) or not binding.get("path") or not binding.get("sha256"):
        raise ValueError(f"Missing bound NoteOn timing evidence: {producer}/{unit}")
    report = Path(binding["path"])
    if not report.is_absolute():
        report = BASE / report
    if sha256(report) != binding["sha256"]:
        raise ValueError(f"Timing-evidence hash mismatch: {producer}/{unit}")
    timing = ppa.load_timing_report(report, path)
    expected_role = ("reference_origin_authenticated" if producer == "reference"
                     else "dev_render_verification")
    if (timing.get("coordinate") != "note_on_relative"
            or timing.get("evidence_role") != expected_role):
        raise ValueError(f"Timing-evidence role cannot authorize {producer}: {timing.get('evidence_role')}")
    return ppa.analyze_unit(path, note, timing=timing)


def plan_report(prereg, prereg_path):
    """准备级报告：只读预登记与声明契约，报告真实阻塞；不读音频、不写输出、不声称就绪或冻结。"""
    blockers = list(execution_blockers(prereg))
    declared = prereg.get("contracts")
    if prereg.get("schema") == V3_SCHEMA:
        for required in ("frequency_observable", "input_render"):
            if not isinstance(declared, dict) or required not in declared:
                blockers.append(f"contract_missing:{required}")
    contracts, documents = [], {}
    for name in (sorted(declared) if isinstance(declared, dict) else ()):
        entry = declared[name]
        text = entry.get("path") if isinstance(entry, dict) else entry
        path = Path(text) if isinstance(text, str) else Path("missing")
        if not path.is_absolute():
            path = BASE / path
        present = isinstance(text, str) and path.is_file()
        document = json.loads(path.read_text(encoding="utf-8-sig")) if present else None
        documents[name] = document
        declared_digest = entry.get("sha256") if isinstance(entry, dict) else None
        digest = sha256(path) if present else None
        contracts.append({"name": name, "declared_path": text, "resolved_path": str(path),
                          "present": present, "sha256": digest, "declared_sha256": declared_digest,
                          "document_status": (document.get("status") if isinstance(document, dict)
                                              else None)})
        if not present:
            blockers.append(f"contract_missing:{name}")
        elif isinstance(declared_digest, str) and declared_digest and declared_digest != digest:
            blockers.append(f"contract_hash_mismatch:{name}")
    entry_gate = prereg.get("entry_gate_frozen")
    tool_identity = []
    for name, digest in sorted(actual_tool_hashes().items()):
        declared_digest = bound_digest(entry_gate, name)
        tool_identity.append({"name": name, "declared_sha256": declared_digest,
                              "actual_sha256": digest, "matches": declared_digest == digest})
        if declared_digest is None:
            blockers.append(f"tool_identity_unbound:{name}")
        elif declared_digest != digest:
            blockers.append(f"tool_identity_mismatch:{name}")
    manifest = documents.get("input_render")
    frequency_contract = documents.get("frequency_observable")
    limits = frequency_contract.get("limits") if isinstance(frequency_contract, dict) else None
    origin = prereg.get("reference_origin")
    qualification = prereg.get("qualification")
    contract_origin = manifest.get("reference_origin") if isinstance(manifest, dict) else None
    cross_check = {
        "declared_reference_origin_status": (origin.get("status") if isinstance(origin, dict) else None),
        "contract_reference_origin_status": (contract_origin.get("status")
                                             if isinstance(contract_origin, dict) else None),
        "contract_formal_readiness": manifest.get("formal_readiness") if isinstance(manifest, dict) else None,
        "contract_v3_formal_method_ready": (limits.get("v3_formal_method_ready")
                                            if isinstance(limits, dict) else None),
    }
    if (cross_check["contract_reference_origin_status"] is not None
            and cross_check["declared_reference_origin_status"] != cross_check["contract_reference_origin_status"]):
        blockers.append("reference_origin_contradicts_contract")
    completed = None
    current_snapshot_qualified = False
    if prereg.get("schema") == V3_SCHEMA:
        completed = verify_completed_method_evidence(
            qualification.get("completed_method_evidence") if isinstance(qualification, dict) else None)
        current_snapshot_qualified = completed["verified"] and completed["current_sources_match"]
        if not completed["verified"]:
            blockers.append("method_qualification:evidence_not_verified")
        elif not current_snapshot_qualified:
            blockers.append("method_qualification:current_snapshot_changed")
        if cross_check["contract_v3_formal_method_ready"] is not True:
            blockers.append("v3_formal_method_not_ready")
    reference_timing_supported = "reference_origin_authenticated" in getattr(
        ppa, "SUPPORTED_EVIDENCE_ROLES", ())
    if prereg.get("schema") == V3_SCHEMA and not reference_timing_supported:
        blockers.append("reference_timing_verifier_not_available")
    authorizations = prereg.get("authorizations")
    unresolved = prereg.get("unresolved_prerequisites")
    return {
        "mode": "check_plan",
        "preparation_only": True,
        "readiness_or_freeze_asserted": False,
        "preregistration": str(prereg_path),
        "preregistration_sha256": sha256(prereg_path),
        "schema": prereg.get("schema"),
        "status": prereg.get("status"),
        "execution_allowed": not blockers,
        "blockers": sorted(set(blockers)),
        "required_authorizations": list(V3_REQUIRED_AUTHORIZATIONS),
        "authorizations": {key: authorizations.get(key)
                           for key in sorted(authorizations)} if isinstance(authorizations, dict) else {},
        "unresolved_prerequisites": ([entry.get("id") if isinstance(entry, dict) else entry
                                      for entry in unresolved] if isinstance(unresolved, list) else None),
        "contracts": contracts,
        "tool_identity": tool_identity,
        "cross_check": cross_check,
        "method_qualification": {"completed_evidence": completed,
                                 "current_snapshot_qualified": current_snapshot_qualified},
        "accounting_states": list(STATES),
        "reference_timing_verifier_available": reference_timing_supported,
        "note": "契约/工具散列只用于准备报告，不构成冻结、就绪、准入或验收结论。",
    }


def check_plan(prereg, prereg_path):
    """打印准备级报告并返回退出码；不写任何输出文件、不读取任何生产者输入。"""
    report = plan_report(prereg, prereg_path)
    blockers = report["blockers"]
    print(json.dumps(report, ensure_ascii=False, indent=1, allow_nan=False) + "\n")
    print(f"plan={'blocked' if blockers else 'unblocked'} blockers={len(blockers)} "
          f"execution_allowed={report['execution_allowed']}", file=sys.stderr)
    for blocker in blockers:
        print(f"  blocker: {blocker}", file=sys.stderr)
    return PLAN_BLOCKED_EXIT if blockers else 0


def observation_qualified(observation, frequency):
    """条件区间必须覆盖报告频率且窄于频率预算；不认证真实弦身份。"""
    if not isinstance(observation, dict) or not finite(frequency) or frequency <= 0:
        return False
    interval = observation.get("interval_hz")
    if (observation.get("status") != "single_component_adequate"
            or observation.get("frequency_hz") != frequency
            or not isinstance(interval, (list, tuple)) or len(interval) != 2
            or any(not finite(value) for value in interval)):
        return False
    budget = max(0.005, frequency * (2.0 ** (0.05 / 1200.0) - 1.0))
    return (0 < interval[0] <= frequency <= interval[1]
            and max(frequency - interval[0], interval[1] - frequency) <= budget)


def reference_quality(analysis):
    """只从实际观测重算门禁；流程 status=ok 不代替数值或留出充分性。"""
    reasons, windows = [], {}
    for name in ("W1", "W2"):
        window = analysis.get("windows", {}).get(name)
        if not isinstance(window, dict):
            reasons.append(f"{name}:missing_window")
            continue
        if window.get("status") != "ok":
            reasons.append(f"{name}:window_{window.get('status')}")
        numbers = window.get("partial_numbers", [])
        observed = window.get("observed_peak_Hz", [])
        prediction = window.get("independent_prediction", {})
        details = prediction.get("details", [])
        if (len(numbers) < 5 or len(set(numbers)) != len(numbers)
                or len(observed) != len(numbers)
                or any(not finite(f) or f <= 0 for f in observed)):
            reasons.append(f"{name}:invalid_identified_partials")
        observations = window.get("partial_observations", {})
        # 重查全部候选的结构证据；低信息弃权仍只约束实际用于拟合的编号。
        mixed = [number for number, row in observations.items()
                 if isinstance(row, dict) and ppa.observation_blocks_family(row)]
        if mixed:
            reasons.append(f"{name}:mixed_partial_observation")
        if any(not observation_qualified(observations.get(str(n)), f)
               for n, f in zip(numbers, observed)):
            reasons.append(f"{name}:unqualified_partial_observation")
        if prediction.get("status") != "ok":
            reasons.append(f"{name}:independent_prediction_status")
        if not finite(prediction.get("training_size")) or prediction["training_size"] < 3:
            reasons.append(f"{name}:insufficient_training")
        if (not finite(prediction.get("holdout_size")) or prediction["holdout_size"] < 2
                or len(details) != prediction["holdout_size"]):
            reasons.append(f"{name}:incomplete_holdout")
        errors, held_numbers = [], []
        for detail in details:
            predicted, actual = detail.get("predicted_Hz"), detail.get("reidentified_Hz")
            number = detail.get("number")
            if (not finite(predicted) or not finite(actual) or predicted <= 0 or actual <= 0
                    or number not in numbers or number in held_numbers):
                reasons.append(f"{name}:invalid_holdout_observation")
                continue
            if not observation_qualified(detail.get("observation"), actual):
                reasons.append(f"{name}:unqualified_holdout_observation")
                continue
            held_numbers.append(number)
            errors.append(1200.0 * math.log2(actual / predicted))
        rms = math.sqrt(sum(e * e for e in errors) / len(errors)) if errors else None
        maximum = max(map(abs, errors)) if errors else None
        if len(errors) < 2:
            reasons.append(f"{name}:insufficient_independent_holdout")
        if rms is not None and (rms > 1.0 or maximum > 3.0):
            reasons.append(f"{name}:independent_prediction_error")
        first, stiffness = window.get("f1_Hz"), window.get("effective_B")
        if not finite(first) or first <= 0 or not finite(stiffness) or stiffness < 0:
            reasons.append(f"{name}:invalid_fitted_parameters")
        windows[name] = {"identified_partials": len(numbers), "holdout_observed": len(errors),
                         "independent_rms_cents": rms, "independent_max_cents": maximum,
                         "f1_Hz": first if finite(first) else None,
                         "effective_B": stiffness if finite(stiffness) else None,
                         "mixed_partials": mixed}
    fspread, bspread = None, None
    if len(windows) == 2 and all(finite(w["f1_Hz"]) and w["f1_Hz"] > 0
                               and finite(w["effective_B"]) and w["effective_B"] >= 0
                               for w in windows.values()):
        a, b = windows["W1"], windows["W2"]
        fspread = abs(1200.0 * math.log2(a["f1_Hz"] / b["f1_Hz"]))
        ceiling = max(a["effective_B"], b["effective_B"])
        bspread = abs(a["effective_B"] - b["effective_B"]) / ceiling if ceiling else 0.0
        if fspread > 1.0:
            reasons.append("window_frequency_spread")
        if bspread > 0.1:
            reasons.append("window_B_spread")
    return {"admitted": not reasons, "reasons": reasons, "windows": windows,
            "window_frequency_spread_cents": fspread, "window_B_relative_spread": bspread}


def repeat_quality(rows, analyses):
    """重复组不完整或不稳定时整组拒绝；缺失行本身仍保留自己的分类。"""
    expected = {row["repeat"] for row in rows}
    available = [analyses[row["unit"]] for row in rows if row["unit"] in analyses]
    if len(expected) < 2 or len(available) != len(rows):
        return {"admitted": False, "reasons": ["incomplete_repeat_group"]}
    first = [a.get("windows", {}).get("W1", {}).get("f1_Hz") for a in available]
    stiffness = [a.get("windows", {}).get("W1", {}).get("effective_B") for a in available]
    if (any(not finite(f) or f <= 0 for f in first)
            or any(not finite(b) or b < 0 for b in stiffness)):
        return {"admitted": False, "reasons": ["invalid_repeat_parameters"]}
    fspread = abs(1200.0 * math.log2(max(first) / min(first)))
    bspread = (max(stiffness) - min(stiffness)) / max(stiffness) if max(stiffness) else 0.0
    reasons = [] if all(reference_quality(a)["admitted"] for a in available) else ["rejected_repeat_member"]
    if fspread > 1.0:
        reasons.append("repeat_frequency_spread")
    if bspread > 0.1:
        reasons.append("repeat_B_spread")
    return {"admitted": not reasons, "reasons": reasons,
            "frequency_spread_cents": fspread, "B_relative_spread": bspread}


def compare_analyses(entry, reference, dev, min_comparable):
    """基准仅用于归一化；零/一个非基准样本不得落出分类或被算作通过。"""
    # 比较候选不能绕过任一侧完整族的混合证据或后窗失败。
    for producer, analysis in (("reference", reference), ("devpiano", dev)):
        quality = reference_quality(analysis)
        if not quality["admitted"]:
            entry.update({"state": "reference_rejected" if producer == "reference"
                          else "insufficient_comparable", "producer": producer,
                          "reason": "comparison_family_rejected", "family_quality": quality})
            return entry
    rw, dw = reference["windows"]["W1"], dev["windows"]["W1"]
    rp = dict(zip(rw["partial_numbers"], rw["observed_peak_Hz"], strict=True))
    dp = dict(zip(dw["partial_numbers"], dw["observed_peak_Hz"], strict=True))
    for name, window, values in (("reference", rw, rp), ("devpiano", dw, dp)):
        if any(not observation_qualified(window.get("partial_observations", {}).get(str(n)), f)
               for n, f in values.items()):
            raise ValueError(f"{name} contains unqualified partial observations")
    if (any(not finite(f) or f <= 0 for f in dp.values())
            or not finite(dw["f1_Hz"]) or dw["f1_Hz"] <= 0
            or not finite(dw["effective_B"]) or dw["effective_B"] < 0):
        raise ValueError("Invalid devpiano frequencies or stiffness")
    common = sorted(set(rp) & set(dp))
    note = entry["note"]
    # 冻结内置设计的单弦区没有同音弦分化；多弦分化区仍按原界限排除。
    first = 1 if 21 <= note < 36 else (min_comparable if note < 72 else (5 if note < 96 else 1))
    comparable = [n for n in common if n >= first]
    entry.update({"ref_partials": len(rp), "dev_partials": len(dp),
                  "common_partials": len(common), "comparable_partials": len(comparable),
                  "base_partial": comparable[0] if comparable else None,
                  "nonbase_count": max(0, len(comparable) - 1),
                  "norm_rms": None, "norm_max": None, "details": []})
    rB, dB = rw["effective_B"], dw["effective_B"]
    entry.update({"ref_B": rB, "dev_B": dB,
                  "B_rel_pct": (dB - rB) / rB * 100.0 if rB else None,
                  "f1_cents": 1200.0 * math.log2(dw["f1_Hz"] / rw["f1_Hz"])})
    if comparable:
        m = comparable[0]
        entry["details"] = [
            {"partial": n, "error_cents": 1200.0 * math.log2((dp[n] / dp[m]) / (rp[n] / rp[m]))}
            for n in comparable[1:]]
    if entry["details"]:
        errors = [d["error_cents"] for d in entry["details"]]
        entry["norm_rms"] = math.sqrt(sum(e * e for e in errors) / len(errors))
        entry["norm_max"] = max(map(abs, errors))
    if entry["nonbase_count"] < 2:
        entry["state"] = "insufficient_comparable"
    else:
        entry["state"] = ("comparison_passed" if entry["norm_rms"] <= 1.0 and entry["norm_max"] <= 3.0
                          else "comparison_failed")
    return entry


def summarize(results):
    if len({r["unit"] for r in results}) != len(results):
        raise ValueError("Duplicate registered unit")
    counts = Counter(r["state"] for r in results)
    if set(counts) - set(STATES):
        raise ValueError("Unclassified result")
    return {"counts": {state: counts[state] for state in STATES},
            "units": {state: [r["unit"] for r in results if r["state"] == state] for state in STATES},
            "complete": sum(counts.values()) == len(results)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preregistration", required=True)
    parser.add_argument("--reference-batch", default=None)
    parser.add_argument("--dev-render", default=None, help="devpiano render root (<rate>/n<note>-v<vel>.wav)")
    parser.add_argument("--out", default=None)
    parser.add_argument("--candidate-table", default=None)
    parser.add_argument("--diagnostic-only", action="store_true",
                        help="consumed-data diagnosis only; never replaces a frozen acoustic verdict")
    parser.add_argument("--refinement-guard-db", default=None,
                        help="override preregistered guard; 'off' = legacy nearest")
    parser.add_argument("--check-plan", action="store_true",
                        help="preparation-only plan/draft report; reads no producer inputs, writes no outputs")
    options = parser.parse_args()

    prereg_path = Path(options.preregistration)
    prereg = json.loads(prereg_path.read_text(encoding="utf-8-sig"))
    if options.check_plan:
        if (options.diagnostic_only or options.out or options.reference_batch
                or options.dev_render or options.candidate_table):
            parser.error("--check-plan is preparation-only: it accepts only --preregistration "
                         "(no producer inputs, outputs or diagnostic role)")
        raise SystemExit(check_plan(prereg, prereg_path))
    blockers = execution_blockers(prereg)
    if blockers:
        parser.error("Preregistration not executable (" + ", ".join(blockers)
                     + "); use --check-plan for a preparation report")
    if prereg.get("schema") == V3_SCHEMA:
        blockers = plan_report(prereg, prereg_path)["blockers"]
        if blockers:
            parser.error("Preregistration contracts not executable (" + ", ".join(blockers) + ")")
    if not (options.reference_batch and options.dev_render and options.out):
        parser.error("--reference-batch, --dev-render and --out are required for evaluation")
    out_path = Path(options.out)
    if out_path.exists():
        parser.error("Output exists; preserve previous evidence and use a fresh path")
    bindings = prereg["entry_gate_frozen"]
    actual_hashes = actual_tool_hashes()
    mismatches = [name for name, digest in actual_hashes.items()
                  if digest != bindings.get(name, {}).get("sha256")]
    if mismatches and (prereg.get("schema") == V3_SCHEMA or not options.diagnostic_only):
        parser.error("Frozen tool identity mismatch: " + ", ".join(mismatches)
                     + "; revised methods require --diagnostic-only, not a historical re-verdict")
    evaluation = prereg["evaluation"]
    a4 = evaluation["a4_hz"]
    matrix = evaluation["matrix"]
    velocities = evaluation["velocities"]
    min_comparable = evaluation["min_comparable_below_72"]
    guard = evaluation.get("refinement_guard_db", 20.0)
    if options.refinement_guard_db is not None:
        guard = (None if str(options.refinement_guard_db).lower() in ("off", "none")
                 else float(options.refinement_guard_db))
    ppa.REFINEMENT_GUARD_DB = guard

    ppa.NOTES = {n: a4 * 2.0 ** ((n - 69) / 12.0) for n in range(0, 128)}
    ppa.SNR_ADMISSION_DB = 25.0
    ppa.SNR_MIN_NOTE = 72

    ref_root = Path(options.reference_batch)
    dev_root = Path(options.dev_render)
    results, references, groups = [], {}, {}
    for row in matrix:
        note, rate, repeat, session = row["note"], row["rate"], row["repeat"], row["session"]
        for vel in velocities:
            unit = f"n{note}-v{vel}-{rate}-rep{repeat}"
            ref_path = ref_root / "sessions" / session / "units" / unit / "export.wav"
            dev_path = dev_root / str(rate) / f"n{note}-v{vel}.wav"
            entry = {"note": note, "velocity": vel, "rate": rate, "repeat": repeat, "unit": unit}
            results.append(entry)
            groups.setdefault((note, vel, rate), []).append(entry)
            missing = [str(path) for path in (ref_path, dev_path) if not path.is_file()]
            if missing:
                entry.update({"state": "missing_input", "missing": missing})
                continue
            try:
                analysis = analyze_registered_input(ref_path, note, prereg, unit, "reference")
                if analysis["rate"] != rate:
                    raise ValueError(f"Reference sample rate differs: {analysis['rate']} != {rate}")
                references[unit] = analysis
                entry["reference_quality"] = reference_quality(analysis)
                entry["reference_window_reports"] = analysis["windows"]
                if analysis["status"] == "window_failure":
                    entry.update({"state": "analysis_error", "producer": "reference",
                                  "window_failures": analysis["window_failures"]})
                entry["reference_wav_sha256"] = sha256(ref_path)
            except Exception as error:  # noqa: BLE001 - 每个登记单元保留错误，不删行
                entry.update({"state": "analysis_error", "producer": "reference", "error": str(error)})
    for rows in groups.values():
        quality = repeat_quality(rows, references)
        for entry in rows:
            if "state" not in entry:
                entry["reference_quality"]["repeat"] = quality
                if not entry["reference_quality"]["admitted"] or not quality["admitted"]:
                    entry["state"] = "reference_rejected"
    dev_cache = {}
    for entry in results:
        if "state" in entry:
            continue
        note, vel, rate = entry["note"], entry["velocity"], entry["rate"]
        dev_path = dev_root / str(rate) / f"n{note}-v{vel}.wav"
        try:
            cache_key = (dev_path, entry["unit"]) if prereg.get("schema") == V3_SCHEMA else dev_path
            if cache_key not in dev_cache:
                dev_cache[cache_key] = analyze_registered_input(
                    dev_path, note, prereg, entry["unit"], "devpiano")
            dev = dev_cache[cache_key]
            if dev["rate"] != rate:
                raise ValueError(f"Dev sample rate differs: {dev['rate']} != {rate}")
            if dev["status"] == "window_failure":
                entry.update({"state": "analysis_error", "producer": "devpiano",
                              "window_failures": dev["window_failures"],
                              "dev_window_reports": dev["windows"]})
                continue
            if dev["status"] == "observation_inconclusive":
                entry.update({"state": "insufficient_comparable", "producer": "devpiano",
                              "reason": "observer_inconclusive", "dev_window_reports": dev["windows"]})
                continue
            entry["dev_wav_sha256"] = sha256(dev_path)
            compare_analyses(entry, references[entry["unit"]], dev, min_comparable)
        except Exception as error:  # noqa: BLE001 - 后端失败同样纳入完整分类
            entry.update({"state": "analysis_error", "producer": "devpiano", "error": str(error)})
    accounting = summarize(results)
    ok = [r for r in results if r["state"] in ("comparison_passed", "comparison_failed")]
    weak = [r for r in results if r["state"] == "insufficient_comparable"]
    errs_n = [r for r in results if r["state"] == "analysis_error"]
    passing = [r for r in ok if r["state"] == "comparison_passed"]
    out = {
        "schema": "devpiano-task39-2-validation-observer-diagnostic-v3",
        "assessment_role": "diagnostic_only" if options.diagnostic_only else "registered_analysis",
        "historical_verdict_changed": False,
        "dependency_hash_mismatches": mismatches,
        "evaluator_sha256": actual_hashes["evaluator"],
        "accounting": accounting,
        "preregistration": str(options.preregistration),
        "preregistration_sha256": sha256(options.preregistration),
        "analysis_tool": ANALYSIS_TOOL,
        "analysis_tool_sha256": sha256(ANALYSIS_TOOL),
        "partial_observer": str(ppa.OBSERVER_PATH),
        "partial_observer_sha256": actual_hashes["partial_observer"],
        "refinement_guard_db": guard,
        "reference_batch": str(ref_root),
        "dev_render": str(dev_root),
        "candidate_table": options.candidate_table,
        "criterion": ("monochord MIDI21-35 n>=1; multistring MIDI36-71 n>=%d, MIDI72-95 n>=5, "
                      "MIDI96+ n>=1; both complete families admitted before comparison; "
                      "amendment-4 base m = min common comparable; "
                      "RMS<=1 cent and max<=3 cents, >=2 non-base partials; amendment-5 strength guard"
                      % min_comparable),
        "units_total": len(results),
        "units_evaluable": len(ok),
        "units_weak": [r["unit"] for r in weak],
        "units_error": [r["unit"] for r in errs_n],
        "units_missing": [r["unit"] for r in results if r["state"] == "missing_input"],
        "units_reference_rejected": [r["unit"] for r in results if r["state"] == "reference_rejected"],
        "units_passing": len(passing),
        "failing_units": [r["unit"] for r in ok if r["state"] == "comparison_failed"],
        "results": results,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=1, allow_nan=False) + "\n", encoding="utf-8")

    print(f"role={out['assessment_role']} guard={guard}: units {len(results)} "
          f"accounted={sum(accounting['counts'].values())} states={accounting['counts']}")
    notes = sorted({r["note"] for r in results})
    for note in notes:
        rows = [r for r in ok if r["note"] == note]
        if not rows:
            continue
        nr = [r["norm_rms"] for r in rows]
        nm = [r["norm_max"] for r in rows]
        b = [r["B_rel_pct"] for r in rows if r["B_rel_pct"] is not None]
        p = sum(1 for r in rows if r["norm_rms"] <= 1.0 and r["norm_max"] <= 3.0)
        b_mean = float(np.mean(b)) if b else float("nan")
        print(f"  n{note}: B_rel {b_mean:+6.2f}%  rms mean {np.mean(nr):5.3f} max {max(nr):5.3f}  "
              f"max mean {np.mean(nm):5.3f} worst {max(nm):5.3f}  pass {p}/{len(rows)}")
    if ok:
        nr = [r["norm_rms"] for r in ok]
        nm = [r["norm_max"] for r in ok]
        print(f"overall: median rms {np.median(nr):.3f} worst rms {max(nr):.3f} | "
              f"median max {np.median(nm):.3f} worst max {max(nm):.3f}")


if __name__ == "__main__":
    main()
