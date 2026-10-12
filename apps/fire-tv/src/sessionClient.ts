/**
 * Session client for the RepRoom TV app.
 *
 * The television is a pure display: it opens a session, polls the API for
 * state, and renders. It measures nothing and keeps no view model of its own
 * between polls.
 *
 * Two behaviours matter on a big screen.
 *
 * If polling starts failing, subscribers are told `stale` together with the age
 * of the last good frame, rather than being left to replay whatever they last
 * rendered -- a rep counter frozen at 12 is an active claim that the session is
 * still at 12. And polling backs off under load instead of hammering a machine
 * that is already spending its time on pose detection, then decays back down
 * once the server answers again.
 */

import {buildViewModel, type ViewModel} from './format';
import type {FrameUpdate, Presence, SessionState} from './types';

export const STATUS = {
  IDLE: 'idle',
  CONNECTING: 'connecting',
  LIVE: 'live',
  STALE: 'stale',
  ERROR: 'error',
  STOPPED: 'stopped',
} as const;

export type Status = (typeof STATUS)[keyof typeof STATUS];

export interface Snapshot {
  status: Status;
  sessionId: string | null;
  error: string | null;
  viewModel: ViewModel | null;
  lastGoodAgeMs: number | null;
  pollMs: number;
}

export interface SessionClientOptions {
  baseUrl: string;
  fetchImpl?: (url: string, init?: Record<string, unknown>) => Promise<Response>;
  timer?: {setInterval: typeof setInterval; clearInterval: typeof clearInterval};
  pollMs?: number;
  staleAfterMs?: number;
  now?: () => number;
}

export interface StartOptions {
  exercise?: string;
  view?: 'side' | 'front';
  adaptiveDepth?: boolean;
}

const POLL_MIN_MS = 150;
const POLL_MAX_MS = 2000;

export function createSessionClient(options: SessionClientOptions) {
  const {
    baseUrl,
    fetchImpl = globalThis.fetch,
    timer = globalThis,
    pollMs = 400,
    staleAfterMs = 2500,
    now = () => Date.now(),
  } = options;

  if (!baseUrl) throw new Error('createSessionClient needs a baseUrl');

  let status: Status = STATUS.IDLE;
  let sessionId: string | null = null;
  let viewModel: ViewModel | null = null;
  let lastGoodAt: number | null = null;
  let interval = pollMs;
  let error: string | null = null;
  let stopped = false;
  let handle: ReturnType<typeof setInterval> | null = null;
  const listeners = new Set<(snapshot: Snapshot) => void>();

  const emit = () => {
    const snapshot: Snapshot = {
      status,
      sessionId,
      error,
      viewModel,
      lastGoodAgeMs: lastGoodAt === null ? null : now() - lastGoodAt,
      pollMs: interval,
    };
    listeners.forEach((listener) => listener(snapshot));
  };

  const url = (path: string) => `${baseUrl.replace(/\/$/, '')}${path}`;

  async function request<T>(path: string, init: Record<string, unknown> = {}): Promise<T> {
    const response = await fetchImpl(url(path), {
      ...init,
      headers: {'Content-Type': 'application/json', ...((init.headers as object) || {})},
    });
    if (!response.ok) {
      const body = await response.text().catch(() => '');
      throw new Error(`${path} -> ${response.status} ${body}`.trim());
    }
    return response.json() as Promise<T>;
  }

  function retune() {
    if (handle) timer.clearInterval(handle);
    handle = timer.setInterval(tick, interval);
  }

  async function start(startOptions: StartOptions = {}): Promise<{session_id: string}> {
    const {exercise = 'squat', view = 'side', adaptiveDepth = false} = startOptions;
    status = STATUS.CONNECTING;
    stopped = false;
    error = null;
    emit();
    try {
      const created = await request<{session_id: string}>('/session', {
        method: 'POST',
        body: JSON.stringify({exercise, view, adaptive_depth: adaptiveDepth}),
      });
      sessionId = created.session_id;
      status = STATUS.LIVE;
      lastGoodAt = now();
      interval = pollMs;
      emit();
      retune();
      return created;
    } catch (err) {
      status = STATUS.ERROR;
      error = messageOf(err);
      emit();
      throw err;
    }
  }

  async function tick() {
    if (stopped || !sessionId) return;
    try {
      const state = await request<SessionState>(`/session/${sessionId}`);
      const live = state.live ?? {};
      viewModel = buildViewModel(state, {
        presence: live.presence as Presence | undefined,
        phase: live.phase,
        reason: live.reason,
        angle: live.angle ?? null,
      });
      lastGoodAt = now();
      if (status !== STATUS.LIVE) status = STATUS.LIVE;
      if (interval > pollMs) {
        interval = Math.max(POLL_MIN_MS, Math.round(interval / 2));
        retune();
      }
    } catch (err) {
      error = messageOf(err);
      const age = lastGoodAt === null ? Infinity : now() - lastGoodAt;
      status = age > staleAfterMs ? STATUS.STALE : STATUS.LIVE;
      interval = Math.min(POLL_MAX_MS, Math.max(interval * 2, pollMs));
      retune();
    }
    emit();
  }

  async function stop() {
    stopped = true;
    if (handle) timer.clearInterval(handle);
    handle = null;
    status = STATUS.STOPPED;
    if (sessionId) {
      try {
        await request(`/session/${sessionId}/stop`, {method: 'POST'});
      } catch {
        // The totals stay on the server either way, and the screen has already
        // said stop. A failed farewell is not a reason to keep polling.
      }
    }
    emit();
  }

  function subscribe(listener: (snapshot: Snapshot) => void) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  }

  return {
    start,
    stop,
    tick,
    subscribe,
    get status() {
      return status;
    },
    get sessionId() {
      return sessionId;
    },
    get viewModel() {
      return viewModel;
    },
    get error() {
      return error;
    },
    get pollMs() {
      return interval;
    },
  };
}

export type SessionClient = ReturnType<typeof createSessionClient>;

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** Re-exported so a caller can render one frame update without a poll cycle. */
export type {FrameUpdate};
