import React from 'react';
import {render} from '@testing-library/react-native';

import {Hud} from '../src/components/Hud';
import {buildViewModel} from '../src/format';
import type {SessionState} from '../src/types';

/**
 * Structural tests for the live HUD.
 *
 * The setup screen was confirmed by eye on the emulator; the running screen has
 * never been looked at, because the virtual device has no screen capture. These
 * tests are the substitute: they pin the regions a viewer depends on being
 * present, legible and correctly labelled, and a snapshot catches a layout
 * regression when someone changes the theme.
 */

const state: SessionState = {
  exercise: {name: 'Bodyweight squat', focus: 'Quads, glutes, core'},
  reps: 12,
  elapsed_ms: 21000,
  pause_ms: 1500,
  cadence_upm: 34.3,
  mean_quality: 0.81,
  mean_tempo_ms: 1600,
  lowest_check: 'Depth',
  rep_log: [
    {
      index: 12,
      exercise: 'squat',
      duration_ms: 1600,
      primary_min: 108,
      primary_max: 175,
      range_of_motion: 67,
      quality: 0.75,
      checks_run: 4,
      failed: ['depth'],
      low_confidence_frames: 0,
      checks: [
        {
          key: 'depth',
          label: 'Depth',
          ok: false,
          severity: 'critical',
          measured: 0.211,
          threshold: 0.15,
          unit: 'ratio',
          detail: 'above the depth target',
          status: 'fail',
        },
        {
          key: 'torso_lean',
          label: 'Back angle',
          ok: true,
          severity: 'posture',
          measured: 31.4,
          threshold: 60,
          unit: 'deg',
          detail: 'torso within range',
          status: 'pass',
        },
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
        {
          key: 'tempo',
          label: 'Tempo',
          ok: true,
          severity: 'tempo',
          measured: 1600,
          threshold: 1100,
          unit: 'ms',
          detail: 'controlled through the arc',
          status: 'pass',
        },
      ],
    },
  ],
  no_reps: 2,
  abandoned_arcs: 1,
  frames: {received: 168, with_pose: 160},
  low_confidence_frames: 8,
  view: 'side',
  recommended_view: 'side',
  view_matches: true,
  fps_estimate: 7.9,
  depth_threshold: 0.15,
  depth_threshold_source: 'absolute',
  live: {presence: 'locked', phase: 'bottom', angle: 108, reason: ''},
};

const cue = {
  text: 'Depth is the one to fix: slow the lowering phase.',
  source: 'rules' as const,
  label: 'built-in rules',
  model: null,
  latency_ms: null,
  reason: 'no AWS region configured',
  rep_key: 'v1:squat:12:depth',
};

const model = buildViewModel(state, {
  presence: 'locked',
  phase: 'bottom',
  angle: 108,
  cue,
});

const renderHud = (overrides: Partial<Parameters<typeof Hud>[0]> = {}) =>
  render(
    <Hud
      model={model}
      status="live"
      ageMs={120}
      sessionCode="k7d21f"
      apiBase="http://192.168.29.2:8420"
      onFinish={() => {}}
      {...overrides}
    />,
  );

it('shows the counted reps as the dominant number', () => {
  const {getByTestId, getByText} = renderHud();
  expect(getByTestId('rep-count').props.children).toBe(12);
  expect(getByText('REPS COUNTED')).toBeTruthy();
});

it('keeps discards and abandoned arcs visible next to the total', () => {
  const {getByText} = renderHud();
  expect(getByText('DISCARDED')).toBeTruthy();
  expect(getByText('ABANDONED')).toBeTruthy();
  expect(getByText('2')).toBeTruthy();
  expect(getByText('1')).toBeTruthy();
});

it('renders every graded check, including the one that could not run', () => {
  const {getByText} = renderHud();
  expect(getByText('DEPTH')).toBeTruthy();
  expect(getByText('BACK ANGLE')).toBeTruthy();
  expect(getByText('KNEE TRACKING')).toBeTruthy();
  expect(getByText('not measured')).toBeTruthy();
  expect(getByText('0.21')).toBeTruthy();
  expect(getByText('31°')).toBeTruthy();
});

it('names what produced the coaching line', () => {
  const {getByTestId, getByText} = renderHud();
  expect(getByTestId('coach')).toBeTruthy();
  expect(getByText('COACH · BUILT-IN RULES')).toBeTruthy();
  expect(getByText('Depth is the one to fix: slow the lowering phase.')).toBeTruthy();
});

it('shows the pairing code and the address the camera must open', () => {
  const {getByTestId, getByText} = renderHud();
  expect(getByTestId('session-code').props.children).toBe('k7d21f');
  expect(getByText('http://192.168.29.2:8420/capture')).toBeTruthy();
});

it('publishes the depth threshold and where it came from', () => {
  const {getByText} = renderHud();
  expect(getByText(/depth target 0\.15 · absolute/)).toBeTruthy();
});

it('covers the screen with a signal-lost notice when polling has gone stale', () => {
  const {getByTestId, getByText} = renderHud({status: 'stale', ageMs: 6400});
  expect(getByTestId('stale-veil')).toBeTruthy();
  expect(getByText('SIGNAL LOST')).toBeTruthy();
  expect(getByText(/Last reading 6s ago/)).toBeTruthy();
  expect(getByText(/frozen, not current/)).toBeTruthy();
});

it('draws nothing invented when there is no session yet', () => {
  const {getByText, queryByTestId} = renderHud({model: null, sessionCode: null, ageMs: null});
  expect(queryByTestId('rep-count')).toBeNull();
  expect(getByText('NO SESSION')).toBeTruthy();
  expect(getByText(/Nothing here is drawn until a frame has been measured/)).toBeTruthy();
});

it('lays out a full live session as expected', () => {
  const {toJSON} = renderHud();
  expect(toJSON()).toMatchSnapshot();
});
