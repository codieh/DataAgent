import { app as v, BrowserWindow as _, ipcMain as d } from "electron";
import j from "node:http";
import O from "node:https";
import { fileURLToPath as x } from "node:url";
import c from "node:path";
const S = c.dirname(x(import.meta.url));
process.env.APP_ROOT = c.join(S, "..");
const g = process.env.VITE_DEV_SERVER_URL, C = c.join(process.env.APP_ROOT, "dist-electron"), P = c.join(process.env.APP_ROOT, "dist");
process.env.VITE_PUBLIC = g ? c.join(process.env.APP_ROOT, "public") : P;
let i;
const l = /* @__PURE__ */ new Map();
function R(t) {
  const e = [], s = t.replace(/\r\n/g, `
`).split(`

`), r = s.pop() ?? "";
  for (const n of s) {
    if (!n.trim())
      continue;
    let o = "message", w = "";
    const E = [];
    for (const m of n.split(`
`)) {
      if (!m || m.startsWith(":"))
        continue;
      const f = m.indexOf(":"), h = f >= 0 ? m.slice(0, f) : m, u = f >= 0 ? m.slice(f + 1).replace(/^ /, "") : "";
      h === "event" ? o = u || "message" : h === "data" ? E.push(u) : h === "id" && (w = u);
    }
    e.push({ event: o, data: E.join(`
`), id: w || void 0 });
  }
  return { events: e, rest: r };
}
function p(t, e) {
  t.isDestroyed() || t.send("stream:event", e);
}
function T(t) {
  const e = l.get(t);
  e && (l.delete(t), e.destroy());
}
function z(t, e, a) {
  p(t, {
    requestId: e,
    type: "open",
    status: a.statusCode ?? 0
  }), a.setEncoding("utf8");
  let s = "";
  a.on("data", (r) => {
    s += r;
    const n = R(s);
    s = n.rest;
    for (const o of n.events)
      p(t, {
        requestId: e,
        type: "message",
        event: o.event,
        data: o.data,
        id: o.id
      });
  }), a.on("end", () => {
    if (s.trim()) {
      const r = R(`${s}

`);
      for (const n of r.events)
        p(t, {
          requestId: e,
          type: "message",
          event: n.event,
          data: n.data,
          id: n.id
        });
    }
    l.delete(e), p(t, { requestId: e, type: "close" });
  }), a.on("error", (r) => {
    l.delete(e), p(t, {
      requestId: e,
      type: "error",
      error: r instanceof Error ? r.message : String(r)
    });
  });
}
function V(t, e, a) {
  T(e);
  const s = new URL(a), n = (s.protocol === "https:" ? O : j).request(
    s,
    {
      method: "GET",
      headers: {
        Accept: "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive"
      }
    },
    (o) => z(t, e, o)
  );
  l.set(e, n), n.on("error", (o) => {
    l.delete(e), p(t, {
      requestId: e,
      type: "error",
      error: o instanceof Error ? o.message : String(o)
    });
  }), n.end();
}
function L() {
  i = new _({
    width: 1440,
    height: 960,
    minWidth: 760,
    minHeight: 580,
    frame: !1,
    transparent: !1,
    backgroundColor: "#f2efe8",
    icon: c.join(process.env.VITE_PUBLIC, "app-icon.png"),
    webPreferences: {
      preload: c.join(S, "preload.mjs")
    }
  }), i.webContents.on("did-finish-load", () => {
    i?.webContents.send("main-process-message", (/* @__PURE__ */ new Date()).toLocaleString());
  }), g ? i.loadURL(g) : i.loadFile(c.join(P, "index.html"));
}
v.on("window-all-closed", () => {
  process.platform !== "darwin" && (v.quit(), i = null);
});
v.on("activate", () => {
  _.getAllWindows().length === 0 && L();
});
d.on("stream:start", (t, e) => {
  !e?.requestId || !e?.url || V(t.sender, e.requestId, e.url);
});
d.on("stream:stop", (t, e) => {
  e && T(e);
});
d.on("window:minimize", () => i?.minimize());
d.on("window:maximize", () => {
  i && (i.isMaximized() ? i.unmaximize() : i.maximize());
});
d.on("window:close", () => i?.close());
v.whenReady().then(L);
export {
  C as MAIN_DIST,
  P as RENDERER_DIST,
  g as VITE_DEV_SERVER_URL
};
