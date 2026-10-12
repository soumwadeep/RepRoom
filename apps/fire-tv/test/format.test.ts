import {
  DASH,
  buildViewModel,
  checkRows,
  coachLine,
  formScore,
  measure,
  presenceLine,
  rateLines,
  viewWarning,
} from '../src/format';
import type {RepRecord, SessionState} from '../src/types';

const rep = (overrides: Partial<RepRecord> = {}): RepRecord => ({
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
  ...overrides,
});

const session = (overrides: Partial<SessionState> = {}): SessionState => ({
  exercise: {name: 'Bodyweight squat', focus: 'Quads, glutes, core'},
  reps: 5,
  elapsed_ms: 20000,
  pause_ms: 0,
  cadence_upm: 40,
  mean_quality: 1,
  mean_tempo_ms: 1500,
  lowest_check: null,
  rep_log: [rep()],
  no_reps: 0,
  abandoned_arcs: 0,
  frames: {received: 120, with_pose: 118},
  low_confidence_frames: 2,
  view: 'side',
  recommended_view: 'side',
  view_matches: true,
  fps_estimate: 6.7,
  depth_threshold: 0.15,
  depth_threshold_source: 'absolute',
  ...overrides,
});

describe('measure', () => {
  it('never renders an unmeasured value as a number', () => {
    expect(measure(null)).toBe(DASH);
    expect(measure(undefined)).toBe(DASH);
    expect(measure(NaN)).toBe(DASH);
  });

  it('keeps a real zero at zero', () => {
    expect(measure(0)).toBe('0');
  });

  it('carries units and digits', () => {
    expect(measure(95.4, {unit: '\u00b0', digits: 0})).toBe('95\u00b0');
    expect(measure(0.0595, {digits: 2})).toBe('0.06');
  });
});

describe('formScore', () => {
  it('gives no score when no check could run', () => {
    const line = formScore(session({rep_log: [rep({checks_run: 0, quality: 0})]}));
    expect(line.text).toBe(DASH);
    expect(line.caption).toBe('no checks measurable');
    expect(line.tone).toBe('muted');
  });

  it('names the failed checks and drops the tone', () => {
    const line = formScore(session({rep_log: [rep({quality: 0.75, failed: ['depth']})]}));
    expect(line.text).toBe('75%');
    expect(line.caption).toBe('depth');
    expect(line.tone).toBe('warn');

    const bad = formScore(session({rep_log: [rep({quality: 0.4, failed: ['depth', 'tempo']})]}));
    expect(bad.tone).toBe('bad');
    expect(bad.caption).toBe('depth, tempo');
  });

  it('says how many checks were met when none failed', () => {
    expect(formScore(session()).caption).toBe('all 4 checks met');
  });

  it('returns a dash for a session that has no reps at all', () => {
    expect(formScore(session({rep_log: []})).text).toBe(DASH);
  });
});

describe('buildViewModel', () => {
  it('keeps discards and abandoned arcs out of the hero total', () => {
    const model = buildViewModel(session({reps: 12, no_reps: 3, abandoned_arcs: 1}));
    expect(model.hero).toEqual({value: 12, discarded: 3, abandoned: 1});
  });

  it('reports waiting for a camera when nothing has arrived', () => {
    const model = buildViewModel(
      session({frames: {received: 0, with_pose: 0}, reps: 0}),
      {},
    );
    expect(model.presence.text).toBe('waiting for camera');
  });

  it('takes live presence from the engine rather than inferring it', () => {
    const model = buildViewModel(session(), {presence: 'lost', reason: 'subject near the edge'});
    expect(model.presence.text).toBe('paused');
    expect(model.presence.detail).toBe('subject near the edge');
  });
});

describe('rateLines', () => {
  it('withholds tempo and cadence when the feed is too slow to measure them', () => {
    const rates = rateLines(session({fps_estimate: 2}));
    expect(rates.cadence).toBe(DASH);
    expect(rates.tempo).toBe(DASH);
    expect(rates.gate.blocked).toBe(true);
    expect(rates.gate.caption).toMatch(/4 fps/);
  });

  it('shows them when the feed is fast enough', () => {
    const rates = rateLines(session({fps_estimate: 8}));
    expect(rates.cadence).toBe('40 /min');
    expect(rates.tempo).toBe('1500 ms');
    expect(rates.fps).toBe('8.0 fps');
  });

  it('shows a dash rather than a fabricated fps when there is no session', () => {
    expect(rateLines(null).fps).toBe(DASH);
  });
});

