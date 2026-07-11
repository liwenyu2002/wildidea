#!/usr/bin/env python3
"""references/domains.json 数据完整性检查（纯标准库，本地或 CI 均可运行）。

校验：全局 id 唯一、必填字段非空、methods 非空且含 mechanism、quotas 加总为 9。
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "references" / "domains.json").read_text(encoding="utf-8"))

errors = []
seen_ids = set()

for pool_name, entries in DATA["pools"].items():
    for entry in entries:
        eid = entry.get("id", "")
        if not eid:
            errors.append(f"{pool_name}: entry missing id: {str(entry)[:60]}")
            continue
        if eid in seen_ids:
            errors.append(f"duplicate id: {eid}")
        seen_ids.add(eid)
        for field in ("domain", "anchor"):
            if not str(entry.get(field, "")).strip():
                errors.append(f"{eid}: empty field {field!r}")
        methods = entry.get("methods")
        if not isinstance(methods, list) or not methods:
            errors.append(f"{eid}: methods must be a non-empty list")
        else:
            for i, m in enumerate(methods):
                if not str(m.get("mechanism", "")).strip():
                    errors.append(f"{eid}: methods[{i}] has empty mechanism")

for ptype, quota in DATA["quotas"].items():
    total = sum(quota.values())
    if total != 9:
        errors.append(f"quotas[{ptype}] sums to {total}, expected 9")

if errors:
    print(f"{len(errors)} problem(s) in references/domains.json:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)

pool_sizes = ", ".join(f"{k}={len(v)}" for k, v in DATA["pools"].items())
print(f"domains.json OK: {len(seen_ids)} unique entries ({pool_sizes})")
