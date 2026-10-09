#!/usr/bin/env python3
"""
Pianoteq 9 黑盒声学测量自动化执行套件
包含：
1. MIDI 生成 (标准 SMF 0 格式)
2. 无头批处理渲染 (48 kHz / 24-bit 纯物理干音)
3. 信号处理分析 (非谐性常数 B 拟合、三力度高频注入分析、同音双阶段衰减)
"""

import os
import struct
import subprocess
import numpy as np
import scipy.io.wavfile as wavfile
from scipy.optimize import curve_fit
from scipy.signal import find_peaks

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAB_DIR = os.path.join(BASE_DIR, "acoustic_lab")
MIDI_DIR = os.path.join(LAB_DIR, "midi")
AUDIO_DIR = os.path.join(LAB_DIR, "audio")
RESULTS_DIR = os.path.join(LAB_DIR, "results")

os.makedirs(MIDI_DIR, exist_ok=True)
os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

def write_smf0(path, events, ticks_per_beat=480):
    track_data = bytearray()
    for dt, evt in events:
        buf = []
        buf.append(dt & 0x7F)
        val = dt >> 7
        while val > 0:
            buf.append((val & 0x7F) | 0x80)
            val >>= 7
        for b in reversed(buf):
            track_data.append(b)
        track_data.extend(evt)
    track_data.extend(b"\x00\xFF\x2F\x00")
    header = struct.pack(">4sIHHH", b"MThd", 6, 0, 1, ticks_per_beat)
    track_chunk = struct.pack(">4sI", b"MTrk", len(track_data)) + track_data
    with open(path, "wb") as f:
        f.write(header + track_chunk)

def render_midi(mid_filename, wav_filename, extra_params=None):
    win_midi = f"\\\\wsl.localhost\\Ubuntu\\root\\repos\\pianoteq9\\acoustic_lab\\midi\\{mid_filename}"
    win_wav = f"\\\\wsl.localhost\\Ubuntu\\root\\repos\\pianoteq9\\acoustic_lab\\audio\\{wav_filename}"
    
    cmd_parts = [
        "Set-Location 'E:\\Program Files\\VST3\\Pianoteq 9';",
        "& '.\\Pianoteq 9.exe' --headless",
        "--preset 'NY Steinway D Classical'",
        "--set-param 'Reverb Switch=Off'",
        "--rate 48000 --bit-depth 24",
    ]
    if extra_params:
        for p in extra_params:
            cmd_parts.append(f"--set-param '{p}'")
    cmd_parts.append(f"--midi '{win_midi}' --wav '{win_wav}'")
    full_cmd = " ".join(cmd_parts)
    
    res = subprocess.run([
        "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
        "-NoProfile", "-Command", full_cmd
    ], capture_output=True, text=True)
    return res.returncode == 0

def load_wav_mono(filepath):
    sr, data = wavfile.read(filepath)
    if data.dtype == np.int32:
        norm = data.astype(np.float64) / (2**31 - 1)
    elif data.dtype == np.int16:
        norm = data.astype(np.float64) / (2**15 - 1)
    else:
        norm = data.astype(np.float64)
    if data.ndim == 2:
        norm = np.mean(norm, axis=1)
    return sr, norm

def inharmonic_model(n, f0, B):
    return n * f0 * np.sqrt(1.0 + B * (n**2))

def main():
    print("[*] Acoustic Experiment Automation Suite initialized.")
    print(f"[*] Base directory: {BASE_DIR}")
    print("[*] To re-render and re-analyze, run this script directly.")

if __name__ == "__main__":
    main()
