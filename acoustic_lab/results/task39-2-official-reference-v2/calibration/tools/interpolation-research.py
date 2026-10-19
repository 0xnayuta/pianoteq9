#!/usr/bin/env python3
"""Task 39-2 插值预研：仅训练锚点、整键留一，不读取 holdout 或 midfill。

运行于 Windows Python 标准库；输出离线模型诊断，不写生产表或宣称声学验收。
两桥采用公开的指数和形式；高音渐近线仅由每折剩余的 >=60 训练锚点拟合。
"""

import argparse
import bisect
import hashlib
import importlib.util
import itertools
import json
import math
import platform
import re
import statistics
import struct
import sys
from pathlib import Path

BASS = (21, 24, 28, 33, 36, 40, 43)
TREBLE = (45, 47, 48, 60, 69, 72, 84)
METHODS = ('log_linear', 'log_quadratic_left', 'log_quadratic_right',
           'log_pchip', 'two_bridge_anchored')
TARGETS = ((24, 28), (48, 60))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bracket(x, values):
    keys = sorted(values)
    i = bisect.bisect_left(keys, x)
    if i == 0 or i == len(keys):
        raise ValueError('仅允许锚点内部插值')
    return keys[i - 1], keys[i]


def linear(x, values):
    if x in values:
        return values[x]
    lo, hi = bracket(x, values)
    t = (x - lo) / (hi - lo)
    return math.exp((1.0 - t) * math.log(values[lo]) + t * math.log(values[hi]))


def quadratic(x, values, direction):
    if x in values:
        return values[x]
    lo, hi = bracket(x, values)
    left = [key for key in sorted(values) if key < lo]
    right = [key for key in sorted(values) if key > hi]
    if direction == 'left' and left:
        third = left[-1]
    elif direction == 'right' and right:
        third = right[0]
    else:
        third = left[-1] if left else right[0]
    support = (lo, hi, third)
    result = 0.0
    for key in support:
        weight = math.prod((x - other) / (key - other) for other in support if other != key)
        result += weight * math.log(values[key])
    return math.exp(result)


def pchip(x, values):
    if x in values:
        return values[x]
    keys = sorted(values)
    y = [math.log(values[key]) for key in keys]
    h = [b - a for a, b in zip(keys, keys[1:])]
    slopes = [(b - a) / step for a, b, step in zip(y, y[1:], h)]
    if len(keys) == 2:
        return linear(x, values)
    derivatives = [0.0] * len(keys)
    for i in range(1, len(keys) - 1):
        before, after = slopes[i - 1], slopes[i]
        if before * after > 0.0:
            w1 = 2.0 * h[i] + h[i - 1]
            w2 = h[i] + 2.0 * h[i - 1]
            derivatives[i] = (w1 + w2) / (w1 / before + w2 / after)

    def endpoint(first_h, second_h, first_slope, second_slope):
        value = ((2.0 * first_h + second_h) * first_slope - first_h * second_slope) / (first_h + second_h)
        if value * first_slope <= 0.0:
            return 0.0
        if first_slope * second_slope < 0.0 and abs(value) > 3.0 * abs(first_slope):
            return 3.0 * first_slope
        return value

    derivatives[0] = endpoint(h[0], h[1], slopes[0], slopes[1])
    derivatives[-1] = endpoint(h[-1], h[-2], slopes[-1], slopes[-2])
    lo, hi = bracket(x, values)
    i = keys.index(lo)
    t = (x - lo) / (hi - lo)
    value = ((2.0 * t**3 - 3.0 * t**2 + 1.0) * y[i]
             + (t**3 - 2.0 * t**2 + t) * h[i] * derivatives[i]
             + (-2.0 * t**3 + 3.0 * t**2) * y[i + 1]
             + (t**3 - t**2) * h[i] * derivatives[i + 1])
    return math.exp(value)


def golden(function, lo, hi, iterations=56):
    ratio = (math.sqrt(5.0) - 1.0) / 2.0
    a, b = hi - ratio * (hi - lo), lo + ratio * (hi - lo)
    fa, fb = function(a), function(b)
    for _ in range(iterations):
        if fa <= fb:
            hi, b, fb = b, a, fa
            a = hi - ratio * (hi - lo)
            fa = function(a)
        else:
            lo, a, fa = a, b, fb
            b = lo + ratio * (hi - lo)
            fb = function(b)
    x = (lo + hi) / 2.0
    return x, function(x)


