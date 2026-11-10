#!/usr/bin/env python3
"""Captures for the store listing: raw screenshots and the demo screencast, driven over the DevTools protocol.

Usage: store_capture.py OUTDIR MODE      MODE = shots | pcshot | video
  shots   raw_thor.png (Thor gene page), raw_gclc.png (Gclc, sample table open, one dot hovered)
  pcshot  raw_both.png (Thor-PA, needs ProteoCast for FlyBase loaded too)
  video   frames/*.jpg + frames.json (Thor: verdict, dots, contrasts, sample table; Jump to Gene "Gclc"; Gclc)
Then: python3 ../store/make_store_images.py OUTDIR ../store ../icons/icon128.png

Browser (2026-11-02, laptop): branded Google Chrome ignores --load-extension, so use Chrome for Testing,
headless, with a normal user agent (FlyBase's CDN answers the headless one with a 403 page):
  npx -y @puppeteer/browsers install chrome@stable --path DIR
  DIR/chrome/linux-*/chrome-linux64/chrome --headless=new --hide-scrollbars --user-data-dir=PROFILE \
    --remote-debugging-port=9333 --user-agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36" \
    --disable-extensions-except=EXT[,PROTEOCAST] --load-extension=EXT[,PROTEOCAST] about:blank
  VIEWPORT=1240x812 python3 store_capture.py OUTDIR shots      (needs: pip install websockets)
Video: turn frames.json into an ffmpeg concat list (each frame lasts until the next; segments end at the None
markers), then  ffmpeg -f concat -safe 0 -i list.txt -vf "setpts=PTS/1.5,fps=25,format=yuv420p" -c:v libx264
-crf 20 -movflags +faststart demo.mp4   (1.5x: the script's pauses are tuned for that speed).
"""
import asyncio, base64, json, os, sys, time, urllib.request
import websockets

PORT = 9333
OUT = sys.argv[1]
MODE = sys.argv[2]
os.makedirs(OUT, exist_ok=True)

CURSOR_JS = r"""
(() => {
  if (document.getElementById('cc-cursor')) return;
  const c = document.createElement('div'); c.id = 'cc-cursor';
  c.innerHTML = '<svg width="22" height="30" viewBox="0 0 22 30"><path d="M2 2 L2 24 L8 18.5 L12 28 L16 26.3 L12 17 L20 17 Z" fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
  c.style.cssText = 'position:fixed;left:-50px;top:-50px;z-index:2147483647;pointer-events:none;transform:translate(-2px,-2px)';
  document.documentElement.appendChild(c);
  const r = document.createElement('div'); r.id = 'cc-ripple';
  r.style.cssText = 'position:fixed;z-index:2147483646;pointer-events:none;width:34px;height:34px;margin:-17px 0 0 -17px;border-radius:50%;border:3px solid rgba(42,120,214,.85);opacity:0;transition:opacity .45s, transform .45s;transform:scale(.4)';
  document.documentElement.appendChild(r);
  window.__ccMove = (x, y) => { c.style.left = x + 'px'; c.style.top = y + 'px'; };
  window.__ccClick = (x, y) => { r.style.transition = 'none'; r.style.left = x + 'px'; r.style.top = y + 'px'; r.style.opacity = 1; r.style.transform = 'scale(.4)';
    requestAnimationFrame(() => { r.style.transition = 'opacity .5s, transform .5s'; r.style.opacity = 0; r.style.transform = 'scale(1.3)'; }); };
})()
"""


class CDP:
    def __init__(self, ws):
        self.ws, self.n, self.pending, self.recording, self.frames = ws, 0, {}, False, []

    async def reader(self):
        async for raw in self.ws:
            m = json.loads(raw)
            if "id" in m and m["id"] in self.pending:
                self.pending.pop(m["id"]).set_result(m.get("result", m.get("error")))
            elif m.get("method") == "Page.screencastFrame":
                p = m["params"]
                asyncio.ensure_future(self.send("Page.screencastFrameAck", sessionId=p["sessionId"]))
                if self.recording:
                    i = len(self.frames)
                    fn = f"{OUT}/frames/f{i:05d}.jpg"
                    open(fn, "wb").write(base64.b64decode(p["data"]))
                    self.frames.append((time.monotonic(), fn))

    async def send(self, method, **params):
        self.n += 1
        fut = asyncio.get_event_loop().create_future()
        self.pending[self.n] = fut
        await self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        return await fut

    async def js(self, expr):
        r = await self.send("Runtime.evaluate", expression=expr, returnByValue=True, awaitPromise=True)
        return r.get("result", {}).get("value")


