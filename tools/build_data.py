#!/usr/bin/env python3
"""
Build the extension's bundled dataset from the public SmurfsTrsc repository and FlyBase's ID tables.

    git clone https://github.com/MichaelRera/SmurfsTrsc
    # from https://s3ftp.flybase.org/releases/current/precomputed_files/genes/ :
    #   fbgn_annotation_ID_*.tsv.gz  fbgn_fbtr_fbpp_*.tsv.gz  fbgn_NAseq_Uniprot_*.tsv.gz
    # and from ../synonyms/ : fb_synonym_*.tsv.gz
    python3 tools/build_data.py --smurfstrsc SmurfsTrsc --flybase <dir with the four tables> --out data

Output: data/genes/NN.json and data/products/NN.json (100 shards each, NN = last two digits of the ID) and
data/meta.json. Standard library only. The build stops unless the DEG counts equal those printed in the paper.
"""
import argparse, collections, glob, gzip, json, math, os, re, shutil, subprocess, sys

SOURCE = "Zane et al. 2023, Aging Cell 22(11):e13946"
DOI = "10.1111/acel.13946"
# Differentially expressed genes at padj <= 0.05 as printed in the paper: (total, up, down).
PAPER_COUNTS = {"sn": (3009, 1618, 1391), "s": (2320, 1385, 935), "n": (526, 415, 111)}
SIG = 0.05

# Table 1 of the paper: candidates for the longevity tests, with the selection method and deregulation it lists.
# Current FlyBase symbols: NF-YB is Nf-YB today and CG4360 is Sag1. Lifespan results as stated in the paper.
LONGEVITY = {
    "Adf1": ("i-cisTarget", "putative regulator of genes up in Smurfs"),
    "Aef1": ("i-cisTarget", "putative regulator of genes up in Smurfs"),
    "Sag1": ("i-cisTarget", "putative regulator of genes up in Smurfs (CG4360 in the paper)"),
    "FoxP": ("DESeq2 and i-cisTarget", "up in Smurfs and putative regulator of genes up in Smurfs"),
    "Hsf": ("i-cisTarget", "putative regulator of genes up in Smurfs"),
    "Trl": ("i-cisTarget", "putative regulator of genes up in Smurfs"),
    "dmrt93B": ("DESeq2", "up in Smurfs"),
    "Ets21C": ("DESeq2", "up in Smurfs"),
    "Hey": ("DESeq2", "up in Smurfs"),
    "kay": ("DESeq2", "up in Smurfs"),
    "Mef2": ("DESeq2 and i-cisTarget", "up in Smurfs and putative regulator of genes up in Smurfs"),
    "rib": ("DESeq2", "up in Smurfs"),
    "Ets96B": ("DESeq2", "down in Smurfs"),
    "GATAd": ("i-cisTarget", "putative regulator of genes down in Smurfs"),
    "GATAe": ("i-cisTarget", "putative regulator of genes down in Smurfs"),
    "Nf-YB": ("DESeq2 and i-cisTarget", "up in Smurfs and putative regulator of genes up in Smurfs"),
    "srp": ("i-cisTarget", "putative regulator of genes down in Smurfs"),
}
EXTENDS = {
    "Adf1": "Knock-down in adulthood extended mean lifespan by 11.8%",
    "Trl": "Knock-down in adulthood extended mean lifespan by 10.5%",
    "Sag1": "Whole-life knock-down extended mean lifespan by 12.4%",
}


