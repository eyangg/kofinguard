/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 배포 시 백엔드(Lightsail) 주소. 로컬에서는 비워 두고 Vite 프록시를 쓴다. */
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