async def main():
    tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json"))
    page = next(t for t in tabs if t["type"] == "page")
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=2**27) as ws:
        cdp = CDP(ws)
        asyncio.ensure_future(cdp.reader())
        await cdp.send("Page.enable"); await cdp.send("Runtime.enable")
        if os.environ.get("VIEWPORT"):
            w, h = map(int, os.environ["VIEWPORT"].split("x"))
            await cdp.send("Emulation.setDeviceMetricsOverride", width=w, height=h, deviceScaleFactor=1, mobile=False)
        mouse = [600, 400]

        async def nav(url, settle=3):
            await cdp.send("Page.navigate", url=url)
            for _ in range(120):
                await asyncio.sleep(0.5)
                ok = await cdp.js("location.href === " + json.dumps(url) + " && !!document.querySelector('.report > #smurftrsc-panel-host')?.shadowRoot && document.readyState === 'complete'")
                if ok: break
            await asyncio.sleep(settle)
            print("loaded", url, await cdp.js("document.title"), flush=True)

        async def cursor():
            await cdp.js(CURSOR_JS)
            await cdp.js(f"window.__ccMove({mouse[0]},{mouse[1]})")

        async def where(sel, nth=0, root="shadow"):
            q = (f"document.getElementById('smurftrsc-panel-host').shadowRoot.querySelectorAll({json.dumps(sel)})[{nth}]"
                 if root == "shadow" else f"document.querySelectorAll({json.dumps(sel)})[{nth}]")
            return await cdp.js(f"(() => {{ const e = {q}; if (!e) return null; const b = e.getBoundingClientRect(); return [b.left + b.width/2, b.top + b.height/2]; }})()")

        async def move(x, y, dur=0.8):
            steps = max(2, int(dur * 30))
            x0, y0 = mouse
            for k in range(1, steps + 1):
                t = k / steps; t = t * t * (3 - 2 * t)
                mouse[:] = [x0 + (x - x0) * t, y0 + (y - y0) * t]
                await cdp.send("Input.dispatchMouseEvent", type="mouseMoved", x=mouse[0], y=mouse[1])
                await cdp.js(f"window.__ccMove && window.__ccMove({mouse[0]},{mouse[1]})")
                await asyncio.sleep(dur / steps)

        async def click():
            x, y = mouse
            await cdp.js(f"window.__ccClick && window.__ccClick({x},{y})")
            await cdp.send("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
            await cdp.send("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1)

        async def shot(name):
            r = await cdp.send("Page.captureScreenshot", format="png")
            open(f"{OUT}/{name}.png", "wb").write(base64.b64decode(r["data"]))
            print("shot", name, flush=True)

        async def rec(on):
            if on:
                os.makedirs(f"{OUT}/frames", exist_ok=True)
                cdp.recording = True
                await cdp.send("Page.startScreencast", format="jpeg", quality=92, everyNthFrame=1)
            else:
                await asyncio.sleep(0.3)
                await cdp.send("Page.stopScreencast")
                cdp.recording = False
                cdp.frames.append((time.monotonic(), None))  # segment end marker

        async def hover_dot(i, pause=1.3):
            p = await where(f".hit[data-i='{i}']")
            if p: await move(*p, dur=0.6); await asyncio.sleep(pause)

        if MODE == "shots":
            await nav("https://flybase.org/reports/FBgn0261560")
            await shot("raw_thor")
            await nav("https://flybase.org/reports/FBgn0040319")
            await cursor()
            p = await where(".toggle"); await move(*p, dur=0.1); await click(); await asyncio.sleep(1)
            await hover_dot(await cdp.js("(() => { const s = document.getElementById('smurftrsc-panel-host').shadowRoot; const h = [...s.querySelectorAll('.hit[data-i]')]; return h[h.length-3].dataset.i; })()"), pause=1)
            await cdp.js("document.getElementById('cc-cursor').style.display='none'")
            await shot("raw_gclc")
            print(json.dumps(await cdp.js("(() => { const b = document.getElementById('smurftrsc-panel-host').getBoundingClientRect(); return [b.top, b.bottom]; })()")))

        if MODE == "pcshot":
            await nav("https://flybase.org/reports/FBpp0077213", settle=8)
            await shot("raw_both")

        if MODE == "video":
            await nav("https://flybase.org/reports/FBgn0261560")
            await cursor()
            mouse[:] = [700, 300]; await cdp.js("window.__ccMove(700,300)")
            await rec(True)
            await asyncio.sleep(1.8)
            # headline, then a few dots: non-Smurf low, Smurf high, at each age
            p = await where(".head"); await move(p[0] - 60, p[1], dur=0.9); await asyncio.sleep(1.2)
            idx = await cdp.js("""(() => { const s = document.getElementById('smurftrsc-panel-host').shadowRoot;
                 return [...s.querySelectorAll('.hit[data-i]')].map(e => +e.dataset.i); })()""")
            for i in [idx[1], idx[6], idx[12], idx[18], idx[25], idx[30]]:
                await hover_dot(i, pause=0.9)
            # the contrast table: age effects within each status
            p = await where("tbody tr", 1); await move(p[0] + 60, p[1], dur=0.7); await asyncio.sleep(1.0)
            p = await where("tbody tr", 2); await move(p[0] + 60, p[1], dur=0.4); await asyncio.sleep(1.0)
            # sample table
            p = await where(".toggle"); await move(*p, dur=0.6); await asyncio.sleep(0.3); await click(); await asyncio.sleep(1.6)
            await cdp.js("document.getElementById('smurftrsc-panel-host').shadowRoot.querySelector('.samples').scrollBy({top: 120, behavior: 'smooth'})")
            await asyncio.sleep(1.4)
            p = await where(".toggle"); await move(*p, dur=0.4); await click(); await asyncio.sleep(0.8)
            # jump to another gene through FlyBase's own box
            p = await where("#J2G_input, input[placeholder='Jump to Gene']", root="page")
            if p is None:
                p = await where("input[type=text]", root="page")
            await move(*p, dur=0.8); await click(); await asyncio.sleep(0.4)
            for ch in "Gclc":
                await cdp.send("Input.insertText", text=ch); await asyncio.sleep(0.18)
            await asyncio.sleep(0.5)
            await rec(False)
            await cdp.send("Input.dispatchKeyEvent", type="keyDown", key="Enter", code="Enter", windowsVirtualKeyCode=13, text="\r")
            await cdp.send("Input.dispatchKeyEvent", type="keyUp", key="Enter", code="Enter", windowsVirtualKeyCode=13)
            for _ in range(60):
                await asyncio.sleep(0.5)
                if "Gclc" in (await cdp.js("document.title") or "") and await cdp.js("document.readyState === 'complete' && !!document.querySelector('.report > #smurftrsc-panel-host')?.shadowRoot"): break
            await asyncio.sleep(4)
            print("loaded", await cdp.js("document.title"), flush=True)
            await cursor()
            await rec(True)
            await asyncio.sleep(1.5)
            p = await where(".head"); await move(p[0] - 60, p[1], dur=0.8); await asyncio.sleep(1.4)
            p = await where("tbody tr", 2); await move(p[0] + 60, p[1], dur=0.7); await asyncio.sleep(1.4)
            p = await where(".lines");
            if p: await move(p[0], p[1], dur=0.7); await asyncio.sleep(2.2)
            await rec(False)
            json.dump([(t, f) for t, f in cdp.frames], open(f"{OUT}/frames.json", "w"))
            print("frames", len(cdp.frames), flush=True)

asyncio.run(main())
