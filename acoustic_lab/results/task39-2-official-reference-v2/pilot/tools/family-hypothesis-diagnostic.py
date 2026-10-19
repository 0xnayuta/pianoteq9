#!/usr/bin/env python3
"""Task 39-2 n29-v107 家族假设诊断工具（只读、有界）。

严格 import 传入的冻结 PPA（pilot-partial-analysis.py），直接调用其
read_wav_stereo / power_spectrum / spectral_peaks / fit / partial_prediction / holdout_window_cents，
禁止代码复制与内部算法回退。
在固定原窗 W1/W2 与 3 个预声明诊断窗（D_early, D_mid, D_late）上，
评估低阶预设子集（1..6、1..12、1..24）与竞争静态拟合/选峰假设；
留出峰在原始谱峰内按训练预测重新识别，不从生产表读 B。
独立已知基准（stationary/decaying）逐线逐窗自检超 max(0.005Hz, 0.05cents) 严格标为
non-discriminating，不放宽阈值。
"""

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np

NOMINAL_F1 = 440.0 * (2.0 ** ((29 - 69) / 12.0))  # 43.6536 Hz
VELOCITIES = [47, 79, 107]
RATES = [44100, 48000]
REPEATS = [0, 1]
SESSIONS = {
    (44100, 0): "s01-n29-44100-rep0",
    (44100, 1): "s02-n29-44100-rep1",
    (48000, 0): "s03-n29-48000-rep0",
    (48000, 1): "s04-n29-48000-rep1",
}
WINDOWS = {
    "W1": (0.08, 3.80),
    "W2": (0.50, 4.10),
    "D_early": (0.08, 1.58),
    "D_mid": (1.58, 3.08),
    "D_late": (2.60, 4.10),
}
SUBSETS = {"1..6": list(range(1, 7)), "1..12": list(range(1, 13)), "1..24": list(range(1, 25))}
HOLDOUT_BANDS = {
    "7..12": list(range(7, 13)),
    "13..24": list(range(13, 25)),
    "25..36": list(range(25, 37)),
    "37..48": list(range(37, 49)),
}
CALIBRATION_LINES = [1, 2, 3, 4, 6, 8, 10, 12, 16, 20, 24, 30, 36, 48]


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_ppa(path: Path):
    if not path.is_file():
        raise SystemExit(f"analysis-tool 文件不存在: {path}")
    spec = importlib.util.spec_from_file_location("ppa", str(path))
    if spec is None or spec.loader is None:
        raise SystemExit(f"无法加载 analysis-tool 规格: {path}")
    ppa = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ppa)
    return ppa


