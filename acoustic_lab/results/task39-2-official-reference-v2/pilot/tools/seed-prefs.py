#!/usr/bin/env python3
"""为 interp-training 会话生成 prefs-seed：改写 RecentWav 预置本会话导出路径。

机制（midfill-20261014-001725 已验证）：导出对话框 Target file 目录继承 RecentWav
记录路径；把 RecentWav 预置为本会话三条导出路径即可免除运行时 D1 修正。
只改写 RecentWav 一行；其余字段与模板逐字节保持。seed 与模板的 diff 作为会话证据保留。
"""

import argparse
import re
import xml.etree.ElementTree as ElementTree
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, help="批次 prefs-template/<rate>/session-prefs.xml")
    parser.add_argument("--user-prefs", required=True, help="批次 prefs-template/<rate>/user-prefs.xml")
    parser.add_argument("--out-dir", required=True, help="会话 prefs-seed 输出目录")
    parser.add_argument("--note", type=int, required=True)
    parser.add_argument("--wav-dir-win", required=True, help=r"本会话 Documents（Windows 路径，使用反斜杠）")
    args = parser.parse_args()

    template = Path(args.template).read_text(encoding="utf-8")
    recent = "&#10;".join(f"{args.wav_dir_win}\\{args.note}-v{velocity}.wav" for velocity in (98, 70, 41))
    replacement = f'<VALUE name="RecentWav" val="{recent}"/>'
    # 函数替换：替换串中的反斜杠按字面量处理（Windows 路径含 \d \s 等序列）。
    new_text, count = re.subn(r'<VALUE name="RecentWav" val="[^"]*"/>',
                              lambda _match: replacement, template)
    if count != 1:
        raise SystemExit(f"RecentWav substitution count {count} != 1")

    # 结构自检：改写后的 XML 必须可解析，且 RecentWav 值等于目标路径。
    root = ElementTree.fromstring(new_text)
    values = {node.get("name"): node.get("val") for node in root.findall("VALUE")}
    if values.get("RecentWav") != recent.replace("&#10;", "\n"):
        raise SystemExit("RecentWav readback mismatch after substitution")

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "session-prefs.xml").write_text(new_text, encoding="utf-8")
    (out / "user-prefs.xml").write_text(Path(args.user_prefs).read_text(encoding="utf-8"), encoding="utf-8")
    print(f"seed written: {out} note={args.note} recent_wav_dir={args.wav_dir_win}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
