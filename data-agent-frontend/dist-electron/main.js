import { app, BrowserWindow, ipcMain } from "electron";
import http from "node:http";
import https from "node:https";
import { fileURLToPath } from "node:url";
import path from "node:path";
const __dirname$1 = path.dirname(fileURLToPath(import.meta.url));
process.env.APP_ROOT = path.join(__dirname$1, "..");
const VITE_DEV_SERVER_URL = process.env["VITE_DEV_SERVER_URL"];
const MAIN_DIST = path.join(process.env.APP_ROOT, "dist-electron");
const RENDERER_DIST = path.join(process.env.APP_ROOT, "dist");
process.env.VITE_PUBLIC = VITE_DEV_SERVER_URL ? path.join(process.env.APP_ROOT, "public") : RENDERER_DIST;
let win;
const activeStreams = /* @__PURE__ */ new Map();
function parseSseChunk(buffer) {
  const events = [];
  const normalized = buffer.replace(/\r\n/g, "\n");
  const parts = normalized.split("\n\n");
  const rest = parts.pop() ?? "";
  for (const part of parts) {
    if (!part.trim()) {
      continue;
    }
    let event = "message";
    let id = "";
    const dataLines = [];
    for (const rawLine of part.split("\n")) {
      if (!rawLine || rawLine.startsWith(":")) {
        continue;
      }
      const separator = rawLine.indexOf(":");
      const field = separator >= 0 ? rawLine.slice(0, separator) : rawLine;
      const value = separator >= 0 ? rawLine.slice(separator + 1).replace(/^ /, "") : "";
      if (field === "event") {
        event = value || "message";
      } else if (field === "data") {
        dataLines.push(value);
      } else if (field === "id") {
        id = value;
      }
    }
    events.push({ event, data: dataLines.join("\n"), id: id || void 0 });
  }
  return { events, rest };
}
function emitStreamEvent(webContents, payload) {
  if (!webContents.isDestroyed()) {
    webContents.send("stream:event", payload);
  }
}
function stopStream(requestId) {
  const request = activeStreams.get(requestId);
  if (!request) {
    return;
  }
  activeStreams.delete(requestId);
  request.destroy();
}
function handleStreamResponse(webContents, requestId, response) {
  emitStreamEvent(webContents, {
    requestId,
    type: "open",
    status: response.statusCode ?? 0
  });
  response.setEncoding("utf8");
  let buffer = "";
  response.on("data", (chunk) => {
    buffer += chunk;
    const parsed = parseSseChunk(buffer);
    buffer = parsed.rest;
    for (const event of parsed.events) {
      emitStreamEvent(webContents, {
        requestId,
        type: "message",
        event: event.event,
        data: event.data,
        id: event.id
      });
    }
  });
  response.on("end", () => {
    if (buffer.trim()) {
      const parsed = parseSseChunk(`${buffer}

`);
      for (const event of parsed.events) {
        emitStreamEvent(webContents, {
          requestId,
          type: "message",
          event: event.event,
          data: event.data,
          id: event.id
        });
      }
    }
    activeStreams.delete(requestId);
    emitStreamEvent(webContents, { requestId, type: "close" });
  });
  response.on("error", (error) => {
    activeStreams.delete(requestId);
    emitStreamEvent(webContents, {
      requestId,
      type: "error",
      error: error instanceof Error ? error.message : String(error)
    });
  });
}
function startStream(webContents, requestId, rawUrl) {
  stopStream(requestId);
  const url = new URL(rawUrl);
  const transport = url.protocol === "https:" ? https : http;
  const request = transport.request(
    url,
    {
      method: "GET",
      headers: {
        Accept: "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive"
      }
    },
    (response) => handleStreamResponse(webContents, requestId, response)
  );
  activeStreams.set(requestId, request);
  request.on("error", (error) => {
    activeStreams.delete(requestId);
    emitStreamEvent(webContents, {
      requestId,
      type: "error",
      error: error instanceof Error ? error.message : String(error)
    });
  });
  request.end();
}
function createWindow() {
  win = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 760,
    minHeight: 580,
    frame: false,
    transparent: false,
    backgroundColor: "#f2efe8",
    icon: path.join(process.env.VITE_PUBLIC, "app-icon.png"),
    webPreferences: {
      preload: path.join(__dirname$1, "preload.mjs")
    }
  });
  win.webContents.on("did-finish-load", () => {
    win?.webContents.send("main-process-message", (/* @__PURE__ */ new Date()).toLocaleString());
  });
  if (VITE_DEV_SERVER_URL) {
    win.loadURL(VITE_DEV_SERVER_URL);
  } else {
    win.loadFile(path.join(RENDERER_DIST, "index.html"));
  }
}
app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
    win = null;
  }
});
app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
ipcMain.on("stream:start", (event, payload) => {
  if (!payload?.requestId || !payload?.url) {
    return;
  }
  startStream(event.sender, payload.requestId, payload.url);
});
ipcMain.on("stream:stop", (_event, requestId) => {
  if (!requestId) {
    return;
  }
  stopStream(requestId);
});
ipcMain.on("window:minimize", () => win?.minimize());
ipcMain.on("window:maximize", () => {
  if (!win) return;
  if (win.isMaximized()) win.unmaximize();
  else win.maximize();
});
ipcMain.on("window:close", () => win?.close());
app.whenReady().then(createWindow);
export {
  MAIN_DIST,
  RENDERER_DIST,
  VITE_DEV_SERVER_URL
};
