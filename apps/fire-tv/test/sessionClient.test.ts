import {createSessionClient, STATUS, type Snapshot} from '../src/sessionClient';
import type {SessionState} from '../src/types';

/**
 * The polling contract, tested without a server.
 *
 * What is under test is the behaviour a viewer would notice: how fast the
 * number on the wall changes, what happens when the API stops answering, and
 * whether a frozen picture is allowed to look live.
 */

interface Handle {
  fn: () => Promise<void>;
  ms: number;
}

function fakeTimer() {
  const handles: Handle[] = [];
  return {
    handles,
    setInterval(fn: () => Promise<void>, ms: number) {
      const handle = {fn, ms};
      handles.push(handle);
      return handle as unknown as ReturnType<typeof setInterval>;
    },
    clearInterval(handle: ReturnType<typeof setInterval>) {
      const index = handles.indexOf(handle as unknown as Handle);
      if (index >= 0) handles.splice(index, 1);
    },
    nextMs() {
      return handles.length ? handles[handles.length - 1].ms : null;
    },
    fire() {
      return handles[handles.length - 1].fn();
    },
  };
}

function fakeFetch(routes: Array<{json?: unknown; ok?: boolean; status?: number; throw?: Error}>) {
  const calls: Array<{url: string; method: string; body?: unknown}> = [];
  const impl = async (url: string, init: Record<string, unknown> = {}) => {
    calls.push({url, method: (init.method as string) || 'GET', body: init.body});
    const route = routes.shift();
    if (!route) throw new Error(`no canned response left for ${url}`);
    if (route.throw) throw route.throw;
    return {
      ok: route.ok ?? true,
      status: route.status ?? 200,
      json: async () => route.json,
      text: async () => JSON.stringify(route.json ?? {}),
    } as unknown as Response;
  };
  return {impl, calls};
}

const state = (reps: number, overrides: Partial<SessionState> = {}): SessionState => ({
  exercise: {name: 'Bodyweight squat', focus: 'Quads'},
  reps,
  elapsed_ms: reps * 1500,
  pause_ms: 0,
  cadence_upm: 40,
  mean_quality: 1,
  mean_tempo_ms: 1400,
  lowest_check: null,
  rep_log: [
    {
      index: 1,
      exercise: 'squat',
      duration_ms: 1500,
      primary_min: 95,
      primary_max: 175,
      range_of_motion: 64,
      quality: 1,
      checks_run: 4,
      failed: [],
      low_confidence_frames: 0,
      checks: [],
    },
  ],
  no_reps: 0,
  abandoned_arcs: 0,
  frames: {received: 40, with_pose: 40},
  low_confidence_frames: 0,
  view: 'side',
  recommended_view: 'side',
  view_matches: true,
  fps_estimate: 8,
  depth_threshold: 0.15,
  depth_threshold_source: 'absolute',
  live: {presence: 'locked', phase: 'descending', angle: 130, reason: ''},
  ...overrides,
});

function harness(
  routes: Array<{json?: unknown; ok?: boolean; status?: number; throw?: Error}>,
  {now = 0, ...rest}: {now?: number} & Record<string, unknown> = {},
) {
  const clock = {now};
  const timer = fakeTimer();
  const fetcher = fakeFetch(routes);
  const client = createSessionClient({
    baseUrl: 'http://127.0.0.1:8420',
    fetchImpl: fetcher.impl as never,
    timer: timer as never,
    now: () => clock.now,
    pollMs: 400,
    staleAfterMs: 2500,
    ...(rest as object),
  });
  return {client, clock, timer, fetcher};
}

it('opens a session and starts exactly one poll loop', async () => {
  const {client, fetcher, timer} = harness([
    {json: {session_id: 'abc123'}},
    {json: state(1)},
  ]);
  await client.start({exercise: 'squat', view: 'side'});

  expect(client.status).toBe(STATUS.LIVE);
  expect(client.sessionId).toBe('abc123');
  expect(fetcher.calls[0].url).toBe('http://127.0.0.1:8420/session');
  expect(fetcher.calls[0].method).toBe('POST');
  expect(JSON.parse(fetcher.calls[0].body as string)).toEqual({
    exercise: 'squat',
    view: 'side',
    adaptive_depth: false,
  });
  expect(timer.handles).toHaveLength(1);

  await timer.fire();
  expect(client.pollMs).toBe(400);
});

