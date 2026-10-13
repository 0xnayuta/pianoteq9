#!/usr/bin/env python3
"""
Pianoteq 9 官方归档的只读字符串线索工具。
只读取当前来源登记的官方样本，不加载程序，也不证明内部物理算法。
"""

import hashlib
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PROVENANCE_PATH = BASE_DIR / "acoustic_lab/results/task39-2-official-reference-v2/provenance.json"

def extract_strings(filepath, expected_sha256):
    raw = filepath.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("binary differs from the registered official archive")
    ascii_strings = [s.decode("latin1") for s in re.findall(rb"[\x20-\x7e]{4,}", raw)]
    utf16_strings = []
    for s in re.findall(rb"(?:[\x20-\x7e]\x00){4,}", raw):
        try:
            utf16_strings.append(s.decode("utf-16le"))
        except UnicodeError:
            pass
    return sorted(list(set(ascii_strings + utf16_strings)))

def main():
    try:
        provenance = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
        candidate = provenance["new_candidate"]
        source = BASE_DIR / candidate["directory"] / "Pianoteq 9.exe"
        strings = extract_strings(source, candidate["exe_sha256"])
    except (OSError, ValueError, KeyError) as error:
        print(f"[error] {error}", file=sys.stderr)
        return 1
    print(f"[*] Reading registered official archive: {source}")
    print(f"[*] SHA256: {candidate['exe_sha256']}")
    print("[*] Static strings only; no binary execution or internal algorithm authority.")
    print(f"[+] Total unique strings extracted: {len(strings)}")

    keywords = ["hammer", "string", "soundboard", "impedance", "resonance", "unison", "duplex"]
    matched = {kw: [s for s in strings if kw in s.lower() and len(s.strip()) < 80] for kw in keywords}
    for kw, items in matched.items():
        print(f"  - {kw.capitalize()}: {len(items)} candidates")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
