import { app, BrowserWindow, ipcMain, WebContents } from 'electron'
import http, { type ClientRequest, type IncomingMessage } from 'node:http'
import https from 'node:https'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// The built directory structure
//
// ├─┬─┬ dist
// │ │ └── index.html
// │ │
// │ ├─┬ dist-electron
// │ │ ├── main.js
// │ │ └── preload.mjs
// │
process.env.APP_ROOT = path.join(__dirname, '..')

// 🚧 Use ['ENV_NAME'] avoid vite:define plugin - Vite@2.x
export const VITE_DEV_SERVER_URL = process.env['VITE_DEV_SERVER_URL']
export const MAIN_DIST = path.join(process.env.APP_ROOT, 'dist-electron')
export const RENDERER_DIST = path.join(process.env.APP_ROOT, 'dist')

process.env.VITE_PUBLIC = VITE_DEV_SERVER_URL ? path.join(process.env.APP_ROOT, 'public') : RENDERER_DIST

let win: BrowserWindow | null
const activeStreams = new Map<string, ClientRequest>()

type ParsedSseEvent = {
  event: string
  data: string
  id?: string
}

function parseSseChunk(buffer: string) {
  const events: ParsedSseEvent[] = []
  const normalized = buffer.replace(/\r\n/g, '\n')
  const parts = normalized.split('\n\n')
  const rest = parts.pop() ?? ''

  for (const part of parts) {
    if (!part.trim()) {
      continue
    }

    let event = 'message'
    let id = ''
    const dataLines: string[] = []

    for (const rawLine of part.split('\n')) {
      if (!rawLine || rawLine.startsWith(':')) {
        continue
      }

      const separator = rawLine.indexOf(':')
      const field = separator >= 0 ? rawLine.slice(0, separator) : rawLine
      const value = separator >= 0 ? rawLine.slice(separator + 1).replace(/^ /, '') : ''

      if (field === 'event') {
        event = value || 'message'
      } else if (field === 'data') {
        dataLines.push(value)
      } else if (field === 'id') {
        id = value
      }
    }

    events.push({ event, data: dataLines.join('\n'), id: id || undefined })
  }

  return { events, rest }
}

function emitStreamEvent(
  webContents: WebContents,
  payload: Record<string, unknown>,
) {
  if (!webContents.isDestroyed()) {
    webContents.send('stream:event', payload)
  }
}

function stopStream(requestId: string) {
  const request = activeStreams.get(requestId)
  if (!request) {
    return
  }
  activeStreams.delete(requestId)
  request.destroy()
}

function handleStreamResponse(webContents: WebContents, requestId: string, response: IncomingMessage) {
  emitStreamEvent(webContents, {
    requestId,
    type: 'open',
    status: response.statusCode ?? 0,
  })

  response.setEncoding('utf8')
  let buffer = ''

  response.on('data', (chunk: string) => {
    buffer += chunk
    const parsed = parseSseChunk(buffer)
    buffer = parsed.rest

    for (const event of parsed.events) {
      emitStreamEvent(webContents, {
        requestId,
        type: 'message',
        event: event.event,
        data: event.data,
        id: event.id,
      })
    }
  })

  response.on('end', () => {
    if (buffer.trim()) {
      const parsed = parseSseChunk(`${buffer}\n\n`)
      for (const event of parsed.events) {
        emitStreamEvent(webContents, {
          requestId,
          type: 'message',
          event: event.event,
          data: event.data,
          id: event.id,
        })
      }
    }
    activeStreams.delete(requestId)
    emitStreamEvent(webContents, { requestId, type: 'close' })
  })

  response.on('error', (error) => {
    activeStreams.delete(requestId)
    emitStreamEvent(webContents, {
      requestId,
      type: 'error',
      error: error instanceof Error ? error.message : String(error),
    })
  })
}

function startStream(webContents: WebContents, requestId: string, rawUrl: string) {
  stopStream(requestId)

  const url = new URL(rawUrl)
  const transport = url.protocol === 'https:' ? https : http
  const request = transport.request(
    url,
    {
      method: 'GET',
      headers: {
        Accept: 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      },
    },
    (response) => handleStreamResponse(webContents, requestId, response),
  )

  activeStreams.set(requestId, request)

  request.on('error', (error) => {
    activeStreams.delete(requestId)
    emitStreamEvent(webContents, {
      requestId,
      type: 'error',
      error: error instanceof Error ? error.message : String(error),
    })
  })

  request.end()
}

function createWindow() {
  win = new BrowserWindow({
    width: 1440,
    height: 960,
    minWidth: 760,
    minHeight: 580,
    frame: false,
    transparent: false,
    backgroundColor: '#f2efe8',
    icon: path.join(process.env.VITE_PUBLIC, 'app-icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.mjs'),
    },
  })

  // Test active push message to Renderer-process.
  win.webContents.on('did-finish-load', () => {
    win?.webContents.send('main-process-message', (new Date).toLocaleString())
  })

  if (VITE_DEV_SERVER_URL) {
    win.loadURL(VITE_DEV_SERVER_URL)
  } else {
    // win.loadFile('dist/index.html')
    win.loadFile(path.join(RENDERER_DIST, 'index.html'))
  }
}

// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
    win = null
  }
})

app.on('activate', () => {
  // On OS X it's common to re-create a window in the app when the
  // dock icon is clicked and there are no other windows open.
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow()
  }
})

ipcMain.on('stream:start', (event, payload: { requestId: string; url: string }) => {
  if (!payload?.requestId || !payload?.url) {
    return
  }
  startStream(event.sender, payload.requestId, payload.url)
})

ipcMain.on('stream:stop', (_event, requestId: string) => {
  if (!requestId) {
    return
  }
  stopStream(requestId)
})

ipcMain.on('window:minimize', () => win?.minimize())
ipcMain.on('window:maximize', () => {
  if (!win) return
  if (win.isMaximized()) win.unmaximize()
  else win.maximize()
})
ipcMain.on('window:close', () => win?.close())

app.whenReady().then(createWindow)
