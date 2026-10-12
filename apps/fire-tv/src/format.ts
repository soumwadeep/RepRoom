/**
 * Presentation rules for the RepRoom HUD.
 *
 * The rule this file exists to enforce: a number that was never measured must
 * not be printed as a number. `null` renders as an explicit dash plus the
 * reason, and a percentage is only allowed when at least one form check actually
 * ran. On a screen sized for a sofa, that is the difference between an
 * instrument panel and a decoration.
 */

import type {CheckResult, Presence, SessionState} from './types';

export const DASH = '\u2014';

export type Tone = 'good' | 'warn' | 'bad' | 'muted';

export interface Line {
  text: string;
  caption?: string;
  tone: Tone;
  detail?: string;
}

export interface CheckRow {
  label: string;
  status: CheckResult['status'];
  value: string;
  detail: string;
  tone: Tone;
}

export interface ViewModel {
  hero: {value: number; discarded: number; abandoned: number};
  score: Line;
  presence: Line;
  rates: {cadence: string; tempo: string; fps: string; gate: {blocked: boolean; caption?: string}};
  checks: CheckRow[];
  warning: Line | null;
  exercise: SessionState['exercise'] | null;
  phase: string;
  angle: number | null;
  raw: SessionState;
}

/** Format a measured value, or say that there is nothing to show. */
export function measure(
  value: number | null | undefined,
  {unit = '', digits = 0, fallback = DASH}: {unit?: string; digits?: number; fallback?: string} = {},
): string {
  if (value === null || value === undefined) return fallback;
  const number = Number(value);
  if (!Number.isFinite(number)) return fallback;
  return `${number.toFixed(digits)}${unit}`;
}

/**
 * Form score as a percentage, or the honest reason it is unavailable.
 *
 * A rep where every check was unmeasurable -- subject too far from the camera,
 * or the wrong view for the exercise -- has no score. Rendering 100% there would
 * be the most misleading thing this app could do.
 */
export function formScore(state: SessionState | null): Line {
  const last = lastRep(state);
  const checksRun = last?.checks_run ?? 0;
  if (!last || checksRun === 0) {
    return {text: DASH, caption: 'no checks measurable', tone: 'muted'};
  }
  const percent = Math.round(last.quality * 100);
  if (last.failed.length === 0) {
    return {text: `${percent}%`, caption: `all ${checksRun} checks met`, tone: 'good'};
  }
  return {
    text: `${percent}%`,
    caption: last.failed.join(', '),
    tone: percent >= 75 ? 'warn' : 'bad',
  };
}

/**
 * The one number the room reads from across the sofa.
 *
 * Discarded arcs and abandoned arcs are surfaced underneath rather than folded
 * into the total, because "12 reps" and "12 of 15 attempts counted" are
 * different claims.
 */
export function heroRepCount(state: SessionState | null): ViewModel['hero'] {
  return {
    value: state?.reps ?? 0,
    discarded: state?.no_reps ?? 0,
    abandoned: state?.abandoned_arcs ?? 0,
  };
}

/** Status line: what the engine is doing and what it needs from the person. */
export function presenceLine(presence: Presence | null, reason = ''): Line {
  switch (presence) {
    case 'locked':
      return {text: 'tracking', tone: 'good', detail: reason};
    case 'searching':
      return {
        text: 'looking for you',
        tone: 'warn',
        detail: reason || 'step back so your shoulders and hips are in frame',
      };
    case 'lost':
      return {
        text: 'paused',
        tone: 'bad',
        detail: reason || 'out of frame; the rep in progress was dropped, not counted',
      };
    default:
      return {text: 'waiting for camera', tone: 'muted', detail: 'no frames received yet'};
  }
}

/** Tempo and cadence, gated on the frame rate that made them possible. */
export function rateLines(state: SessionState | null): ViewModel['rates'] {
  const fps = state?.fps_estimate ?? null;
  const blocked = fps !== null && fps < 4;
  return {
    cadence: blocked ? DASH : measure(state?.cadence_upm, {unit: ' /min'}),
    tempo: blocked ? DASH : measure(state?.mean_tempo_ms, {unit: ' ms'}),
    fps: measure(fps, {unit: ' fps', digits: 1}),
    gate: blocked
      ? {blocked: true, caption: 'feed below 4 fps: tempo not trustworthy'}
      : {blocked: false},
  };
}

/** Per-check rows, including the ones that could not run. */
export function checkRows(state: SessionState | null): CheckRow[] {
  const checks = lastRep(state)?.checks ?? [];
  return checks.map((check) => ({
    label: check.label,
    status: check.status,
    value:
      check.status === 'not_measurable'
        ? DASH
        : measure(check.measured, {
            unit: check.unit === 'deg' ? '\u00b0' : '',
            // Degrees and milliseconds are read from a distance; decimals there
            // are noise. A ratio is a small number whose second decimal is the
            // entire signal.
            digits: check.unit === 'ratio' ? 2 : 0,
          }),
    detail: check.detail,
    tone:
      check.status === 'pass'
        ? 'good'
        : check.status === 'fail'
        ? check.severity === 'critical'
          ? 'bad'
          : 'warn'
        : 'muted',
  }));
}

/** Banner explaining a camera that fights the exercise, or a clock that gave up. */
export function viewWarning(state: SessionState | null): Line | null {
  if (!state) return null;
  if (state.view_matches === false && state.recommended_view) {
    return {
      tone: 'warn',
      text: `${state.exercise.name} is graded from a ${state.recommended_view} camera. Some checks cannot run from ${state.view}.`,
    };
  }
  if (state.clock_degraded) {
    return {
      tone: 'warn',
      text: 'The camera clock moved backwards mid-set. Tempo is being measured on the server clock.',
    };
  }
  return null;
}

export function lastRep(state: SessionState | null): SessionState['rep_log'][number] | null {
  if (!state?.rep_log?.length) return null;
  return state.rep_log[state.rep_log.length - 1];
}

/**
 * Everything the HUD renders, from one session payload.
 *
 * One translation function so the component tree stays declarative and every
 * rule above is testable without a renderer or a camera.
 */
export function buildViewModel(
  state: SessionState | null,
  live: {presence?: Presence; reason?: string; phase?: string; angle?: number | null} = {},
): ViewModel {
  const last = lastRep(state);
  const presence =
    live.presence ?? (state && state.frames?.received > 0 ? 'locked' : null);
  return {
    hero: heroRepCount(state),
    score: formScore(state),
    presence: presenceLine(presence, live.reason),
    rates: rateLines(state),
    checks: checkRows(state),
    warning: viewWarning(state),
    exercise: state?.exercise ?? null,
    phase: live.phase ?? 'setup',
    angle: live.angle !== undefined ? live.angle : last?.primary_min ?? null,
    raw: state as SessionState,
  };
}
