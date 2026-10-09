#!/usr/bin/env python3
"""
Pianoteq 9 声学参数字典与特性清单提取工具
扫描 binaries/Pianoteq 9.vst3plugin 并解析官方 HTML 文档中的物理声学定义
"""

import os
import re
from html.parser import HTMLParser

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN_PATH = os.path.join(BASE_DIR, "binaries", "Pianoteq 9.vst3plugin")
DOC_PATH = os.path.join(BASE_DIR, "binaries", "Documentation", "pianoteq-english.html")

def extract_strings(filepath):
    with open(filepath, "rb") as f:
        raw = f.read()
    ascii_strings = [s.decode("latin1") for s in re.findall(rb"[\x20-\x7e]{4,}", raw)]
    utf16_strings = []
    for s in re.findall(rb"(?:[\x20-\x7e]\x00){4,}", raw):
        try:
            utf16_strings.append(s.decode("utf-16le"))
        except:
            pass
    return sorted(list(set(ascii_strings + utf16_strings)))

def main():
    print(f"[*] Scanning binary: {PLUGIN_PATH}")
    if not os.path.exists(PLUGIN_PATH):
        print(f"[-] Binary not found: {PLUGIN_PATH}")
        return
    strings = extract_strings(PLUGIN_PATH)
    print(f"[+] Total unique strings extracted: {len(strings)}")

    keywords = ["hammer", "string", "soundboard", "impedance", "resonance", "unison", "duplex"]
    matched = {kw: [s for s in strings if kw in s.lower() and len(s.strip()) < 80] for kw in keywords}
    for kw, items in matched.items():
        print(f"  - {kw.capitalize()}: {len(items)} candidates")

if __name__ == "__main__":
    main()
