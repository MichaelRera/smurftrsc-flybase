// Service worker: the dataset ships inside the extension, split into 100 shards by the last two digits of the
// ID, so a lookup reads two small files at most and nothing leaves the browser.

const ID = /^FB(gn|pp|tr)\d{7}$/;
const shardCache = new Map();

async function loadJson(path) {
  if (!shardCache.has(path)) {
    const r = await fetch(chrome.runtime.getURL(path));
    if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
    shardCache.set(path, await r.json());
  }
  return shardCache.get(path);
}

const shardOf = (id) => id.slice(-2);

async function lookup(id) {
  let fbgn = id;
  if (!id.startsWith("FBgn")) {
    fbgn = (await loadJson(`data/products/${shardOf(id)}.json`))[id];
    if (!fbgn) return { fbgn: null, record: null };
  }
  const [genes, meta] = await Promise.all([loadJson(`data/genes/${shardOf(fbgn)}.json`), loadJson("data/meta.json")]);
  return { fbgn, record: genes[fbgn] || null, meta };
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (sender.id !== chrome.runtime.id) return; // only our own content script (there is no externally_connectable)
  if (msg.type !== "getGene" || !ID.test(msg.id)) return sendResponse({ error: "bad request" });
  lookup(msg.id).then(sendResponse).catch((e) => sendResponse({ error: String(e.message || e) }));
  return true; // async
});
