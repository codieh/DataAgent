/// <reference types="vite-plugin-electron/electron-env" />

declare namespace NodeJS {
  interface ProcessEnv {
    APP_ROOT: string
    VITE_PUBLIC: string
  }
}

// 渲染进程通过 preload 的 contextBridge 暴露；这里给出最小类型声明。
interface Window {
  ipcRenderer?: import('electron').IpcRenderer
}
