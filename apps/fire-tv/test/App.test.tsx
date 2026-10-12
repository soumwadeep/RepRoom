import React from 'react';
import {act, fireEvent, render, waitFor} from '@testing-library/react-native';

import {App} from '../src/App';
import type {CatalogueEntry, SessionState} from '../src/types';

/**
 * Screen-flow tests against a scripted API.
 *
 * These are the assertions the demo depends on: the TV shows the pairing code
 * the camera needs, a live session renders measured reps, and a server that
 * stops answering produces a visible "signal lost" rather than a confident
 * frozen number.
 */

const CATALOGUE: CatalogueEntry[] = [
  {
    key: 'squat',
    name: 'Bodyweight squat',
    focus: 'Quads, glutes, core',
    view: 'side',
    guidance: 'side, 3 m back',
    checks: ['depth', 'tempo'],
  },
  {
    key: 'pushup',
    name: 'Push-up',
    focus: 'Chest',
    view: 'side',
    guidance: 'floor level',
    checks: ['body_line'],
  },
];

const state = (reps: number, overrides: Partial<SessionState> = {}): SessionState => ({
  exercise: {name: 'Bodyweight squat', focus: 'Quads, glutes, core'},
  reps,
  elapsed_ms: 18000,
  pause_ms: 0,
  cadence_upm: 40,
  mean_quality: 1,
  mean_tempo_ms: 1500,
  lowest_check: null,
  rep_log: [
    {
      index: reps,
      exercise: 'squat',
      duration_ms: 1500,
      primary_min: 95,
      primary_max: 175,
      range_of_motion: 64,
      quality: 1,
      checks_run: 4,
      failed: [],
      low_confidence_frames: 0,
      checks: [
        {
          key: 'knee_track',
          label: 'Knee tracking',
          ok: false,
          severity: 'posture',
          measured: null,
          threshold: null,
          unit: 'ratio',
          detail: 'not valid from a side camera',
          status: 'not_measurable',
        },
      ],
    },
  ],
  no_reps: 1,
  abandoned_arcs: 0,
  frames: {received: 120, with_pose: 118},
  low_confidence_frames: 2,
  view: 'side',
  recommended_view: 'side',
  view_matches: true,
  fps_estimate: 8,
  depth_threshold: 0.15,
  depth_threshold_source: 'absolute',
  live: {presence: 'locked', phase: 'bottom', angle: 95, reason: ''},
  ...overrides,
});

function scriptedApi(handlers: Record<string, () => unknown> = {}) {
  const seen: string[] = [];
  const fallback: Record<string, () => unknown> = {
    'GET /health': () => ({status: 'ok', detected_by: 'mediapipe-pose-landmarker'}),
    'GET /exercises': () => CATALOGUE,
    'POST /session': () => ({session_id: 'k7d21f'}),
    'GET /session/k7d21f': () => state(6),
    'POST /session/k7d21f/stop': () => state(9, {finished: true}),
    ...handlers,
  };
  const impl = async (url: string, init: Record<string, unknown> = {}) => {
    const method = (init.method as string) || 'GET';
    const path = url.replace(/^https?:\/\/[^/]+/, '');
    const key = `${method} ${path}`;
    seen.push(key);
    const handler = fallback[key];
    if (!handler) return {ok: false, status: 404, json: async () => ({detail: `unhandled ${key}`}), text: async () => ''} as unknown as Response;
    return {ok: true, status: 200, json: async () => handler(), text: async () => ''} as unknown as Response;
  };
  return {impl: impl as typeof fetch, seen};
}

/**
 * The probe path is two sequential fetches; under a loaded CI box the default
 * 1 s wait is shorter than the scheduler's word, not shorter than the app's
 * contract. The assertion is 'this eventually renders', so say that.
 */
const SETTLE = {timeout: 8000, interval: 25};

const renderApp = (api: ReturnType<typeof scriptedApi>) =>
  render(<App fetchImpl={api.impl} initialApiBase="http://127.0.0.1:8420" />);

it('starts on setup and lists what the API offers', async () => {
  const api = scriptedApi();
  const {getByText} = renderApp(api);
  await waitFor(() => expect(getByText('BODYWEIGHT SQUAT')).toBeTruthy(), SETTLE);
  expect(getByText('PUSH-UP')).toBeTruthy();
  expect(api.seen).toContain('GET /health');
});

it('refuses to list exercises when the API is not answering', async () => {
  const api = {
    impl: (async () => {
      throw new Error('ECONNREFUSED');
    }) as typeof fetch,
    seen: [] as string[],
  };
  const {getByText} = render(
    <App fetchImpl={api.impl} initialApiBase="http://127.0.0.1:9" />,
  );
  await waitFor(
    () => expect(getByText(/no API answering at http:\/\/127\.0\.0\.1:9/)).toBeTruthy(),
    SETTLE,
  );
});

