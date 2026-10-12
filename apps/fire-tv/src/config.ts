/**
 * Where the session API lives, and what happens when it is not there.
 *
 * The default points at the device itself, which is correct when the API is
 * reached through `vega device start-port-forwarding`. A hand-entered address
 * covers the case where the API runs on another machine on the LAN -- which is
 * the normal case, since the camera and the TV are rarely the same box.
 *
 * Nothing here silently retries a stale address forever: the app shows the
 * origin it is talking to, so a screen full of zeros next to the wrong host is
 * at least a legible lie.
 */

export const DEFAULT_API_BASE = 'http://127.0.0.1:8420';

export interface ApiConfig {
  base: string;
  /** How long a picture may sit unrefreshed before the HUD calls it stale. */
  staleAfterMs: number;
  pollMs: number;
}

export const defaultConfig = (): ApiConfig => ({
  base: DEFAULT_API_BASE,
  staleAfterMs: 2500,
  pollMs: 400,
});

/**
 * Validate before persisting.
 *
 * Only the shape is checked -- reachability is the health probe's job, because
 * a syntactically fine address can still be a machine with the service down,
 * and those two failures need different messages on screen.
 */
export function normaliseBase(input: string): string | null {
  const trimmed = input.trim().replace(/\/+$/, '');
  if (!trimmed) return null;
  const hasScheme = /^[a-zA-Z][\w+.-]*:\/\//.test(trimmed);
  const withScheme = hasScheme ? trimmed : `http://${trimmed}`;
  const match = /^(https?):\/\/([\w.-]+)(?::(\d{1,5}))?$/i.exec(withScheme);
  if (!match) return null;
  const scheme = match[1].toLowerCase();
  if (scheme !== 'http' && scheme !== 'https') return null;
  const port = match[3];
  if (port !== undefined) {
    const value = Number(port);
    if (value < 1 || value > 65535) return null;
    return `${scheme}://${match[2]}:${port}`;
  }
  return `${scheme}://${match[2]}`;
}

export function isReachableDefault(base: string): boolean {
  return base === DEFAULT_API_BASE;
}
