#!/usr/bin/env python3
"""Task 39-2 v2 Pilot 批次归档（参数化版，基于 archive_pilot_b0.py 的行为）。

流程（与 b0 归档一致）：
  1. 拒绝目标已存在或索引已含批次（重复运行安全）
  2. 备份 _index 四个索引到 /tmp
  3. 收集源文件清单（含空目录）-> 无覆盖复制 -> 逐文件 SHA-256 源/目标核验
  4. 写批次 evidence-manifest.json
  5. 追加 _index 的 inventory / classification.csv / migration-map / integrity-manifest

批次叙述性字段（result / authorization / deviations / summary 等）由 --meta 提供的
JSON 文件给定，避免把叙述硬编码进脚本。--meta 必填字段见 REQUIRED_META。
"""
import argparse
import csv
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timezone

DEFAULT_INDEX = "/mnt/g/source/projects/devpiano-evidence/_index"
REQUIRED_META = ("batch", "rel", "src_wsl", "dst_wsl", "phase", "task", "classification",
                 "result", "authorization", "gui_backend", "registered_deviations",
                 "content_summary", "current_status", "current_status_note", "generator")


def win(path: str) -> str:
    return path.replace("/mnt/g/", "G:\\").replace("/", "\\")


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meta", required=True, help="批次元数据 JSON（叙述字段）")
    parser.add_argument("--index-root", default=DEFAULT_INDEX)
    args = parser.parse_args()

    meta = json.load(open(args.meta, encoding="utf-8"))
    missing_fields = [key for key in REQUIRED_META if not meta.get(key)]
    if missing_fields:
        sys.exit("meta missing required fields: " + ", ".join(missing_fields))

    src = meta["src_wsl"]
    dst = meta["dst_wsl"]
    rel = meta["rel"]
    batch = meta["batch"]
    index_root = args.index_root

    if os.path.exists(dst):
        sys.exit("destination already exists: " + dst)
    inv_path = os.path.join(index_root, "inventory.json")
    inventory = json.load(open(inv_path, encoding="utf-8"))
    if any(record.get("archived_as") == rel for record in inventory["roots"]):
        sys.exit("batch already present in inventory: " + rel)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    for name in ("inventory.json", "classification.csv", "migration-map.json", "integrity-manifest.json"):
        shutil.copy2(os.path.join(index_root, name), os.path.join("/tmp", "idx-backup-%s-%s" % (stamp, name)))
    print("index backups written to /tmp (stamp %s)" % stamp)

    # 1) 源清单（文件 + 空目录）
    files, empty_dirs = [], []
    for root, dirs, filenames in os.walk(src):
        for directory in dirs:
            path = os.path.join(root, directory)
            if not os.listdir(path):
                empty_dirs.append(os.path.relpath(path, src).replace(os.sep, "/"))
        for filename in filenames:
            path = os.path.join(root, filename)
            files.append(os.path.relpath(path, src).replace(os.sep, "/"))
    files.sort()

    # 2) 复制（不覆盖）+ 散列
    total = 0
    records = []
    for relative in files:
        source = os.path.join(src, relative)
        target = os.path.join(dst, relative)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(source, target)
        size = os.path.getsize(source)
        total += size
        records.append({"src_wsl": source, "dst_wsl": target, "src_win": win(source), "dst_win": win(target),
                        "bytes": size, "sha256": sha256(source), "verified": False})
    for relative in empty_dirs:
        os.makedirs(os.path.join(dst, relative), exist_ok=True)

    # 3) 目标核验
    mismatch = missing = 0
    for record in records:
        if not os.path.exists(record["dst_wsl"]):
            missing += 1
            continue
        record["verified"] = sha256(record["dst_wsl"]) == record["sha256"]
        if not record["verified"]:
            mismatch += 1

    # 4) 批次 evidence-manifest.json
    now_iso = datetime.now(timezone.utc).isoformat()
    manifest = {
        "batch": batch,
        "archived_utc": now_iso,
        "result": meta["result"],
        "authorization": meta["authorization"],
        "gui_backend": meta["gui_backend"],
        "registered_deviations": meta["registered_deviations"],
        "empty_dirs_recreated": len(empty_dirs),
        "totals": {"files": len(records), "bytes": total,
                   "verified": sum(1 for record in records if record["verified"]),
                   "mismatch": mismatch, "missing": missing},
        "files": [{key: record[key] for key in ("src_win", "dst_win", "bytes", "sha256", "verified")}
                  for record in records],
    }
    manifest_path = os.path.join(dst, "evidence-manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
    manifest_sha = sha256(manifest_path)

    # 5) 索引追加
    inventory["roots"].append({
        "source_win": win(src),
        "source_wsl": src,
        "canonical_source_wsl": src,
        "archived_as": rel,
        "phase": meta["phase"],
        "task": meta["task"],
        "classification": meta["classification"],
        "files": len(records),
        "bytes": total,
        "generator": meta["generator"],
        "content_summary": meta["content_summary"],
        "current_status": meta["current_status"],
        "current_status_note": meta["current_status_note"],
        "archive_verified_utc": now_iso,
    })
    with open(inv_path, "w", encoding="utf-8") as handle:
        json.dump(inventory, handle, indent=1, ensure_ascii=False)

    with open(os.path.join(index_root, "classification.csv"), "a", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerow([
            win(src), rel, meta["phase"], meta["task"], meta["classification"],
            len(records), total, len(records), 0, 0,
            meta["content_summary"],
            meta.get("source_baseline", ""),
            meta.get("method_note", "全量复制；逐文件 SHA-256 源/目标核验；口径与 092853 / pilot-b0 相同"),
            meta["current_status"],
        ])

    migration_path = os.path.join(index_root, "migration-map.json")
    migration = json.load(open(migration_path, encoding="utf-8"))
    migration["roots"].append({
        "source_win": win(src),
        "dest_win": win(dst),
        "files_copied": len(records),
        "bytes_copied": total,
        "files_excluded": 0,
        "bytes_excluded": 0,
    })
    for record in records:
        migration["files"].append({"src_win": record["src_win"], "dst_win": record["dst_win"],
                                   "bytes": record["bytes"], "sha256": record["sha256"],
                                   "verified": record["verified"]})
    with open(migration_path, "w", encoding="utf-8") as handle:
        json.dump(migration, handle, indent=1, ensure_ascii=False)

    integrity_path = os.path.join(index_root, "integrity-manifest.json")
    integrity = json.load(open(integrity_path, encoding="utf-8"))
    integrity.setdefault("additional_archivals", []).append({
        "batch": rel,
        "source_root": win(src),
        "verified_at_utc": now_iso,
        "files_copied": len(records),
        "bytes_copied": total,
        "files_excluded": 0,
        "bytes_excluded": 0,
        "empty_dirs_recreated": len(empty_dirs),
        "method": "source/destination SHA256 for every newly copied file",
        "mismatch": mismatch,
        "missing": missing,
        "evidence_manifest_sha256": manifest_sha,
        "originals_deleted": False,
        "result": meta["current_status_note"],
        "historical_stats_above_unchanged": True,
    })
    with open(integrity_path, "w", encoding="utf-8") as handle:
        json.dump(integrity, handle, indent=1, ensure_ascii=False)

    print("archived files: %d bytes: %d" % (len(records), total))
    print("verified: %d mismatch: %d missing: %d" % (sum(1 for record in records if record["verified"]), mismatch, missing))
    print("empty dirs recreated: %d" % len(empty_dirs))
    print("evidence-manifest.json sha256: %s" % manifest_sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
