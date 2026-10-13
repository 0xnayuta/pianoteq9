#!/usr/bin/env python3
"""Task 39-2 v2 Pilot 受保护文件快照与比对。

受保护范围（规则生成，规则文本随快照落盘）：
  1. /root/repos/devpiano/source/**            全部源码（300+ 文件）
  2. pianoteq9 task39-2 v2 任务目录全部文件     协议、方案、pilot 工具与 stimulus
  3. 固定清单：证据库 6 个既有 GUI/协议脚本     与 b0 批次受保护清单一致

语义：批次前后各生成一次快照，比对必须 missing=0 且 changed=0；
added 单独列出（新增文件不算破坏，但受保护范围内出现新增需人工审视）。
跳过 __pycache__ 与 *.pyc。

子命令：
  generate --out <json>
  compare  --before <json> --after <json> --out <json>
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DEVPIANO_ROOT = Path("/root/repos/devpiano")
PIANOTEQ9_ROOT = Path("/root/repos/pianoteq9")
V2_DIR = PIANOTEQ9_ROOT / "acoustic_lab/results/task39-2-official-reference-v2"
EVIDENCE_ROOT = Path("/mnt/g/source/projects/devpiano-evidence")

FIXED_EVIDENCE_FILES = [
    "phase39/task39-2/official925-transition-20261011-203015/official-ui-freeze/inspect-owned-window.ps1",
    "phase39/task39-2/official925-transition-20261011-203015/official-ui-freeze/inspect-single-session.ps1",
    "phase39/task39-2/official925-transition-20261011-203015/official-ui-freeze/launch-ui.py",
    "phase39/task39-2/official925-transition-20261011-203015/official-ui-freeze/standard-closure.ps1",
    "phase39/task39-2/official925-transition-20261011-203015/official-ui-freeze/ui-controller.py",
    "windows-mcp/pianoteq-gui-validation/gui-20261011-225457/owned-session.ps1",
]

RULE_TEXT = (
    "devpiano source/** + pianoteq9 task39-2-official-reference-v2/** + "
    "6 fixed evidence scripts from the b0 protected list"
)


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def skipped(path: Path) -> bool:
    return "__pycache__" in path.parts or path.suffix == ".pyc"


def collect_files() -> list:
    files = []
    for root in (DEVPIANO_ROOT / "source", V2_DIR):
        for path in sorted(root.rglob("*")):
            if path.is_file() and not skipped(path):
                files.append(path)
    for relative in FIXED_EVIDENCE_FILES:
        files.append(EVIDENCE_ROOT / relative)
    return files


def cmd_generate(args) -> int:
    files = collect_files()
    snapshot = {
        "schema": "devpiano-protected-snapshot",
        "generated_utc": now_utc(),
        "rule": RULE_TEXT,
        "count": len(files),
        "files": {},
    }
    missing = []
    for path in files:
        if not path.is_file():
            missing.append(str(path))
            continue
        snapshot["files"][str(path)] = sha256_file(path)
    snapshot["count"] = len(snapshot["files"])
    snapshot["rule_missing"] = missing
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print("protected snapshot: %d files -> %s" % (snapshot["count"], out))
    for item in missing:
        print("  rule target missing: %s" % item)
    return 0 if not missing else 2


def cmd_compare(args) -> int:
    before = json.loads(Path(args.before).read_text(encoding="utf-8-sig"))
    after = json.loads(Path(args.after).read_text(encoding="utf-8-sig"))
    before_files = before["files"]
    after_files = after["files"]
    missing = sorted(set(before_files) - set(after_files))
    added = sorted(set(after_files) - set(before_files))
    changed = []
    for path in sorted(set(before_files) & set(after_files)):
        if before_files[path] != after_files[path]:
            changed.append({"path": path, "before_sha256": before_files[path], "after_sha256": after_files[path]})
    report = {
        "schema": "devpiano-protected-comparison",
        "before": args.before,
        "after": args.after,
        "compared_utc": now_utc(),
        "checked": len(set(before_files) & set(after_files)),
        "missing": missing,
        "changed": changed,
        "added": added,
        "ok": not missing and not changed,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print("protected compare: checked=%d missing=%d changed=%d added=%d ok=%s"
          % (report["checked"], len(missing), len(changed), len(added), report["ok"]))
    for item in missing:
        print("  MISSING: %s" % item)
    for item in changed:
        print("  CHANGED: %s" % item["path"])
    for item in added:
        print("  added: %s" % item)
    return 0 if report["ok"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_gen = sub.add_parser("generate")
    p_gen.add_argument("--out", required=True)
    p_gen.set_defaults(func=cmd_generate)
    p_cmp = sub.add_parser("compare")
    p_cmp.add_argument("--before", required=True)
    p_cmp.add_argument("--after", required=True)
    p_cmp.add_argument("--out", required=True)
    p_cmp.set_defaults(func=cmd_compare)
    args = parser.parse_args()
    try:
        return args.func(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print("protected-snapshot failed: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
