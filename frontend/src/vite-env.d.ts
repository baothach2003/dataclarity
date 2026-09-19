// No imports here: they would turn this file into a module and break the
// augmentation (https://vite.dev/guide/env-and-mode).
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