def fit_two_bridge(values):
    high = {key: value for key, value in values.items() if key >= 60}
    center = statistics.mean(high)
    log_center = statistics.mean(math.log(value) for value in high.values())
    st = sum((key - center) * (math.log(value) - log_center) for key, value in high.items())
    st /= sum((key - center)**2 for key in high)
    yt = log_center - st * center
    observations = [(key, math.log(value)) for key, value in sorted(values.items())]

    def loss(slope, intercept):
        return statistics.mean(abs(math.log(math.exp(intercept + slope * (key - 33))
                                             + math.exp(st * key + yt)) - log_value)
                               for key, log_value in observations)

    def at_slope(slope):
        return golden(lambda intercept: loss(slope, intercept), -20.0, -5.0)

    # 固定扫描范围与精化规则，防止用已查看验证结果选择初值或优化区间。
    grid = [-0.30 + i * (0.299 / 100.0) for i in range(101)]
    scans = [at_slope(slope) for slope in grid]
    index = min(range(len(grid)), key=lambda i: scans[i][1])
    if 0 < index < len(grid) - 1:
        sb, _ = golden(lambda slope: at_slope(slope)[1], grid[index - 1], grid[index + 1], 40)
        yb, best_loss = at_slope(sb)
    else:
        sb, (yb, best_loss) = grid[index], scans[index]
    return {'s_B': sb, 'y_B_at_33': yb, 's_T': st, 'y_T': yt,
            'mean_absolute_log_residual': best_loss, 'slope_at_scan_boundary': index in (0, 100),
            'treble_training_notes': sorted(high)}


def two_bridge(x, fit):
    return math.exp(fit['y_B_at_33'] + fit['s_B'] * (x - 33)) + math.exp(fit['s_T'] * x + fit['y_T'])


def predict(method, x, values, fit=None):
    if x in values:
        return values[x]
    if method == 'log_linear':
        return linear(x, values)
    if method.startswith('log_quadratic_'):
        return quadratic(x, values, method.rsplit('_', 1)[1])
    if method == 'log_pchip':
        return pchip(x, values)
    if method == 'two_bridge_anchored':
        lo, hi = bracket(x, values)
        t = (x - lo) / (hi - lo)
        # 只保留模型曲率；去除端点偏差，保持现有实测锚点不变。
        correction = ((1.0 - t) * math.log(values[lo] / two_bridge(lo, fit))
                      + t * math.log(values[hi] / two_bridge(hi, fit)))
        return two_bridge(x, fit) * math.exp(correction)
    raise ValueError(method)


def signature(note, predicted, measured):
    last = 20 if note < 48 else (14 if note < 72 else 8)
    base = 7 if note < 72 else 5
    errors = [600.0 * math.log2(((1.0 + predicted * rank * rank) / (1.0 + predicted * base * base))
                               / ((1.0 + measured * rank * rank) / (1.0 + measured * base * base)))
              for rank in range(base + 1, last + 1)]
    return {'B_error_pct': (predicted / measured - 1.0) * 100.0,
            'analytic_ratio_rms_cents': math.sqrt(statistics.mean(error * error for error in errors)),
            'analytic_ratio_max_cents': max(abs(error) for error in errors),
            'analytic_base': base, 'analytic_compared_ranks': list(range(base + 1, last + 1))}


def summary(rows):
    return {'folds': len(rows),
            'median_abs_B_error_pct': statistics.median(abs(row['B_error_pct']) for row in rows),
            'max_abs_B_error_pct': max(abs(row['B_error_pct']) for row in rows),
            'median_analytic_ratio_rms_cents': statistics.median(row['analytic_ratio_rms_cents'] for row in rows),
            'max_analytic_ratio_rms_cents': max(row['analytic_ratio_rms_cents'] for row in rows)}


