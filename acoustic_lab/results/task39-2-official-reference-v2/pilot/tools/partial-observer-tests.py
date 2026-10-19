#!/usr/bin/env python3
"""独立采样信号的估计精度、混合歧义、同频双衰减与数据边界回归。"""
import importlib.util
import math
from pathlib import Path
import unittest

import numpy as np

spec = importlib.util.spec_from_file_location('observer', Path(__file__).with_name('partial-observer.py'))
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


class SampledObserver(unittest.TestCase):
    rate = 44100
    window = (0.08, 3.8)

    def signal(self, lines, envelope=None, chirp=0.0):
        time = np.arange(int(4.2 * self.rate)) / self.rate
        samples = np.zeros((len(time), 2))
        for frequency, amplitude, phase in lines:
            env = envelope(time) if envelope else 1.0
            angle = 2 * math.pi * (frequency * time + chirp * time ** 2 / 2) + phase
            samples[:, 0] += amplitude * env * np.cos(angle)
            samples[:, 1] += amplitude * 0.8 * env * np.cos(angle + 0.23)
        return samples[:, 0], samples[:, 1]

    def observe(self, lines, envelope=None, chirp=0.0):
        left, right = self.signal(lines, envelope, chirp)
        return observer.observe_partial(left, right, self.rate, self.window, 440.1, 3.0)

    def assert_single(self, result, frequency):
        self.assertEqual(result['status'], 'single_component_adequate', result['reasons'])
        self.assertLess(abs(result['frequency_hz'] - frequency), 0.005)
        self.assertLessEqual(result['interval_hz'][0], frequency)
        self.assertGreaterEqual(result['interval_hz'][1], frequency)

    def test_off_bin_stationary_and_fast_damped_single_remain_precise(self):
        for tau in (None, 0.15, 0.4):
            with self.subTest(tau=tau):
                env = (lambda time: np.exp(-time / tau)) if tau else None
                self.assert_single(self.observe([(440.137, 0.05, 0.73)], env), 440.137)

    def test_same_frequency_two_decay_is_not_a_physical_doublet(self):
        result = self.observe([(440.137, 0.05, 1.0)],
                              lambda time: 0.6 * np.exp(-time / 0.2) + 0.4 * np.exp(-time / 2.0))
        self.assert_single(result, 440.137)

    def test_weak_and_phase_varying_unresolved_mixtures_do_not_claim_single(self):
        for ratio, phase in ((1.0, 0.0), (1.0, math.pi), (0.1, 0.7)):
            with self.subTest(ratio=ratio, phase=phase):
                result = self.observe([(440.0, 0.05, 0.2), (440.4, 0.05 * ratio, phase)])
                self.assertNotEqual(result['status'], 'single_component_adequate', result['diagnostics'])
                self.assertIsNone(result['frequency_hz'])

    def test_resolved_pair_returns_component_frequencies(self):
        result = self.observe([(440.0, 0.05, 0.3), (441.5, 0.035, 1.1)])
        self.assertEqual(result['status'], 'resolved_components', result['reasons'])
        frequencies = sorted(component['frequency_hz'] for component in result['components'])
        self.assertEqual(len(frequencies), 2)
        self.assertLess(abs(frequencies[0] - 440.0), 0.01)
        self.assertLess(abs(frequencies[1] - 441.5), 0.01)

    def test_nonstationary_signal_cannot_claim_precise_scalar(self):
        result = self.observe([(440.0, 0.05, 0.3)], chirp=0.6)
        self.assertEqual(result['status'], 'ambiguous', result['reasons'])
        self.assertIsNone(result['frequency_hz'])

    def test_search_edge_cannot_hide_a_coherent_companion(self):
        left, right = self.signal([(1188.06, 0.03, 0.3), (1177.13, 0.03, 0.9)])
        result = observer.observe_partial(left, right, self.rate, self.window, 1193.73, 12.0)
        self.assertEqual(result['status'], 'ambiguous', result['reasons'])
        self.assertIsNone(result['frequency_hz'])

    def test_silence_short_windows_and_malformed_channels_have_explicit_outcomes(self):
        zero = np.zeros(int(4.2 * self.rate))
        result = observer.observe_partial(zero, zero, self.rate, self.window, 440.1, 3.0)
        self.assertEqual(result['status'], 'ambiguous')
        result = observer.observe_partial(zero, zero, self.rate, (0.0, 0.1), 440.1, 3.0)
        self.assertEqual(result['status'], 'ambiguous')
        for args in ((zero[:-1], zero, self.rate, self.window, 440.1, 3.0),
                     (zero, zero, self.rate, (0.0, 6.0), 440.1, 3.0),
                     (zero, zero, self.rate, self.window, 1.0, 3.0)):
            with self.assertRaises(ValueError):
                observer.observe_partial(*args)


if __name__ == '__main__':
    unittest.main()