def fnum(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def sig(x, n=3):
    return None if x is None else float(f"{x:.{n}g}")


def read_tsv(path):
    """Yield rows of an R write.table file (header one field shorter than the rows when row names are kept)."""
    with open(path, encoding="utf8", errors="replace") as f:
        header = f.readline().rstrip("\n").split("\t")
        for line in f:
            yield header, line.rstrip("\n").split("\t")


def open_gz(pattern, directory):
    hits = sorted(glob.glob(os.path.join(directory, pattern)))
    if not hits:
        sys.exit(f"missing {pattern} in {directory}")
    return gzip.open(hits[-1], "rt", encoding="utf8"), re.search(r"fb_(\d{4}_\d{2})", hits[-1]).group(1)


def load_flybase(directory):
    symbols, secondary = {}, collections.defaultdict(list)
    f, release = open_gz("fbgn_annotation_ID_fb_*.tsv.gz", directory)
    for line in f:
        if line.startswith("#") or not line.strip():
            continue
        p = line.rstrip("\n").split("\t")
        if p[1] != "Dmel":
            continue
        symbols[p[2]] = p[0]
        for old in filter(None, p[3].split(",")):
            secondary[old].append(p[2])
    products = {}
    f, _ = open_gz("fbgn_fbtr_fbpp_fb_*.tsv.gz", directory)
    for line in f:
        if line.startswith("#") or not line.strip():
            continue
        p = line.rstrip("\n").split("\t")
        for product in p[1:3]:
            if product:
                products[product] = p[0]
    uniprot = collections.defaultdict(set)
    f, _ = open_gz("fbgn_NAseq_Uniprot_fb_*.tsv.gz", directory)
    for line in f:
        if line.startswith("#") or not line.strip():
            continue
        p = line.rstrip("\n").split("\t")
        if len(p) > 5 and p[5] and p[1] == "Dmel":
            uniprot[p[5]].add(p[2])
    synonyms = collections.defaultdict(set)
    f, _ = open_gz("fb_synonym_fb_*.tsv.gz", directory)
    for line in f:
        p = line.rstrip("\n").split("\t")
        if not line.startswith("#") and p[0].startswith("FBgn") and p[1] == "Dmel":
            for name in (p[2], *p[-1].split("|")):
                if name:
                    synonyms[name].add(p[0])
    return symbols, secondary, products, uniprot, synonyms, release


def load_contrast(path):
    out = {}
    for _, p in read_tsv(path):
        q = fnum(p[6])
        # padj keeps full precision near the cut-off, so rounding can't move a gene across it
        out[p[0]] = [sig(fnum(p[1]), 4), sig(fnum(p[2]), 3), q if q is not None and 0.04 < q < 0.06 else sig(q, 2)]
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--smurfstrsc", required=True)
    ap.add_argument("--flybase", required=True)
    ap.add_argument("--out", default="data")
    a = ap.parse_args()
    d = os.path.join(a.smurfstrsc, "data")
    symbols, secondary, products, uniprot, synonyms, release = load_flybase(a.flybase)
    commit = subprocess.run(["git", "-C", a.smurfstrsc, "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()

    # --- expression ---
    with open(os.path.join(d, "vst_df.txt")) as f:
        samples = f.readline().split()
        vst = {p[0]: [round(float(x), 2) for x in p[1:]] for p in (l.split() for l in f)}
    if len(samples) != 32 or len(vst) != 15364:
        sys.exit(f"unexpected vst table: {len(samples)} samples, {len(vst)} genes")
    with open(os.path.join(d, "RNAseq_raw_data_matrix.tabular")) as f:
        f.readline()
        never_detected = {p[0] for p in (l.rstrip("\n").split("\t") for l in f) if not any(int(x) for x in p[1:])}

    # --- DESeq2 contrasts (independent of rounding: counted on the raw padj) ---
    paths = {"sn": "res_DEGS_SvsNS.txt", "s": "res_DEGS_S_40days_20days.txt", "n": "res_DEGS_NS_40days_20days.txt"}
    contrasts, exact = {}, {}
    for key, name in paths.items():
        path = os.path.join(d, "differential_expression", name)
        raw = [(fnum(p[2]), fnum(p[6])) for _, p in read_tsv(path)]
        hits = [lfc for lfc, q in raw if q is not None and q <= SIG]
        got = (len(hits), sum(x > 0 for x in hits), sum(x < 0 for x in hits))
        if got != PAPER_COUNTS[key]:
            sys.exit(f"{name}: {got} DEGs, the paper says {PAPER_COUNTS[key]}")
        contrasts[key] = load_contrast(path)
        exact[key] = {p[0]: fnum(p[2]) for _, p in read_tsv(path)}

    # --- the paper's other per-gene tables ---
    lm = collections.defaultdict(dict)
    lm_csv = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lm_terms.tsv")
    with open(lm_csv) as f:
        for line in f:
            gene, term, est, p = line.rstrip("\n").split("\t")
            lm[gene][term] = [sig(float(est), 3), sig(float(p), 2)]

    trend = {}
    for _, p in read_tsv(os.path.join(d, "nonSmurf_lm", "TABLE_S9_nonSmurf_lm_over_time.txt")):
        trend[p[1]] = [float(p[2]), float(p[3]), float(p[4]), p[6].strip()]

    proteins = collections.defaultdict(dict)
    n_prot = n_mapped = 0
    for key, name in (("y", "SvsNS_young_all_protein.txt"), ("o", "SvsNS_old_all_protein.txt")):
        for _, p in read_tsv(os.path.join(d, "proteomic", name)):
            lfc, pval = fnum(p[2]), fnum(p[3])
            if lfc is None or pval is None or p[1] in ("", "NA"):
                continue
            n_prot += 1
            genes = uniprot.get(p[1], ())
            n_mapped += bool(genes)
            for g in genes:
                best = proteins[g].get(key)
                if best is None or pval < best[1]:  # several accessions for one gene: keep the best supported
                    proteins[g][key] = [sig(lfc, 3), pval, p[1]]

    by_symbol = {s: g for g, s in symbols.items()}
    # GenAge rows name genes by the symbols of the time: FB2022_05 file, today's symbols, then unambiguous synonyms.
    old_symbol = dict(by_symbol)
    with open(os.path.join(d, "annotation", "dmel_human_orthologs_disease_fb_2022_05.tsv"), encoding="utf8") as f:
        for line in f:
            p = line.split("\t")
            if not line.startswith("#") and len(p) > 1:
                old_symbol.setdefault(p[1], p[0])
    def current_id(old):
        return old if old in symbols else (secondary.get(old) or [None])[0]
    genage = collections.defaultdict(list)
    missing_genage = set()
    for name, key in (("TABLE_S6_SMURFDEGs_genAge.txt", "sn"), ("TABLE_S6_OldNonSmurfDEGs_genAge.txt", "n")):
        for _, p in read_tsv(os.path.join(d, "human_ageing_atlas_genage_results", name)):
            g = current_id(old_symbol.get(p[1], ""))
            if g is None:
                # A synonym can name several genes (Sod, hk, dm...): the row's log2FC, copied from the contrast
                # table, says which one it was.
                lfc = float(p[2])
                hits = [c for c in synonyms.get(p[1], ()) if abs((exact[key].get(c) or 1e9) - lfc) < 1e-9]
                g = hits[0] if len(hits) == 1 else None
            row = [p[3], p[4], p[5], p[6]]
            if g is None:
                missing_genage.add(p[1])
            elif row not in genage[g]:
                genage[g].append(row)
    if missing_genage:
        print("GenAge symbols not resolved:", sorted(missing_genage), file=sys.stderr)
    atlas = collections.defaultdict(set)
    for _, p in read_tsv(os.path.join(d, "human_ageing_atlas_genage_results",
                                      "TABLE_S5_SMURFDEGsOldNonSmurfs_human_ageing_atlas.txt")):
        atlas[p[2]].add(p[1])
    if missing_genage:
        print("GenAge symbols not resolved:", sorted(missing_genage), file=sys.stderr)
    longevity = {}
    for s, (method, dereg) in LONGEVITY.items():
        if s not in by_symbol:
            sys.exit(f"longevity gene {s} is not a current FlyBase symbol")
        longevity[by_symbol[s]] = [method, dereg, EXTENDS.get(s, "")]

    # --- one record per 2019 gene ID, then re-keyed on current FlyBase IDs ---
    def record(old):
        r = {}
        if old in vst:
            r["e"] = vst[old]
            r["d"] = {k: contrasts[k][old] for k in contrasts if old in contrasts[k]}
        else:
            r["z"] = 1
        for key, table in (("lm", lm), ("t", trend), ("g", genage), ("h", atlas), ("l", longevity), ("p", proteins)):
            if old in table:
                r[key] = sorted(table[old]) if key == "h" else table[old]
        return r

    genes, merged = {}, collections.defaultdict(list)
    unmapped = 0
    for old in sorted(set(vst) | never_detected):
        if old in symbols:
            current = [old]
        elif old in secondary:
            current = secondary[old]
        else:
            unmapped += 1
            continue
        for g in current:
            merged[g].append(old)
    for g, olds in merged.items():
        # Genes FlyBase merged since 2019: show the best expressed one and say so.
        olds.sort(key=lambda o: -(contrasts["sn"].get(o, [0])[0] or 0))
        r = record(olds[0])
        r["s"] = symbols[g]
        if olds != [g]:
            r["o"] = olds
        genes[g] = r

    shutil.rmtree(os.path.join(a.out, "genes"), ignore_errors=True)
    shutil.rmtree(os.path.join(a.out, "products"), ignore_errors=True)
    os.makedirs(os.path.join(a.out, "genes"))
    os.makedirs(os.path.join(a.out, "products"))

    def write_shards(folder, items):
        shards = collections.defaultdict(dict)
        for key, value in items:
            shards[key[-2:]][key] = value
        for n in range(100):
            with open(os.path.join(a.out, folder, f"{n:02d}.json"), "w") as f:
                json.dump(shards.get(f"{n:02d}", {}), f, separators=(",", ":"), sort_keys=True)

    write_shards("genes", genes.items())
    write_shards("products", [(p, g) for p, g in products.items() if g in genes])

    meta = {
        "samples": samples, "source": SOURCE, "doi": DOI, "smurfstrsc_commit": commit, "flybase_release": release,
        "paper_counts": PAPER_COUNTS, "n_genes": len(genes),
    }
    with open(os.path.join(a.out, "meta.json"), "w") as f:
        json.dump(meta, f, separators=(",", ":"))
    tested = sum("e" in r for r in genes.values())
    print(f"{len(genes)} current genes ({tested} with expression, {len(genes) - tested} never detected), "
          f"{unmapped} 2019 IDs without a current gene, {sum('o' in r for r in genes.values())} re-keyed, "
          f"FlyBase {release}, SmurfsTrsc {commit}; proteomics {n_mapped}/{n_prot} rows mapped")


if __name__ == "__main__":
    main()
