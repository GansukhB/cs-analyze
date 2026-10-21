// Telling "it isn't there" from "the server didn't answer" (OPS-8). The fetch
// middleware stamps every failed response's body with its status; a 404 says
// the thing is missing, anything else (a 5xx, Cloudflare's 52x, no network)
// that it could not be read, with a way to try again.
export function errorStatus(error: unknown): number | null {
  if (error && typeof error === 'object' && 'status' in error && typeof error.status === 'number') return error.status
  return null
}

/** Retry once what may pass on a second go: a server error or no network. */
export function retryOnce(failures: number, error: unknown): boolean {
  const status = errorStatus(error)
  return failures < 1 && (status === null || status >= 500)
}
