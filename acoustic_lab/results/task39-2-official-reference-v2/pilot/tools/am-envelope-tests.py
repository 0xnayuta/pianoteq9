#!/usr/bin/env python3
"""AM 解释、相干等价与静态频率认证的行为边界。"""
import copy
import importlib.util
import json
import math
from pathlib import Path
import unittest

import numpy as np

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("am_study_tests", HERE / "am-envelope-study.py")
study = importlib.util.module_from_spec(spec)
spec.loader.exec_module(study)
model = study.load_module(HERE / "am-envelope-observer.py", "am_model_tests")
registration = json.loads((HERE.parent / "am-envelope-preregistration.json").read_text(encoding="utf-8"))
config = registration["observation"]["model_config"]


def fixture(kind):
    return {"id": "regression", "kind": kind, "rate": 44100, "carrier_hz": 279.173,
            "modulation_hz": 0.44, "depth": 0.48, "decay_per_s": 0.21,
            "carrier_phase_rad": 0.72, "modulation_phase_rad": -0.9,
            "seed": 910011, "amplitude": 0.05, "noise_sigma": 2e-6,
            "envelope_expectation": "supported", "static_expectation": "not_admitted"}


class EnvelopeClaimSeparation(unittest.TestCase):
    def explain(self, recipe):
        values = study.synthesize(recipe, registration["generator"])
        # 与研究 CLI 相同量化尺度，但测试不依赖磁盘或真实顶层窗口。
        pcm = np.rint(values * 8388608) / 8388608
        observation = registration["observation"]
        result = model.explain_envelope(pcm[:, 0], pcm[:, 1], recipe["rate"],
                                        observation["training_window_s"], observation["prediction_end_s"], config)
        return pcm, result

    def test_envelope_prediction_does_not_certify_a_static_single_component(self):
        recipe = fixture("am_product")
        pcm, envelope = self.explain(recipe)
        self.assertEqual(envelope["status"], "supported", envelope["reasons"])
        self.assertLess(abs(envelope["carrier_hz"] - recipe["carrier_hz"]), 0.005)
        candidate = study.spectral_candidate(pcm, recipe["rate"], registration["observation"]["training_window_s"], config)
        static = model.partial.observe_partial(pcm[:, 0], pcm[:, 1], recipe["rate"], (0.08, 3.8), candidate, 3.0)
        self.assertNotEqual(static["status"], "single_component_adequate")
        score = study.assess(recipe, envelope, static, registration)
        self.assertTrue(score["passed"], score["violations"])

    def test_coherent_triplet_has_same_waveform_and_envelope_explanation(self):
        product, triplet = fixture("am_product"), fixture("coherent_triplet")
        a = study.synthesize(product, registration["generator"])
        b = study.synthesize(triplet, registration["generator"])
        self.assertLess(float(np.max(np.abs(a - b))), 1e-10)
        _, envelope = self.explain(triplet)
        self.assertEqual(envelope["status"], "supported", envelope["reasons"])
        self.assertLess(abs(envelope["parameters"]["modulation_hz"] - triplet["modulation_hz"]), 0.01)

    def test_non_AM_asymmetric_sidebands_do_not_receive_envelope_support(self):
        _, result = self.explain(fixture("asymmetric_triplet"))
        self.assertNotEqual(result["status"], "supported")

    def test_heldout_corruption_cannot_be_repaired_by_refitting(self):
        recipe = fixture("am_product")
        pcm, supported = self.explain(recipe)
        self.assertEqual(supported["status"], "supported", supported["reasons"])
        corrupted = pcm.copy()
        stop = int(registration["observation"]["training_window_s"][1] * recipe["rate"])
        corrupted[stop:] *= -1
        changed = model.explain_envelope(corrupted[:, 0], corrupted[:, 1], recipe["rate"],
                                         (0.08, 2.68), 3.8, config)
        self.assertEqual(changed["status"], "inadequate")
        first = supported["diagnostics"]["candidate_parameters"]["carrier_hz"]
        second = changed["diagnostics"]["candidate_parameters"]["carrier_hz"]
        self.assertEqual(first, second)

    def test_constant_decay_does_not_invent_modulation(self):
        _, result = self.explain(fixture("constant_decay"))
        self.assertEqual(result["status"], "unidentifiable")

    def test_role_overlap_and_missing_equivalence_partner_are_refused(self):
        for mutation in ("seed", "pair"):
            plan = copy.deepcopy(registration)
            if mutation == "seed":
                plan["cases"]["qualification"][0]["seed"] = plan["cases"]["development"][0]["seed"]
            else:
                plan["cases"]["qualification"] = plan["cases"]["qualification"][1:]
            with self.assertRaises(ValueError):
                study.validate_registration(plan)


if __name__ == "__main__":
    unittest.main()