it('turns a polled session into a view model, live presence included', async () => {
  const seen: Snapshot[] = [];
  const {client, timer} = harness([{json: {session_id: 'abc'}}, {json: state(7)}]);
  await client.start();
  const unsubscribe = client.subscribe((snapshot) => seen.push(snapshot));
  await timer.fire();

  const last = seen[seen.length - 1];
  expect(last.status).toBe(STATUS.LIVE);
  expect(last.viewModel?.hero.value).toBe(7);
  expect(last.viewModel?.presence.text).toBe('tracking');
  expect(last.viewModel?.phase).toBe('descending');
  expect(last.viewModel?.angle).toBe(130);
  expect(last.lastGoodAgeMs).toBe(0);
  unsubscribe();
});

it('backs off when polling fails and calls the picture stale once it is old', async () => {
  const {client, clock, timer} = harness([
    {json: {session_id: 'abc'}},
    {json: state(3)},
    {throw: new Error('connection refused')},
    {throw: new Error('connection refused')},
  ]);
  await client.start();
  await timer.fire();

  clock.now += 1000;
  await timer.fire();
  expect(client.status).toBe(STATUS.LIVE);
  expect(client.pollMs).toBe(800);

  clock.now += 2000;
  await timer.fire();
  expect(client.status).toBe(STATUS.STALE);
  expect(client.pollMs).toBe(1600);
  expect(client.error).toBe('connection refused');
});

it('restores live status and shortens the interval again on recovery', async () => {
  const {client, clock, timer} = harness([
    {json: {session_id: 'abc'}},
    {throw: new Error('boom')},
    {json: state(4)},
  ]);
  await client.start();
  clock.now += 5000;
  await timer.fire();
  expect(client.pollMs).toBe(800);

  await timer.fire();
  expect(client.status).toBe(STATUS.LIVE);
  expect(client.pollMs).toBe(400);
  expect(client.viewModel?.hero.value).toBe(4);
});

it('holds the ceiling of the backoff rather than growing without bound', async () => {
  const {client, timer} = harness([
    {json: {session_id: 'abc'}},
    ...Array.from({length: 8}, () => ({throw: new Error('down')})),
  ]);
  await client.start();
  for (let i = 0; i < 8; i += 1) {
    await timer.fire();
  }
  expect(client.pollMs).toBe(2000);
});

it('reports an unopenable session as an error with nothing on screen', async () => {
  const {client} = harness([{status: 400, ok: false, json: {detail: 'unknown exercise'}}]);
  await expect(client.start({exercise: 'yoga'})).rejects.toThrow(/unknown exercise/);
  expect(client.status).toBe(STATUS.ERROR);
  expect(client.viewModel).toBeNull();
});

it('stops the loop and tells the server the set is over', async () => {
  const {client, fetcher, timer} = harness([
    {json: {session_id: 'abc'}},
    {json: state(2)},
    {json: {finished: true}},
  ]);
  await client.start();
  await client.stop();

  expect(client.status).toBe(STATUS.STOPPED);
  expect(timer.handles).toHaveLength(0);
  expect(fetcher.calls.at(-1)?.url).toBe('http://127.0.0.1:8420/session/abc/stop');
});

it('stays stopped even when the server never hears the farewell', async () => {
  const {client} = harness([{json: {session_id: 'abc'}}, {throw: new Error('server gone away')}]);
  await client.start();
  await client.stop();
  expect(client.status).toBe(STATUS.STOPPED);
});

it('refuses a client with no address, because a HUD pointed at nothing is worse than an error', () => {
  expect(() => createSessionClient({baseUrl: ''} as never)).toThrow(/baseUrl/);
});

it('does no work on a tick before a session exists', async () => {
  const {client, fetcher} = harness([]);
  await client.tick();
  expect(fetcher.calls).toHaveLength(0);
});
