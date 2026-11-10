#!/usr/bin/env python3
"""
Checks the bundled data against the SmurfsTrsc tables it was built from:

    python3 tests/test_data.py --smurfstrsc ../SmurfsTrsc
"""
import argparse, glob, json, os, sys

SIG = 0.05
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
FILES = {"sn": "res_DEGS_SvsNS.txt", "s": "res_DEGS_S_40days_20days.txt", "n": "res_DEGS_NS_40days_20days.txt"}


def num(x):
    try:
        return float(x)
    except ValueError:
        return None


ap = argparse.ArgumentParser()
ap.add_argument("--smurfstrsc", required=True)
a = ap.parse_args()
d = os.path.join(a.smurfstrsc, "data")

genes = {}
for f in glob.glob(os.path.join(ROOT, "genes", "*.json")):
    shard = json.load(open(f))
    assert all(g[-2:] == os.path.basename(f)[:2] for g in shard), f"gene in the wrong shard: {f}"
    genes.update(shard)
products = {}
for f in glob.glob(os.path.join(ROOT, "products", "*.json")):
    products.update(json.load(open(f)))
assert all(g in genes for g in products.values()), "product of an unknown gene"

failures = compared = 0
for key, name in FILES.items():
    raw = {}
    with open(os.path.join(d, "differential_expression", name)) as f:
        f.readline()
        for line in f:
            p = line.rstrip("\n").split("\t")
            raw[p[0]] = (num(p[2]), num(p[6]))
    for g, r in genes.items():
        src = r["o"][0] if "o" in r else g
        if src not in raw or "e" not in r:
            continue
        compared += 1
        lfc, q = raw[src]
        got = r["d"].get(key)
        same = got is not None and (q is None) == (got[2] is None) and (q is None or (q <= SIG) == (got[2] <= SIG))
        same = same and (lfc is None or abs(got[1] - lfc) <= max(abs(lfc) * 0.006, 1e-3))
        if not same:
            failures += 1
            print("MISMATCH", key, g, src, raw[src], got)

with open(os.path.join(d, "vst_df.txt")) as f:
    f.readline()
    for line in f:
        p = line.split()
        r = genes.get(p[0])
        if r and "o" not in r:
            compared += 1
            if any(abs(float(x) - y) > 0.0051 for x, y in zip(p[1:], r["e"])) or len(r["e"]) != 32:
                failures += 1
                print("MISMATCH vst", p[0])

print(f"{len(genes)} genes, {len(products)} products, {compared} values compared, {failures} failures")
sys.exit(1 if failures else 0)
