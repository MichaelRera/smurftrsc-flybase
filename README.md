# SmurfTrsc for FlyBase

Browser extension (Chrome, Edge, Brave and other Chromium browsers, and Firefox 140 or later) that shows a gene's expression in **Zane et al. 2023**, *Smurfness-based two-phase model of ageing helps deconvolve the ageing transcriptional signature*, *Aging Cell* 22(11):e13946, [doi:10.1111/acel.13946](https://doi.org/10.1111/acel.13946), on FlyBase gene (`FBgn`), protein (`FBpp`), transcript (`FBtr`) and allele (`FBal`) pages. Protein, transcript and allele pages show their parent gene.

The sibling of [ProteoCast for FlyBase](https://github.com/MichaelRera/proteocast-flybase), with one difference: the data ships inside the extension, so it needs no server, makes no network request of its own and has no host permission.

What it shows, at the top of the report (under ProteoCast's panel when both extensions are installed):
- a one-line verdict: up, down or no change in Smurfs, with log2FC, fold change and q, and the paper's category (Smurf gene, old non-Smurf gene, or both);
- the 32 samples as a strip plot by age and Smurf status, with group means, hover and keyboard tooltips, and a table of all values;
- the three DESeq2 contrasts: Smurf vs non-Smurf (16 vs 16), 40 vs 20 days in Smurfs (6 vs 4) and in non-Smurfs (6 vs 4);
- where the gene has one: its result in the linear model on Smurf status and age (File S5), progressive change in non-Smurfs (Table S9), Smurf vs non-Smurf proteomics in young and old flies (File S2), GenAge and Human Ageing Atlas matches, and the longevity tests (Table 1).

The Hide button collapses the panel to its verdict and is remembered.

## Install
- **Chrome, Edge, Brave:** [Chrome Web Store](https://chromewebstore.google.com/detail/smurftrsc-for-flybase/edlhmihcnmdcgmaaidgcpgolidinnkjp) (updates automatically).
- **Firefox:** [Firefox Add-ons](https://addons.mozilla.org/en-US/firefox/addon/smurftrsc-for-flybase/) (Firefox 140 or later), updates automatically.

More at https://michaelrera.github.io/tools/smurftrsc-flybase/.

From source (for development): `chrome://extensions` → enable *Developer mode* → *Load unpacked* → select this folder. In Firefox (140 or later): `about:debugging#/runtime/this-firefox` → *Load Temporary Add-on* → select `manifest.json`. Then open e.g. `https://flybase.org/reports/FBgn0014018`.

## Reading the numbers
- **log2FC** is DESeq2's unshrunken estimate, as quoted in the paper's text and tables; the paper's volcano plot uses apeglm-shrunken values instead. Low-count genes can show a large log2FC with no adjusted p: the panel calls these "not tested".
- **q** is DESeq2's adjusted p; significant means q ≤ 0.05, the paper's cut-off.
- **Expression** is the paper's VST table (`vst_df.txt`), on a log2-like scale. It floors near 6 for genes close to zero.
- The two 32-day "mixed" samples sit in the 30-day group, as in the paper's analysis.
- **Whole-body** RNA-seq of mated *Drs*-GFP females, so a change may come from a shift in tissue composition.
- **Longevity candidates** were picked as DEGs or as i-cisTarget regulators, so a gene like Trl or CG4360 (now Sag1) can be a candidate without its own transcript changing in Smurfs.
- **Proteomics** gives the best-supported accession when several map to the gene, with the paper's ANOVA p < 0.05 cut-off, not corrected for multiple testing. UniProt accessions shared by several genes (histones, for instance) appear under each.

## Gene IDs
The paper mapped reads to BDGP6.95, and FlyBase has moved on, so `tools/build_data.py` re-keys genes on the current release (FB2026_03): 131 published IDs now live under a new one, and the panel says so; where FlyBase merged genes, the best expressed is shown. 41 published IDs have no current gene and are left out. Genes with 0 reads in all samples (2,356) are reported as never detected, and genes annotated after BDGP6.95 as not in the dataset.

## Rebuilding the data
```
git clone https://github.com/MichaelRera/SmurfsTrsc
# fbgn_annotation_ID, fbgn_fbtr_fbpp and fbgn_NAseq_Uniprot from
#   https://s3ftp.flybase.org/releases/current/precomputed_files/genes/
# fb_synonym from .../precomputed_files/synonyms/
python3 tools/build_data.py --smurfstrsc SmurfsTrsc --flybase <dir with the four tables> --out data
python3 tests/test_data.py --smurfstrsc SmurfsTrsc
```
Standard library only. `data/` is committed, about 6.7 MB in 201 small JSON files: `genes/NN.json` and `products/NN.json`, 100 shards each keyed on the last two digits of the ID, plus `meta.json` with the sources' versions. The build stops unless the DEG counts equal the paper's (3009, 2320, 526, and their up and down splits). `tools/lm_terms.tsv` holds the significant terms of File S5, extracted from the workbook so the build stays dependency-free.

## FlyBase traps
- On load, FlyBase's sidebar script looks for a section header in the top half of the window; with none it throws, and its scroll and resize listeners are never attached. The panel therefore waits for that setup before going at the top of `.report` (falling back to below the first section if the setup never shows). Near the top of the page FlyBase's scroll handler can still throw and clear the sidebar highlight; the extension puts the highlight back on the first section.
- FlyBase's CDN answers headless Chromium with a 403 page that still has a `<body>`, so a headless test can pass on the error page. Test headed (`xvfb-run`) and check the page title.
- The gene pages throw a React `reading 'props'` error of their own, with or without this extension.

## License
The extension is free software under the [GNU General Public License v3.0](LICENSE); it started from ProteoCast for FlyBase. The bundled data comes from [SmurfsTrsc](https://github.com/MichaelRera/SmurfsTrsc) (MIT License, © 2022 Flaminia Zane and Michael Rera) and FlyBase's ID tables. Please cite Zane et al. 2023 when you use it.
