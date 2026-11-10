// Content script: finds the gene behind the current FlyBase report (FBgn, FBpp, FBtr or FBal page) and injects
// a panel with that gene's expression in Zane et al. 2023.

(() => {
  const PANEL_ID = "smurftrsc-panel-host";
  const SIG = 0.05; // padj cut-off of the paper
  let currentId = null;

  function idFromUrl() {
    // Report pages only (/reports/FBgn0000490, optionally .htm/.html): other FlyBase pages (JBrowse, downloads,
    // hit lists, ontology browsers, ...) can carry an ID in their path too and must get no panel.
    const m = location.pathname.match(/^\/reports\/((FBgn|FBpp|FBtr|FBal)\d{7})(?:\.html?)?$/);
    return m ? m[1] : null;
  }

  // Allele report pages are server-rendered: the gene is the FBgn link in the "Associated gene" row.
  function alleleGene() {
    const label = [...document.querySelectorAll("div, th, td, dt")]
      .find((e) => e.children.length < 6 && /^\s*Associated gene\s*$/.test(e.textContent));
    const link = label && [...(label.closest("tr") || label.parentElement).querySelectorAll("a")]
      .map((a) => (a.getAttribute("href") || "").match(/FBgn\d{7}/)).find(Boolean);
    return link ? link[0] : null;
  }

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
  const fmtFC = (x) => (Math.abs(x) < 0.005 ? "" : x > 0 ? "+" : "−") + Math.abs(x).toFixed(2);
  function fmtP(p) {
    if (p === 0) return "≤1e−300"; // underflow; no "<", so the result is safe inside HTML
    return p >= 0.001 ? String(+p.toPrecision(2)) : p.toExponential(1).replace("e-", "e−");
  }
  const linearFold = (lfc) => {
    const f = Math.pow(2, Math.abs(lfc));
    return f >= 100 ? `×${Math.round(f)}` : `×${f.toFixed(f < 10 ? 2 : 1)}`;
  };

  // One DESeq2 contrast as a verdict: { word, arrow, tested, sig }.
  function verdict(c) {
    if (!c || c[1] == null) return { word: "not tested", arrow: "", tested: false, sig: false };
    const [, lfc, q] = c;
    if (q == null) return { word: "not tested", arrow: "", tested: false, sig: false };
    if (q > SIG) return { word: "no change", arrow: "", tested: true, sig: false };
    return lfc > 0 ? { word: "up", arrow: "▲", tested: true, sig: true } : { word: "down", arrow: "▼", tested: true, sig: true };
  }

  // The paper's categories: changed in Smurfs, in old non-Smurfs, in both, or in neither.
  function category(d) {
    const s = verdict(d.sn).sig, n = verdict(d.n).sig;
    if (s && n) return "Smurf & old non-Smurf gene";
    if (s) return "Smurf gene";
    if (n) return "old non-Smurf gene";
    return "";
  }

  function parseSample(name) {
    const age = +name.slice(0, 2);
    return {
      name, age, group: age === 32 ? 30 : age, // the two 32-day "mixed" samples are analysed with the 30-day ones
      smurf: !name.includes("n"),
      time: name.includes("M") ? "mixed, unknown time since the transition" : name.includes("1d") ? "1 day after the transition" : "5 h after the transition",
    };
  }

  // Strip plot of the 32 samples: one axis (VST expression), three age groups, two series. Smurfs are solid and
  // non-Smurfs hollow, so the two stay apart without colour. Returns SVG markup; hover and focus are wired by the caller.
  function stripPlot(values, samples) {
    const W = 600, H = 150, left = 50, right = 6, top = 6, bottom = 20;
    const plotH = H - top - bottom;
    let lo = Math.min(...values), hi = Math.max(...values);
    if (hi - lo < 1) { const mid = (hi + lo) / 2; lo = mid - 0.5; hi = mid + 0.5; }
    const pad = (hi - lo) * 0.06; lo -= pad; hi += pad;
    const y = (v) => top + plotH * (1 - (v - lo) / (hi - lo));
    const step = (hi - lo) / 4 > 2 ? 2 : (hi - lo) / 4 > 1 ? 1 : 0.5;
    let grid = "";
    for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) {
      grid += `<line class="grid" x1="${left}" x2="${W - right}" y1="${y(t)}" y2="${y(t)}"/>
        <text class="tick" x="${left - 6}" y="${y(t) + 3.5}" text-anchor="end">${+t.toFixed(1)}</text>`;
    }
    const groups = [20, 30, 40], bandW = (W - left - right) / 3;
    let marks = "";
    groups.forEach((g, gi) => {
      const cx = left + bandW * (gi + 0.5);
      const counts = [];
      [false, true].forEach((smurf, si) => {
        const idx = samples.map((s, i) => (s.group === g && s.smurf === smurf ? i : -1)).filter((i) => i >= 0);
        counts.push(idx.length);
        const x0 = cx + (si ? 1 : -1) * bandW * 0.2;
        const mean = idx.reduce((a, i) => a + values[i], 0) / idx.length;
        marks += `<line class="mean" x1="${x0 - 22}" x2="${x0 + 22}" y1="${y(mean)}" y2="${y(mean)}"/>`;
        // spread dots sideways only where they would overlap
        const placed = [];
        for (const i of [...idx].sort((a, b) => values[a] - values[b])) {
          const py = y(values[i]);
          let off = 0;
          for (const k of [0, 1, -1, 2, -2, 3, -3]) {
            off = k * 10;
            if (!placed.some((p) => Math.abs(p.off - off) < 10 && Math.abs(p.py - py) < 10)) break;
          }
          placed.push({ off, py });
          marks += `<circle class="dot ${smurf ? "s" : "n"}" cx="${x0 + off}" cy="${py}" r="4.5"/>
            <circle class="hit" cx="${x0 + off}" cy="${py}" r="11" tabindex="0" data-i="${i}" role="img"
              aria-label="${esc(samples[i].name)}: ${values[i]}"/>`;
        }
      });
      marks += `<text class="tick x" x="${cx}" y="${H - 5}" text-anchor="middle">${g} days <tspan class="sub">${counts[1]} Smurf · ${counts[0]} non-Smurf</tspan></text>`;
    });
    return `<svg viewBox="0 0 ${W} ${H}" role="group" aria-label="Expression in the 32 samples, by age and Smurf status">
      ${grid}<line class="base" x1="${left}" x2="${W - right}" y1="${top + plotH}" y2="${top + plotH}"/>
      <text class="tick" transform="translate(9 ${top + plotH / 2}) rotate(-90)" text-anchor="middle">Expression (VST)</text>
      ${marks}</svg>`;
  }

  function contrastRows(d) {
    const rows = [["Smurf vs non-Smurf", "16 vs 16, all ages", d.sn], ["40 vs 20 days, Smurfs", "6 vs 4", d.s], ["40 vs 20 days, non-Smurfs", "6 vs 4", d.n]];
    return rows.map(([name, n, c]) => {
      const v = verdict(c);
      return `<tr><th scope="row">${name} <span class="n">${n}</span></th>
        <td class="num">${c && c[1] != null ? fmtFC(c[1]) : "–"}</td>
        <td class="num">${c && c[2] != null ? fmtP(c[2]) : "–"}</td>
        <td class="${v.sig ? "hit-" + v.word : "muted"}">${v.arrow ? v.arrow + " " : ""}${v.word}</td></tr>`;
    }).join("");
  }

  // The rest of the paper's per-gene results, one line each, only where this gene has something to show.
  function extraLines(r) {
    const out = [];
    if (r.l) {
      const [method, dereg, result] = r.l;
      out.push(`<b>Longevity candidate</b> (paper's Table 1): selected by ${esc(method)}, ${esc(dereg)}.${result ? ` ${esc(result)}.` : ""}`);
    }
    if (r.lm) {
      const names = { k1: "Smurf status", k2: "age", k3: "Smurf × age" };
      const list = Object.keys(names).filter((k) => r.lm[k]).map((k) => `${names[k]} (${r.lm[k][0]}, p = ${fmtP(r.lm[k][1])})`.replace("-", "−"));
      out.push(`<b>Linear model</b> on VST expression, terms at p &lt; 0.05: ${list.join(", ")}.`);
    }
    if (r.t) {
      const [slope, p, r2, cls] = r.t;
      const where = cls === "none" ? "not a DEG in either analysis" : `DEG in: ${esc(cls)}`;
      out.push(`<b>Progressive change</b> in non-Smurfs over time (Table S9): slope ${slope}, p = ${fmtP(p)}, r² = ${r2}; ${where}.`);
    }
    if (r.p) {
      const label = { y: "young", o: "old" };
      const list = ["y", "o"].filter((k) => r.p[k]).map((k) =>
        `${label[k]} ${fmtFC(r.p[k][0])}, ANOVA p = ${r.p[k][1]}${r.p[k][1] < SIG ? "" : " (n.s.)"}`);
      out.push(`<b>Protein</b>, Smurf vs non-Smurf log2FC (${esc((r.p.y || r.p.o)[2])}): ${list.join("; ")}.`);
    }
    if (r.g) {
      const list = r.g.map(([effect, change, method, ref]) => `${esc(effect)}${/^-?\d/.test(change) ? ` ${esc(change)}%` : ""}, ${esc(method)}, ${esc(ref)}`);
      out.push(`<b>GenAge</b> lifespan effect: ${list.join("; ")}.`);
    }
    if (r.h) out.push(`<b>Human Ageing Atlas</b> ortholog: ${r.h.map(esc).join(", ")}.`);
    return out;
  }

  function buildPanel(fbgn, r, meta, collapsed) {
    const host = document.createElement("div");
    host.id = PANEL_ID;
    const sh = host.attachShadow({ mode: "open" });
    const samples = meta.samples.map(parseSample);
    const paper = `https://doi.org/${meta.doi}`;
    const sn = r.d && r.d.sn, v = verdict(sn), cat = r.d ? category(r.d) : "";
    const headline = !r.e ? "Never detected: 0 reads in all 32 samples."
      : !v.tested ? "Too few reads to test Smurf vs non-Smurf."
      : v.sig ? `<span class="hit-${v.word}">${v.arrow} ${v.word === "up" ? "Up" : "Down"} in Smurfs</span>: log2FC ${esc(fmtFC(sn[1]))} (${esc(linearFold(sn[1]))}), q = ${esc(fmtP(sn[2]))}`
      : `No change in Smurfs: log2FC ${esc(fmtFC(sn[1]))}, q = ${esc(fmtP(sn[2]))}`; // HTML, not text
    const renamed = r.o && r.o.some((x) => x !== fbgn)
      ? `<div class="note">Published as ${r.o.map(esc).join(", ")}, now ${esc(fbgn)} in FlyBase${r.o.length > 1 ? "; the first, best expressed, is shown" : ""}.</div>` : "";
    const lines = extraLines(r);
    const linesHtml = lines.length ? `<div class="lines">${lines.map((l) => `<div>${l}</div>`).join("")}</div>` : "";
    const foot = `<div class="foot">Whole-body RNA-seq, mated Drs-GFP females. Source: <a href="${paper}" target="_blank" rel="noopener">${esc(meta.source)}</a>.</div>`;

    sh.innerHTML = `
      <style>
        :host{all:initial;display:block;font:13px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif;color:#0b0b0b}
        .box{--smurf:#2a78d6;--non:#eb6834;--up:#1b7837;--down:#762a83;--surface:#fcfcfb;position:relative;border:1px solid rgba(11,11,11,.14);border-left:4px solid var(--smurf);border-radius:6px;background:var(--surface);margin:8px 0;padding:7px 12px 8px}
        h3{margin:0;padding-right:58px;font-size:14px;display:flex;align-items:baseline;gap:4px 10px;flex-wrap:wrap}
        h3 .id{font-weight:400;font-size:12px;color:#52514e}
        h3 a{font-size:12px;font-weight:400;color:#1c5cab}
        .fold{position:absolute;top:7px;right:12px;font:12px system-ui,sans-serif;background:none;border:1px solid #c3c2b7;border-radius:4px;padding:1px 8px;cursor:pointer;color:#52514e}
        .head{font-size:13.5px;font-weight:600}
        .chip{display:inline-block;font-size:11px;font-weight:500;color:#52514e;border:1px solid #c3c2b7;border-radius:10px;padding:0 8px;margin-left:8px;vertical-align:1px}
        .body{display:flex;flex-wrap:wrap;gap:6px 20px;margin-top:4px}
        .chart{flex:1 1 380px;max-width:520px;min-width:0;position:relative}
        .side{flex:1 1 340px;min-width:0}
        .legend{display:flex;gap:12px;font-size:11.5px;color:#52514e;align-items:center;margin-bottom:1px}
        .legend svg{display:inline-block;width:12px;height:12px;vertical-align:-1px;margin-right:4px}
        .legend .bar{display:inline-block;width:16px;height:2px;background:#0b0b0b;vertical-align:3px;margin-right:4px}
        .chart>svg{display:block;width:100%;height:auto}
        .grid{stroke:#e1e0d9;stroke-width:1}.base{stroke:#c3c2b7;stroke-width:1}
        .tick{font:11px system-ui,sans-serif;fill:#6b6a65;font-variant-numeric:tabular-nums}
        .tick.x{fill:#0b0b0b;font-size:12px}.tick.x .sub{fill:#6b6a65;font-size:10.5px}
        .mean{stroke:#0b0b0b;stroke-width:2;stroke-linecap:round}
        .dot{stroke:var(--surface);stroke-width:1}
        .dot.s{fill:var(--smurf)}.dot.n{fill:var(--surface);stroke:var(--non);stroke-width:2}
        .hit{fill:transparent;cursor:default;outline:none}
        .hit:hover,.hit:focus{fill:rgba(11,11,11,.08)}
        .tip{position:absolute;display:none;transform:translate(-50%,-100%);background:#0b0b0b;color:#fff;padding:3px 7px;border-radius:4px;font-size:11px;white-space:nowrap;pointer-events:none;z-index:5}
        table{border-collapse:collapse;width:100%;font-size:12px}
        th,td{text-align:left;padding:2px 8px 2px 0;border-bottom:1px solid #e1e0d9;font-weight:400;vertical-align:baseline}
        thead th{color:#52514e;font-size:11.5px;border-bottom:1px solid #c3c2b7}
        .num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
        .n{color:#6b6a65;font-size:11px;white-space:nowrap}
        .hit-up,.hit-down{font-weight:600;white-space:nowrap}.hit-up{color:var(--up)}.hit-down{color:var(--down)}.muted{color:#6b6a65;white-space:nowrap}
        .lines{margin:5px 0 0;font-size:11.5px;line-height:1.4;color:#2d2c2a}.lines div{margin-top:2px}
        .note,.foot{color:#52514e;font-size:11px;margin-top:4px}
        .foot a,.toggle{color:#1c5cab}
        .toggle{background:none;border:0;padding:0;font:inherit;font-size:11px;cursor:pointer;text-decoration:underline}
        .samples{display:none;margin-top:6px;max-height:220px;overflow:auto}
        .collapsed .main{display:none}
      </style>
      <div class="box ${collapsed ? "collapsed" : ""}">
        <h3>Smurf transcriptome · ${esc(r.s)} <span class="id">${esc(fbgn)}</span>
          <span class="head">${headline}${cat ? `<span class="chip">${cat}</span>` : ""}</span>
          <a href="${paper}" target="_blank" rel="noopener">Zane et al. 2023 ↗</a>
          <button class="fold">${collapsed ? "Show" : "Hide"}</button></h3>
        <div class="main">
          ${renamed}
          ${r.e ? `<div class="body">
            <div class="chart">
              <div class="legend">
                <span><svg viewBox="0 0 12 12"><circle cx="6" cy="6" r="4.5" fill="#2a78d6"/></svg>Smurf</span>
                <span><svg viewBox="0 0 12 12"><circle cx="6" cy="6" r="4" fill="none" stroke="#eb6834" stroke-width="2"/></svg>non-Smurf</span>
                <span><span class="bar"></span>group mean</span>
              </div>
              ${stripPlot(r.e, samples)}<div class="tip"></div>
            </div>
            <div class="side">
              <table><thead><tr><th scope="col">Contrast</th><th scope="col" class="num">log2FC</th><th scope="col" class="num">q</th><th scope="col"></th></tr></thead>
              <tbody>${contrastRows(r.d)}</tbody></table>
              <div class="note">DESeq2, significant at q ≤ 0.05; "not tested" = too few reads for an adjusted p. <button class="toggle">Show the 32 sample values</button></div>
              ${linesHtml}${foot}
            </div>
          </div>
          <div class="samples"></div>` : `${linesHtml}${foot}`}
        </div>
      </div>`;

    if (r.e) {
      const tip = sh.querySelector(".tip"), chart = sh.querySelector(".chart");
      const show = (el) => {
        const s = samples[+el.dataset.i], box = el.getBoundingClientRect(), c = chart.getBoundingClientRect();
        tip.textContent = `${s.name}: ${r.e[+el.dataset.i]} · ${s.smurf ? "Smurf" : "non-Smurf"}, ${s.age} days, ${s.time}`;
        tip.style.display = "block";
        tip.style.top = (box.top - c.top - 2) + "px";
        const half = tip.offsetWidth / 2;
        tip.style.left = Math.max(half, Math.min(c.width - half, box.left - c.left + box.width / 2)) + "px";
      };
      const hide = () => (tip.style.display = "none");
      for (const el of sh.querySelectorAll(".hit[data-i]")) {
        el.addEventListener("mouseenter", () => show(el)); el.addEventListener("focus", () => show(el));
        el.addEventListener("mouseleave", hide); el.addEventListener("blur", hide);
      }
      const list = sh.querySelector(".samples"), toggle = sh.querySelector(".toggle");
      toggle.addEventListener("click", () => {
        const open = list.style.display !== "block";
        if (open && !list.firstChild) {
          const order = samples.map((s, i) => i).sort((a, b) => samples[a].group - samples[b].group || samples[a].smurf - samples[b].smurf);
          list.innerHTML = `<table><thead><tr><th scope="col">Sample</th><th scope="col">Status</th><th scope="col">Age</th><th scope="col">Collected</th><th scope="col" class="num">VST</th></tr></thead><tbody>${
            order.map((i) => { const s = samples[i]; return `<tr><td>${esc(s.name)}</td><td>${s.smurf ? "Smurf" : "non-Smurf"}</td><td>${s.age} d</td><td>${s.time}</td><td class="num">${r.e[i].toFixed(2)}</td></tr>`; }).join("")
          }</tbody></table>`;
        }
        list.style.display = open ? "block" : "none";
        toggle.textContent = open ? "Hide the sample values" : "Show the 32 sample values";
      });
    }
    const box = sh.querySelector(".box"), fold = sh.querySelector(".fold");
    fold.addEventListener("click", () => {
      const now = box.classList.toggle("collapsed");
      fold.textContent = now ? "Show" : "Hide";
      chrome.storage.local.set({ collapsed: now });
    });
    return host;
  }

  // Goes at the top of the report, under ProteoCast's panel when that extension is installed. FlyBase's sidebar
  // setup calls highlightCurrentSection() once, then attaches its scroll and resize listeners; that call throws
  // (and the listeners are never attached) if no section header sits in the top half of the window. So the panel
  // waits until the setup has run: windowChange(), called right after it, gives the sidebar panel an inline
  // max-height. If that never shows, the panel falls back to just before the second section, which is safe.
  const sidebarReady = () => !document.getElementById("report-navsection")
    || !!document.querySelector("div.sidenav div.panel.panel-default")?.style.maxHeight;

  // With the panels above it, the first section header can sit below FlyBase's halfway mark when the page is
  // scrolled to the top. FlyBase's scroll handler then clears the sidebar highlight and throws before setting a
  // new one (it clears and sets in one go otherwise). That only happens above the first section, so whenever the
  // highlight is left empty, give it back to the first item.
  let highlightFix = false;
  function keepSidebarHighlight() {
    const nav = document.querySelector("#report-navsection > ul");
    if (highlightFix || !nav) return;
    highlightFix = true;
    new MutationObserver(() => {
      if (!nav.querySelector(":scope > li.active")) nav.querySelector(":scope > li")?.classList.add("active");
    }).observe(nav, { subtree: true, attributes: true, attributeFilter: ["class"] });
  }

  async function mount(node) {
    const id = currentId;
    for (let t = 0; t < 75 && !sidebarReady(); t++) await new Promise((r) => setTimeout(r, 200));
    if (id !== currentId) return; // navigated away while waiting
    document.getElementById(PANEL_ID)?.remove();
    const report = document.querySelector(".report");
    if (!report) return document.body.prepend(node);
    if (sidebarReady()) {
      const pc = document.getElementById("proteocast-panel-host");
      if (pc && pc.parentElement === report) pc.after(node); else report.prepend(node);
      keepSidebarHighlight();
      return;
    }
    const ids = [...document.querySelectorAll("#report-navsection > ul > li > a")].map((a) => a.hash.slice(1));
    let next = ids.slice(1).map((id) => document.getElementById(id)).find((e) => e && report.contains(e));
    if (next) {
      while (next.parentElement !== report) next = next.parentElement;
      report.insertBefore(node, next);
    } else report.prepend(node);
  }

  async function send(msg) {
    try {
      return (await chrome.runtime.sendMessage(msg)) || { error: "no response" };
    } catch (e) {
      return { error: "reloaded" }; // "Extension context invalidated" after the extension was reloaded or updated
    }
  }

  function notice(text) {
    const host = document.createElement("div");
    host.id = PANEL_ID;
    host.textContent = text;
    host.style.cssText = "font:12px system-ui;color:#555;padding:6px 14px";
    mount(host);
  }

  async function run() {
    const id = idFromUrl();
    if (id === currentId) return;
    currentId = id;
    document.getElementById(PANEL_ID)?.remove();
    if (!id) return;
    const lookup = id.startsWith("FBal") ? alleleGene() : id;
    if (!lookup) return; // allele of a transgene, a construct, etc.: no gene to show
    const [data, stored] = await Promise.all([send({ type: "getGene", id: lookup }), chrome.storage.local.get({ collapsed: false }).catch(() => ({}))]);
    if (id !== currentId) return; // navigated away meanwhile
    if (data.error) {
      if (data.error === "reloaded") notice("Smurf transcriptome: the extension was updated. Refresh this page.");
      else notice(`Smurf transcriptome: could not read the bundled data (${data.error}).`);
      return;
    }
    if (!data.fbgn) return; // a product of a gene outside the dataset
    if (!data.record) return notice(`Smurf transcriptome: ${data.fbgn} is not in the Zane et al. 2023 annotation (BDGP6.95).`);
    mount(buildPanel(data.fbgn, data.record, data.meta, !!stored.collapsed));
  }

  run();
  // FlyBase navigates client-side in places. Content scripts live in an isolated world, so patching
  // history.pushState here would not see the page's own calls: poll the URL instead (run() is a no-op
  // while the ID is unchanged), plus back/forward and hash changes.
  for (const ev of ["popstate", "hashchange"]) addEventListener(ev, run);
  setInterval(run, 2000);
})();