it('opens a session and puts the pairing code on screen', async () => {
  const api = scriptedApi();
  const {getByTestId, getByText} = renderApp(api);
  await waitFor(() => expect(getByText('BODYWEIGHT SQUAT')).toBeTruthy(), SETTLE);

  await act(async () => {
    fireEvent.press(getByText('BODYWEIGHT SQUAT'));
  });

  await waitFor(() => expect(getByTestId('session-code').props.children).toBe('k7d21f'), SETTLE);
  expect(api.seen).toContain('POST /session');
  expect(getByText('6')).toBeTruthy();
  expect(getByText(/CAMERA JOINS WITH CODE/)).toBeTruthy();
  expect(getByText(/127\.0\.0\.1:8420\/capture/)).toBeTruthy();
});

it('renders measured reps, discards and an unmeasurable check as a dash', async () => {
  const api = scriptedApi();
  const {getByTestId, getByText} = renderApp(api);
  await waitFor(() => expect(getByText('BODYWEIGHT SQUAT')).toBeTruthy(), SETTLE);
  await act(async () => {
    fireEvent.press(getByText('BODYWEIGHT SQUAT'));
  });

  await waitFor(() => expect(getByTestId('rep-count').props.children).toBe(6), SETTLE);
  expect(getByText('DISCARDED')).toBeTruthy();
  expect(getByText('1')).toBeTruthy();
  expect(getByText('\u2014')).toBeTruthy();
  expect(getByText('not measured')).toBeTruthy();
  expect(getByText(/all 4 checks met/)).toBeTruthy();
});

it('finishes a set and reads the totals back from the server', async () => {
  const api = scriptedApi();
  const {getByText} = renderApp(api);
  await waitFor(() => expect(getByText('BODYWEIGHT SQUAT')).toBeTruthy(), SETTLE);
  await act(async () => {
    fireEvent.press(getByText('BODYWEIGHT SQUAT'));
  });
  await waitFor(() => expect(getByText('FINISH SET')).toBeTruthy(), SETTLE);

  await act(async () => {
    fireEvent.press(getByText('FINISH SET'));
  });

  await waitFor(() => expect(getByText('SET COMPLETE')).toBeTruthy(), SETTLE);
  expect(api.seen).toContain('POST /session/k7d21f/stop');
  expect(getByText('9')).toBeTruthy();
  expect(getByText(/absolute/)).toBeTruthy();
});

it('keeps the summary honest when the totals never arrive', async () => {
  const api = scriptedApi({'POST /session/k7d21f/stop': () => {
    throw new Error('server went away');
  }});
  const {getByText} = renderApp(api);
  await waitFor(() => expect(getByText('BODYWEIGHT SQUAT')).toBeTruthy(), SETTLE);
  await act(async () => {
    fireEvent.press(getByText('BODYWEIGHT SQUAT'));
  });
  await waitFor(() => expect(getByText('FINISH SET')).toBeTruthy(), SETTLE);
  await act(async () => {
    fireEvent.press(getByText('FINISH SET'));
  });
  await waitFor(() => expect(getByText('SET COMPLETE')).toBeTruthy(), SETTLE);
  expect(getByText(/will not guess at it/)).toBeTruthy();
});

it('re-probes when a different address is committed from the keypad', async () => {
  const api = scriptedApi();
  const {getByText} = renderApp(api);
  await waitFor(() => expect(getByText('BODYWEIGHT SQUAT')).toBeTruthy(), SETTLE);
  const probesBefore = api.seen.filter((entry) => entry === 'GET /health').length;

  await act(async () => {
    fireEvent.press(getByText('C'));
  });
  for (const key of ['1', '9', '2', '.', '1', '6', '8', '.', '1', '.', '5', ':', '8', '4', '2', '0']) {
    await act(async () => {
      fireEvent.press(getByText(key));
    });
  }
  await act(async () => {
    fireEvent.press(getByText('E'));
  });

  await waitFor(
    () => expect(api.seen.filter((entry) => entry === 'GET /health').length).toBe(probesBefore + 1),
    SETTLE,
  );
  expect(getByText('BODYWEIGHT SQUAT')).toBeTruthy();
});

it('does not re-probe when the committed address is the one already in use', async () => {
  const api = scriptedApi();
  const {getByText} = renderApp(api);
  await waitFor(() => expect(getByText('BODYWEIGHT SQUAT')).toBeTruthy(), SETTLE);
  const probesBefore = api.seen.filter((entry) => entry === 'GET /health').length;

  await act(async () => {
    fireEvent.press(getByText('E'));
  });

  expect(api.seen.filter((entry) => entry === 'GET /health')).toHaveLength(probesBefore);
});
