/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BACKEND_URL?: string
  readonly VITE_TENANT_ID?: string
  readonly VITE_USER_ID?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

interface Window {
  ipcRenderer?: {
    send: (channel: string, ...args: unknown[]) => void
    on: (channel: string, listener: (...args: unknown[]) => void) => void
    off: (channel: string, listener: (...args: unknown[]) => void) => void
    invoke: (channel: string, ...args: unknown[]) => Promise<unknown>
  }
}