def cents(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or a <= 0 or b <= 0:
        return None
    val = 1200.0 * math.log2(a / b)
    return float(val) if math.isfinite(val) else None


def gate_hz(freq: float) -> float:
    return max(0.005, freq * (2.0 ** (0.05 / 1200.0) - 1.0))


def synth_signal(rate: int, dur: float, kind: str, freqs: list[float]) -> np.ndarray:
    t = np.arange(int(dur * rate), dtype=np.float64) / rate
    sig = np.zeros_like(t)
    rng = np.random.RandomState(42)
    phases = [rng.uniform(0, 2 * math.pi) for _ in freqs]
    for k, (f0, phi) in enumerate(zip(freqs, phases)):
        amp = 1.0 / math.sqrt(k + 1)
        if kind == "stationary":
            sig += amp * np.cos(2 * math.pi * f0 * t + phi)
        elif kind == "decaying":
            tau = max(0.4, 3.5 / math.sqrt(k + 1))
            sig += (amp * np.exp(-t / tau)) * np.cos(2 * math.pi * f0 * t + phi)
        elif kind == "chirp":
            theta = 2 * math.pi * (f0 * t - 0.3 * (np.exp(-t / 0.6) - 1.0)) + phi
            sig += amp * np.cos(theta)
    max_val = np.max(np.abs(sig))
    return (0.707 * sig / max_val) if max_val > 0 else sig


def run_preflight(ppa, rate: int) -> dict:
    lines = [n * NOMINAL_F1 + 0.113 * ((-1) ** n) for n in CALIBRATION_LINES]
    dur = 4.5
    s_stat = synth_signal(rate, dur, "stationary", lines)
    s_decay = synth_signal(rate, dur, "decaying", lines)

    win_calib = {}
    for w_name, w_bounds in WINDOWS.items():
        f_stat, p_stat = ppa.power_spectrum(s_stat, s_stat, rate, w_bounds)
        pk_stat, rel_stat, _ = ppa.spectral_peaks(f_stat, p_stat, 35.0, 12000.0)
        f_dec, p_dec = ppa.power_spectrum(s_decay, s_decay, rate, w_bounds)
        pk_dec, rel_dec, _ = ppa.spectral_peaks(f_dec, p_dec, 35.0, 12000.0)


        line_status = {}
        all_passed = True
        for n, f0 in zip(CALIBRATION_LINES, lines):
            ghz = gate_hz(f0)
            tol = 0.01 * f0

            def measure(peaks, rel, signal):
                candidates = np.flatnonzero(np.abs(peaks - n * NOMINAL_F1) <= tol)
                if not candidates.size:
                    return None, {"status": "ambiguous", "reasons": ["no_spectral_candidate"]}
                candidate = float(peaks[candidates[np.argmax(rel[candidates])]])
                result = ppa.observer.observe_partial(
                    signal, signal, rate, w_bounds, candidate,
                    min(0.2 * NOMINAL_F1, max(4.0 / (w_bounds[1] - w_bounds[0]), 0.01 * candidate)))
                error = (abs(result["frequency_hz"] - f0)
                         if result["status"] == "single_component_adequate" else None)
                return error, result

            err_stat, obs_stat = measure(pk_stat, rel_stat, s_stat)
            err_dec, obs_dec = measure(pk_dec, rel_dec, s_decay)

            # 逐线必须 stationary 与 decaying 都 <= gate_hz
            stat_pass = (err_stat is not None and err_stat <= ghz)
            dec_pass = (err_dec is not None and err_dec <= ghz)
            line_disc = stat_pass and dec_pass
            if not line_disc:
                all_passed = False

            line_status[str(n)] = {
                "f_true_hz": f0, "gate_hz": ghz,
                "err_stationary_hz": err_stat, "err_decaying_hz": err_dec,
                "stationary_observation": obs_stat, "decaying_observation": obs_dec,
                "can_discriminate": line_disc
            }

        win_calib[w_name] = {
            "all_lines_discriminating": all_passed,
            "status": "calibrated_discriminating" if all_passed else "non_discriminating_resolution_limit",
            "lines": line_status
        }
    return win_calib


def extract_candidates(ppa, peaks, rel, snr, f1_seed, b_seed, left, right, rate, window):
    cats = {}
    for n in range(1, 49):
        pred = float(ppa.partial_prediction([f1_seed, b_seed], np.array([n]))[0])
        inside = np.flatnonzero(np.abs(peaks - pred) / pred <= 0.015)
        cands = []
        for idx in inside:
            hz = float(peaks[idx])
            cands.append({
                "hz": hz,
                "rel_db": float(10.0 * math.log10(max(rel[idx], 1e-30))),
                "snr_db": float(snr[idx]),
                "cents_err": cents(hz, pred)
            })
        if not cands:
            continue
        strongest = max(cands, key=lambda c: c["rel_db"])
        nearest = min(cands, key=lambda c: abs(c["cents_err"]))
        for candidate in {strongest["hz"], nearest["hz"]}:
            observation = ppa.observer.observe_partial(
                left, right, rate, window, candidate,
                min(0.2 * f1_seed, max(4.0 / (window[1] - window[0]), 0.01 * candidate)))
            for picked in (strongest, nearest):
                if picked["hz"] == candidate:
                    picked["observation"] = observation
        is_same = (strongest["hz"] == nearest["hz"])
        db_diff = float(strongest["rel_db"] - nearest["rel_db"])
        competing = [c for c in cands if strongest["rel_db"] - c["rel_db"] <= 20.0]
        cats[str(n)] = {
            "pred_hz": pred, "count": len(cands),
            "strongest": strongest, "nearest": nearest,
            "is_same": is_same, "db_diff": db_diff,
            "ambiguous": (len(competing) > 1
                          or strongest["observation"]["status"] != "single_component_adequate"),
            "cands": cands
        }
    return cats


def fit_and_holdouts(ppa, raw_peaks, raw_rel, candidates, observe):
    res = {}
    for mode in ("strongest", "nearest"):
        mode_res = {}
        for s_name, s_partials in SUBSETS.items():
            train_n = [n for n in s_partials if str(n) in candidates
                       and candidates[str(n)][mode]["observation"]["status"] == "single_component_adequate"]
            if len(train_n) < 3:
                mode_res[s_name] = {"status": "insufficient_training", "train_count": len(train_n)}
                continue
            train_obs = np.array([candidates[str(n)][mode]["observation"]["frequency_hz"] for n in train_n])
            try:
                sol = ppa.fit(train_obs, np.array(train_n), NOMINAL_F1, 1e-4)
                f1_fit, b_fit = float(sol.x[0]), float(sol.x[1])
            except ValueError as error:
                mode_res[s_name] = {"status": "fit_error", "error": str(error), "train_count": len(train_n)}
                continue

            train_preds = ppa.partial_prediction([f1_fit, b_fit], np.array(train_n))
            train_errs = [cents(obs, pr) for obs, pr in zip(train_obs, train_preds)]

            preds = {}
            for b_name, b_partials in HOLDOUT_BANDS.items():
                h_n = [n for n in b_partials if n not in s_partials]
                b_errs, details = [], []
                for n in h_n:
                    pred_hz = float(ppa.partial_prediction([f1_fit, b_fit], np.array([n]))[0])
                    w_cents = float(ppa.holdout_window_cents(n))
                    in_win = np.flatnonzero(np.abs(1200.0 * np.log2(raw_peaks / pred_hz)) <= w_cents)
                    if in_win.size:
                        in_win = in_win[raw_rel[in_win] >= 1e-7]
                    if in_win.size:
                        if mode == "nearest":
                            picked_idx = in_win[np.argmin(np.abs(raw_peaks[in_win] - pred_hz))]
                        else:
                            picked_idx = in_win[np.argmax(raw_rel[in_win])]
                        candidate_hz = float(raw_peaks[picked_idx])
                        observation = observe(candidate_hz)
                        obs_hz = (observation["frequency_hz"]
                                  if observation["status"] == "single_component_adequate" else None)
                        err_c = cents(obs_hz, pred_hz)
                        if err_c is not None:
                            b_errs.append(err_c)
                        details.append({"n": n, "pred_hz": pred_hz, "raw_candidate_hz": candidate_hz,
                                        "obs_hz": obs_hz, "err_cents": err_c, "observation": observation})
                    else:
                        details.append({"n": n, "pred_hz": pred_hz, "obs_hz": None, "err_cents": None})

                rms_c = float(np.sqrt(np.mean(np.array(b_errs) ** 2))) if b_errs else None
                max_c = float(np.max(np.abs(np.array(b_errs)))) if b_errs else None
                preds[b_name] = {"rms_cents": rms_c, "max_cents": max_c, "reidentified": len(b_errs), "details": details}

            mode_res[s_name] = {
                "status": "fit_observed", "train_count": len(train_n),
                "f1_hz": f1_fit, "effective_B": b_fit,
                "train_rms_cents": float(np.sqrt(np.mean(np.array(train_errs) ** 2))),
                "train_max_cents": float(np.max(np.abs(np.array(train_errs)))),
                "holdout_predictions": preds
            }
        res[mode] = mode_res
    return res


def analyze_trajectories(win_cats, calib_rate):
    trajs = {}
    for n in range(1, 49):
        sn = str(n)
        early = win_cats.get("D_early", {}).get(sn)
        mid = win_cats.get("D_mid", {}).get(sn)
        late = win_cats.get("D_late", {}).get(sn)

        d_early_disc = calib_rate.get("D_early", {}).get("lines", {}).get(sn, {}).get("can_discriminate", False)
        d_mid_disc = calib_rate.get("D_mid", {}).get("lines", {}).get(sn, {}).get("can_discriminate", False)
        d_late_disc = calib_rate.get("D_late", {}).get("lines", {}).get(sn, {}).get("can_discriminate", False)

        e_hz = (early["strongest"]["observation"]["frequency_hz"] if early else None)
        m_hz = (mid["strongest"]["observation"]["frequency_hz"] if mid else None)
        l_hz = (late["strongest"]["observation"]["frequency_hz"] if late else None)

        e_to_m = cents(m_hz, e_hz)
        e_to_l = cents(l_hz, e_hz)

        # 峰轨迹只在其两个端点都通过自检且无竞争峰时解释，不把混合峰当一根弦。
        can_disc = (d_early_disc and d_late_disc and e_hz is not None and l_hz is not None
                    and not early["ambiguous"] and not late["ambiguous"])
        trajs[sn] = {
            "early_hz": e_hz, "mid_hz": m_hz, "late_hz": l_hz,
            "early_to_mid_cents": e_to_m, "early_to_late_cents": e_to_l,
            "can_discriminate": can_disc,
            "mid_delta_qualified": d_early_disc and d_mid_disc and e_hz is not None and m_hz is not None,
            "verdict": ("qualified_peak_shift_observed" if (can_disc and abs(e_to_l) > 1.0)
                        else ("non_discriminating_or_ambiguous" if not can_disc else "peak_stable_in_tested_window"))
        }
    return trajs


def synthesize_hypotheses(units, calibs):
    all_calib_pass = all(
        c[w]["all_lines_discriminating"] for c in calibs.values() for w in ("D_early", "D_mid", "D_late")
    )
    if not all_calib_pass:
        h1_status = "non_discriminating_estimator_limit"
        h1_note = "预检短窗已知基准自检未达标（超 max(0.005Hz, 0.05cents)），短窗估计器不具辨识度，不放宽阈值救结论，不可判定为 chirp。"
    else:
        d107 = [abs(t["early_to_late_cents"]) for u in units.values() if u["vel"] == 107
                for t in u["trajs"].values() if t["can_discriminate"] and t["early_to_late_cents"] is not None]
        d47 = [abs(t["early_to_late_cents"]) for u in units.values() if u["vel"] == 47
               for t in u["trajs"].values() if t["can_discriminate"] and t["early_to_late_cents"] is not None]
        m107 = float(np.mean(d107)) if d107 else None
        m47 = float(np.mean(d47)) if d47 else None
        if m107 is None or m47 is None:
            h1_status = "insufficient_observed_trajectories"
            h1_note = "至少一组力度缺少合格的跨窗轨迹，不以零漂移代替缺证。"
        elif m107 > m47 + 1.0:
            h1_status = "remains_plausible"
            h1_note = f"在标定窗口内观测到漂移具有力度相关性（v107={m107:.2f}c, v47={m47:.2f}c）。"
        else:
            h1_status = "no_velocity_dependent_peak_drift_established"
            h1_note = f"未建立显著的力度相关峰轨迹差异（v107={m107:.2f}c, v47={m47:.2f}c）；混合峰未获同弦身份，不据此否定张力机制。"

    amb_count = sum(1 for u in units.values() for c in u["w1_cats"].values() if c.get("ambiguous"))
    if amb_count > 0:
        h2_status = "remains_plausible"
        h2_note = f"W1 内存在 {amb_count} 处竞争峰或共享观察器不足以支持单分量的实例。"
    else:
        h2_status = "unresolved_isolated_peaks"
        h2_note = "搜索窗内局部单峰占优；注意：无多峰歧义不等于否定误编号（可能整窗偏移或锁定次生模态）。"

    h3_status = "unresolved"
    h3_note = "低阶子集拟合与留出重识已记录明细；未证明单一 B 全频段自洽，亦未排除特定分音离群。"

    rep_diffs = []
    for vel in VELOCITIES:
        for rate in RATES:
            u0 = units.get(f"n29-v{vel}-{rate}-rep0")
            u1 = units.get(f"n29-v{vel}-{rate}-rep1")
            if u0 and u1:
                for sn, c0 in u0["w1_cats"].items():
                    if sn in u1["w1_cats"]:
                        c1 = u1["w1_cats"][sn]
                        d = cents(c1["strongest"]["hz"], c0["strongest"]["hz"])
                        if d is not None:
                            rep_diffs.append(abs(d))
    max_rep = max(rep_diffs) if rep_diffs else None
    if max_rep is not None and max_rep < 0.05:
        h4_status = "consistent_deterministic_rendering"
        h4_note = f"跨重复最大差 {max_rep:.4f} cents；重复谱峰一致不能确证商业算法机理、量测绝对精度或一般性的确定性。"
    else:
        h4_status = "cross_repeat_spread_observed"
        h4_note = f"跨重复存在散布（max {max_rep} cents）。"
    rate_diffs = []
    for vel in VELOCITIES:
        for rep in REPEATS:
            a, b = units.get(f"n29-v{vel}-44100-rep{rep}"), units.get(f"n29-v{vel}-48000-rep{rep}")
            if a and b:
                for sn in set(a["w1_cats"]) & set(b["w1_cats"]):
                    rate_diffs.append(abs(cents(a["w1_cats"][sn]["strongest"]["hz"],
                                                b["w1_cats"][sn]["strongest"]["hz"])))
    h4_note += f" 双率共同候选峰最大差 {max(rate_diffs) if rate_diffs else None} cents（只作敏感性记录）。"

    return {
        "H1_tension_modulation_chirp": {"status": h1_status, "note": h1_note},
        "H2_peak_assignment_ambiguity": {"status": h2_status, "note": h2_note},
        "H3_static_stiffness_breakdown": {"status": h3_status, "note": h3_note},
        "H4_deterministic_rendering": {"status": h4_status, "note": h4_note},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--batch", action="append", required=True, help="已消耗参考批次路径（只读，可重复）")
    parser.add_argument("--analysis-tool", type=Path, default=Path(__file__).resolve().parent / "pilot-partial-analysis.py", help="冻结分析工具路径")
    parser.add_argument("--out", type=Path, required=True, help="全新输出目录（若已存在则直接拒绝）")
    args = parser.parse_args()

    out_dir = args.out.resolve()
    if out_dir.exists():
        raise SystemExit(f"--out 目录已存在，按规范拒绝覆盖: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=False)

    ppa = load_ppa(args.analysis_tool)
    ppa_hash = sha256_file(args.analysis_tool)
    self_hash = sha256_file(Path(__file__).resolve())
    batch_paths = [Path(p).resolve() for p in args.batch]

    print("================================================================================")
    print(" Task 39-2 参考侧 n29-v107 家族竞争假设有界诊断")
    print(f" PPA 工具散列: {ppa_hash}")
    print(f" 输出目录    : {out_dir}")
    print("================================================================================")

    # 1. 估计器预检标定（同一估计器，独立已知基准，无跳过）
    calibs = {}
    for rate in RATES:
        print(f"正在对采样率 {rate} Hz 进行预检自检标定...")
        calibs[str(rate)] = run_preflight(ppa, rate)

    with (out_dir / "calibration-results.json").open("w", encoding="utf-8") as f:
        json.dump(calibs, f, indent=2, ensure_ascii=False)

    # 2. 摄取已消耗批次中的最多 12 个 n29 WAV
    units = {}
    unit_hashes = {}
    missing = []
    for rate in RATES:
        for rep in REPEATS:
            sess = SESSIONS[(rate, rep)]
            for vel in VELOCITIES:
                uid = f"n29-v{vel}-{rate}-rep{rep}"
                wav = None
                for root in batch_paths:
                    cand = root / "sessions" / sess / "units" / uid / "export.wav"
                    if cand.is_file():
                        wav = cand
                        break
                if not wav:
                    print(f"  缺失单元: {uid}")
                    missing.append(uid)
                    continue

                whash = sha256_file(wav)
                unit_hashes[uid] = whash
                r_act, frames, left, right = ppa.read_wav_stereo(wav)

                win_cats = {}
                raw_peaks_w1 = None
                raw_rel_w1 = None
                for w_name, w_bounds in WINDOWS.items():
                    freqs, pwr = ppa.power_spectrum(left, right, r_act, w_bounds)
                    pks, rel, snrs = ppa.spectral_peaks(freqs, pwr, 35.0, 20000.0)
                    cats = extract_candidates(
                        ppa, pks, rel, snrs, NOMINAL_F1, 1e-4, left, right, r_act, w_bounds)
                    win_cats[w_name] = cats
                    if w_name == "W1":
                        raw_peaks_w1 = pks
                        raw_rel_w1 = rel

                def observe_w1(candidate):
                    bounds = WINDOWS["W1"]
                    return ppa.observer.observe_partial(
                        left, right, r_act, bounds, candidate,
                        min(0.2 * NOMINAL_F1, max(4.0 / (bounds[1] - bounds[0]), 0.01 * candidate)))

                fits = fit_and_holdouts(ppa, raw_peaks_w1, raw_rel_w1, win_cats.get("W1", {}), observe_w1)
                trajs = analyze_trajectories(win_cats, calibs.get(str(rate), {}))

                units[uid] = {
                    "uid": uid, "vel": vel, "rate": rate, "rep": rep,
                    "wav_sha256": whash, "duration_s": frames / r_act,
                    "w1_cats": win_cats.get("W1", {}),
                    "all_win_cats": win_cats,
                    "fits": fits, "trajs": trajs
                }
                print(f"  已分析: {uid}")

    # 3. 输出结构化结果
    with (out_dir / "n29-candidate-peaks.json").open("w", encoding="utf-8") as f:
        json.dump({uid: u["all_win_cats"] for uid, u in units.items()}, f, indent=2, ensure_ascii=False)

    with (out_dir / "low-order-fits.json").open("w", encoding="utf-8") as f:
        json.dump({uid: u["fits"] for uid, u in units.items()}, f, indent=2, ensure_ascii=False)

    with (out_dir / "temporal-trajectories.json").open("w", encoding="utf-8") as f:
        json.dump({uid: u["trajs"] for uid, u in units.items()}, f, indent=2, ensure_ascii=False)

    hypotheses = synthesize_hypotheses(units, calibs)
    summary = {
        "schema": "devpiano-task39-2-n29-family-hypothesis-summary-v2",
        "diagnostic_status": "diagnostic_only",
        "no_reverdict_certified": True,
        "note": 29, "note_name": "F1",
        "nominal_f1_hz": NOMINAL_F1,
        "units_analyzed": len(units),
        "units_expected": 12, "missing_units": missing,
        "windows": WINDOWS,
        "hypotheses_evaluation": hypotheses
    }
    with (out_dir / "family-hypothesis-summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    recipe = {
        "schema": "devpiano-task39-2-n29-family-hypothesis-recipe-v2",
        "script_sha256": self_hash,
        "analysis_tool_sha256": ppa_hash,
        "partial_observer_sha256": sha256_file(ppa.OBSERVER_PATH),
        "batch_roots": [str(p) for p in batch_paths],
        "configuration": {
            "windows": WINDOWS, "subsets": SUBSETS, "holdout_bands": HOLDOUT_BANDS,
            "calibration_lines": CALIBRATION_LINES, "nominal_f1": NOMINAL_F1,
            "calibration_recipe": {"duration_s": 4.5, "phase_seed": 42,
                                   "offbin_Hz": "0.113*(-1)**n",
                                   "amplitude": "1/sqrt(line_index+1)",
                                   "decay_tau_s": "max(0.4,3.5/sqrt(line_index+1))"},
        },
        "unit_source_hashes": unit_hashes
    }
    with (out_dir / "recipe.json").open("w", encoding="utf-8") as f:
        json.dump(recipe, f, indent=2, ensure_ascii=False)

    print("\n诊断报告与明细已全部生成（纯只读诊断，无重新判决）。")


if __name__ == "__main__":
    main()