describe('presenceLine', () => {
  it('says what the camera needs, not just that it is unhappy', () => {
    expect(presenceLine('locked').text).toBe('tracking');
    expect(presenceLine('searching').text).toBe('looking for you');
    expect(presenceLine('searching', 'torso too small').detail).toBe('torso too small');
    expect(presenceLine('lost').detail).toMatch(/dropped, not counted/);
  });
});

describe('checkRows', () => {
  const checks = [
    {
      key: 'depth',
      label: 'Depth',
      ok: true,
      severity: 'critical' as const,
      measured: 0.05,
      threshold: 0.15,
      unit: 'ratio',
      detail: 'hips at or below parallel',
      status: 'pass' as const,
    },
    {
      key: 'knee_track',
      label: 'Knee tracking',
      ok: false,
      severity: 'posture' as const,
      measured: null,
      threshold: null,
      unit: 'ratio',
      detail: 'not valid from a side camera',
      status: 'not_measurable' as const,
    },
    {
      key: 'tempo',
      label: 'Tempo',
      ok: false,
      severity: 'tempo' as const,
      measured: 640,
      threshold: 1100,
      unit: 'ms',
      detail: 'rep was rushed',
      status: 'fail' as const,
    },
  ];

  it('shows a dash for an unmeasurable check and prose for why', () => {
    const rows = checkRows(session({rep_log: [rep({checks})]}));
    expect(rows[0].value).toBe('0.05');
    expect(rows[0].tone).toBe('good');
    expect(rows[1].value).toBe(DASH);
    expect(rows[1].detail).toBe('not valid from a side camera');
    expect(rows[1].tone).toBe('muted');
  });

  it('renders milliseconds without decimal noise', () => {
    const rows = checkRows(session({rep_log: [rep({checks})]}));
    expect(rows[2].value).toBe('640');
    expect(rows[2].tone).toBe('warn');
  });

  it('marks a critical failure as bad rather than warn', () => {
    const rows = checkRows(
      session({
        rep_log: [
          rep({
            checks: [{...checks[0], status: 'fail', ok: false, detail: 'stopped above parallel'}],
          }),
        ],
      }),
    );
    expect(rows[0].tone).toBe('bad');
  });
});

describe('coachLine', () => {
  it('names the model when Bedrock produced the sentence', () => {
    const line = coachLine({text: 'Sit deeper.', source: 'bedrock', model: 'us.anthropic.claude-sonnet-4'});
    expect(line?.label).toBe('COACH · BEDROCK · us.anthropic.claude-sonnet-4');
    expect(line?.tone).toBe('good');
  });

  it('labels a rule-based sentence as a rule, visibly quieter', () => {
    const line = coachLine({text: 'Depth is the one to fix.', source: 'rules'});
    expect(line?.label).toBe('COACH · BUILT-IN RULES');
    expect(line?.tone).toBe('muted');
    expect(line?.source).toBe('rules');
  });

  it('renders nothing rather than an empty coaching block', () => {
    expect(coachLine(null)).toBeNull();
    expect(coachLine({text: '', source: 'bedrock'})).toBeNull();
  });

  it('is carried through the view model', () => {
    const model = buildViewModel(session(), {cue: {text: 'Hold the tempo.', source: 'rules'}});
    expect(model.coach?.text).toBe('Hold the tempo.');
    expect(buildViewModel(session()).coach).toBeNull();
  });
});

describe('viewWarning', () => {
  it('explains a camera that cannot grade this exercise', () => {
    const line = viewWarning(
      session({
        exercise: {name: 'Overhead press', focus: 'Shoulders'},
        view: 'side',
        recommended_view: 'front',
        view_matches: false,
      }),
    );
    expect(line?.tone).toBe('warn');
    expect(line?.text).toMatch(/front camera/);
    expect(line?.text).toMatch(/Overhead press/);
  });

  it('surfaces a degraded clock as its own warning', () => {
    const line = viewWarning(session({clock_degraded: true}));
    expect(line?.text).toMatch(/server clock/);
  });

  it('stays quiet when the setup is sound', () => {
    expect(viewWarning(session())).toBeNull();
    expect(viewWarning(null)).toBeNull();
  });
});