def production_values(path):
    text = path.read_text(encoding='utf-8')
    def array(name):
        match = re.search(r'constexpr float ' + name + r'\[\d+\]\s*=\s*\{([^}]+)\}', text)
        if match is None:
            raise ValueError('未找到冻结生产数组 ' + name)
        return [float(value.strip().removesuffix('f')) for value in match.group(1).split(',')]
    points = array('bMidi')
    values = array('bVals')
    return dict(zip((int(key) for key in points), values))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    options = parser.parse_args()
    inputs = options.inputs
    data = json.loads((inputs / 'anchors-v3.json').read_text(encoding='utf-8'))
    values = {int(key): row['B_median'] for key, row in data['measured_anchors'].items()}
    assert set(values) == set(BASS + TREBLE)
    assert not any(lo < key < hi for lo, hi in TARGETS for key in values)
    families = json.loads((inputs / 'families-revalidation.json').read_text(encoding='utf-8'))
    supported = {}
    for note in sorted(values):
        anchor = data['measured_anchors'][str(note)]
        velocities = anchor.get('velocities')
        if velocities is None:
            velocities = sorted(set(key.split('-')[1] for key in anchor['family_keys']))
        samples = []
        for identity, unit in families['units'].items():
            if unit['note'] != note or 'v' + str(unit['velocity']) not in velocities:
                continue
            if (unit.get('status') not in (None, 'ok') or unit['independent_status'] != 'ok'
                    or unit['independent_max_cents'] is None or unit['independent_rms_cents'] is None
                    or unit['f1_window_spread_cents'] is None
                    or unit['independent_max_cents'] > 3.0 or unit['independent_rms_cents'] > 1.0
                    or abs(unit['f1_window_spread_cents']) > 1.0 or unit['identified_partials'] < 5):
                continue
            samples.append({'identity': identity, **unit})
        if not samples:
            raise ValueError('无修订口径支持的训练锚点: ' + str(note))
        supported[str(note)] = {'production_anchor_B': values[note], 'training_samples': samples,
                               'raw_B_min': min(unit['effective_B'] for unit in samples),
                               'raw_B_max': max(unit['effective_B'] for unit in samples),
                               'registered_relative_spread': anchor['relative_spread']}

    folds = {method: [] for method in METHODS}
    for region_name, notes in (('bass', BASS), ('treble', TREBLE)):
        for note in notes[1:-1]:
            remaining = {key: value for key, value in values.items() if key != note}
            local = {key: remaining[key] for key in notes if key != note}
            fit = fit_two_bridge(remaining)
            for method in METHODS:
                predicted = predict(method, note, local, fit)
                row = {'region': region_name, 'held_out_note': note,
                       'training_notes': sorted(remaining), 'local_training_notes': sorted(local),
                       'predicted_B': predicted, 'measured_B': values[note],
                       **signature(note, predicted, values[note])}
                # 同音的所有力度/率/重复均随该键排除；此项检验跨条件散布，不重加权训练。
                sample_errors = [(predicted / unit['effective_B'] - 1.0) * 100.0
                                 for unit in supported[str(note)]['training_samples']]
                row['held_out_family_B_error_pct_range'] = [min(sample_errors), max(sample_errors)]
                folds[method].append(row)
    cv = {method: {'all': summary(rows),
                   'bass': summary([row for row in rows if row['region'] == 'bass']),
                   'treble': summary([row for row in rows if row['region'] == 'treble']),
                   'rows': rows} for method, rows in folds.items()}

    density = {}
    for name, notes, sparse in (('bass', BASS, (21, 36, 43)), ('treble', TREBLE, (45, 60, 84))):
        sparse_values = {key: values[key] for key in sparse}
        rows = []
        for note in notes:
            if note in sparse:
                continue
            dense_values = {key: values[key] for key in notes if key != note}
            coarse = linear(note, sparse_values)
            dense = linear(note, dense_values)
            rows.append({'held_out_note': note, 'sparse_training_notes': list(sparse),
                         'dense_training_notes': sorted(dense_values),
                         'sparse': signature(note, coarse, values[note]),
                         'dense': signature(note, dense, values[note])})
        density[name] = {'rows': rows, 'sparse': summary([row['sparse'] for row in rows]),
                         'dense': summary([row['dense'] for row in rows])}

    prod = production_values(inputs / 'Piano88KeyTable.h')
    baseline = {note: linear(note, prod) if note not in prod else prod[note] for note in range(21, 109)}
    fit = fit_two_bridge(values)
    segments = {}
    candidate_tables = {}
    for method in METHODS:
        candidate = dict(baseline)
        target_rows = []
        for lo, hi in TARGETS:
            local = {key: values[key] for key in (BASS if lo < 43 else TREBLE)}
            segment = []
            for note in range(lo + 1, hi):
                predicted = predict(method, note, local, fit)
                candidate[note] = predicted
                segment.append({'note': note, 'B': predicted,
                                'delta_vs_log_linear_pct': (predicted / linear(note, local) - 1.0) * 100.0})
            target_rows.append({'interval': [lo, hi], 'predictions_not_measurements': segment})
        segments[method] = target_rows
        candidate_tables[method] = candidate

    # 二次曲线第三支点可改变曲率符号；上下界是支点区间敏感性，不是统计置信区间。
    sensitivity = []
    for lo, hi in TARGETS:
        region = BASS if lo < 43 else TREBLE
        local = {key: values[key] for key in region}
        for method in ('log_quadratic_left', 'log_quadratic_right'):
            side = method.rsplit('_', 1)[1]
            third = max(key for key in region if key < lo) if side == 'left' else min(key for key in region if key > hi)
            predictions = []
            for limits in itertools.product(('B_min', 'B_max'), repeat=3):
                altered = dict(local)
                for key, limit in zip((lo, hi, third), limits):
                    altered[key] = data['measured_anchors'][str(key)][limit]
                predictions.append(quadratic((lo + hi) / 2.0, altered, side))
            sensitivity.append({'interval': [lo, hi], 'method': method, 'third_anchor': third,
                                'midpoint': (lo + hi) / 2.0,
                                'B_range_from_anchor_bounds': [min(predictions), max(predictions)]})

    spec = importlib.util.spec_from_file_location('previous_verification', inputs / 'pre-verification.py')
    simulator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(simulator)
    def extended(table):
        return {note: table[min(108, max(21, note))] for note in range(128)}
    baseline_ratios = simulator.stretch_ratios(extended(baseline))
    impacts = {}
    for method, candidate in candidate_tables.items():
        result, ratios, _ = simulator.analyse(extended(candidate))
        delta = {note: 1200.0 * math.log2(ratios[note] / baseline_ratios[note]) for note in range(21, 109)}
        impacts[method] = {**result,
                           'changed_B_notes': [note for note in candidate if abs(candidate[note] / baseline[note] - 1.0) > 1e-7],
                           'max_abs_stretch_change_cents': max(abs(value) for value in delta.values()),
                           'max_change_at_note': max(delta, key=lambda key: abs(delta[key])),
                           'changed_stretch_notes': [note for note, value in delta.items() if abs(value) > 1e-7],
                           'anchor_B_preserved': all(candidate[key] == baseline[key] for key in prod),
                           'outside_target_interiors_unchanged': all(candidate[note] == baseline[note] for note in baseline
                                                                       if not any(lo < note < hi for lo, hi in TARGETS))}
    # float32 生产常量/预计算与 float64 预研的差异单列，不当作实测误差。
    def f32(value):
        return struct.unpack('f', struct.pack('f', value))[0]
    anchor_delta = max(abs(values[key] / prod[key] - 1.0) * 100.0 for key in values)
    rounded_drift = max(abs(f32(value) / value - 1.0) * 100.0 for value in baseline.values())
    output = {'schema': 'devpiano-task39-2-interpolation-research-v1',
              'runtime': {'platform': platform.platform(), 'python': sys.version, 'executable': sys.executable},
              'inputs': {name: digest(inputs / name) for name in ('anchors-v3.json', 'families-revalidation.json',
                                                                'Piano88KeyTable.h', 'PianoTuning.h', 'pre-verification.py')},
              'data_boundary': {'training_notes': sorted(values), 'whole_note_cv_only': True,
                                'target_interiors_with_training_measurements': [],
                                'holdout_and_midfill_read': False,
                                'max_anchor_vs_production_rounding_pct': anchor_delta,
                                'max_final_float32_rounding_pct': rounded_drift},
              'supported_training_anchors': supported, 'cross_validation': cv,
              'density_simulation': density, 'target_predictions': segments,
              'quadratic_support_sensitivity': sensitivity, 'two_bridge_fit': fit,
              'two_bridge_raw_anchor_errors_pct': {str(key): (two_bridge(key, fit) / value - 1.0) * 100.0
                                                  for key, value in sorted(values.items())},
              'local_patch_impact_analytic_only': impacts,
              'limits': ['训练交叉验证不是新参考或跨生产者声音验收',
                         '分音误差为解析 B 曲线代理，非录音谱峰误差',
                         '锚点加密仅用既有训练点模拟，不伪造目标段内新实测',
                         '两桥 T 线由每折训练的 >=60 锚点拟合，不照搬文献截距',
                         '两桥端点校正是离线局部候选，不改变生产或既有准入锚点']}
    options.out.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print('runtime:', output['runtime']['platform'], sys.version.split()[0])
    print('training-only notes:', sorted(values), '; folds: whole-note 5 bass + 5 treble')
    for method, result in cv.items():
        print(method, 'bass median/max |B%|:', round(result['bass']['median_abs_B_error_pct'], 3),
              round(result['bass']['max_abs_B_error_pct'], 3), 'treble:',
              round(result['treble']['median_abs_B_error_pct'], 3), round(result['treble']['max_abs_B_error_pct'], 3))
    for name, result in density.items():
        print('density', name, 'sparse -> dense median |B%|:',
              round(result['sparse']['median_abs_B_error_pct'], 3), '->', round(result['dense']['median_abs_B_error_pct'], 3))
    for method, impact in impacts.items():
        print('patch', method, 'stretch max:', round(impact['max_abs_stretch_change_cents'], 6),
              'cents; increasing:', impact['f1_strictly_increasing'], 'anchors unchanged:', impact['anchor_B_preserved'])
    print('written:', options.out)


if __name__ == '__main__':
    main()
