/**
 * The wire contract between the session API and the TV.
 *
 * Hand-written rather than generated, and deliberately full of `| null`: the
 * server's unmeasured values arrive as JSON null, and a type that pretends they
 * are numbers is how a HUD ends up printing `0` where the truth is "we could not
 * see you". Every nullable here matches a real `None` on the Python side.
 */

export type Presence = 'locked' | 'searching' | 'lost';

export type CheckStatus = 'pass' | 'fail' | 'not_measurable';

export type Severity = 'critical' | 'posture' | 'tempo';

export interface CheckResult {
  key: string;
  label: string;
  ok: boolean;
  severity: Severity;
  measured: number | null;
  threshold: number | null;
  unit: string;
  detail: string;
  status: CheckStatus;
}

export interface RepRecord {
  index: number;
  exercise: string;
  duration_ms: number;
  primary_min: number | null;
  primary_max: number | null;
  range_of_motion: number | null;
  quality: number;
  checks_run: number;
  failed: string[];
  low_confidence_frames: number;
  checks: CheckResult[];
}

export interface ExerciseInfo {
  key?: string;
  name: string;
  focus: string;
  primary_label?: string;
  up_angle?: number;
  down_angle?: number;
  guidance?: string;
}

/** What `GET /session/{id}` returns. */
export interface SessionState {
  exercise: ExerciseInfo;
  reps: number;
  elapsed_ms: number;
  pause_ms: number;
  cadence_upm: number | null;
  mean_quality: number | null;
  mean_tempo_ms: number | null;
  lowest_check: string | null;
  rep_log: RepRecord[];
  no_reps: number;
  abandoned_arcs: number;
  frames: {received: number; with_pose: number};
  low_confidence_frames: number;
  view: 'side' | 'front';
  recommended_view?: 'side' | 'front';
  view_matches?: boolean;
  fps_estimate: number | null;
  depth_threshold: number;
  depth_threshold_source: string;
  clock_degraded?: boolean;
  finished?: boolean;
  detect_ms?: {last: number; mean: number};
  /** The engine's latest per-frame answer, mirrored for the polling display. */
  live?: {
    presence?: Presence | 'waiting';
    phase?: string;
    angle?: number | null;
    reason?: string;
  };
}

/** What `POST /session/{id}/frame` returns. */
export interface FrameUpdate {
  reps: number;
  phase: string;
  angle: number | null;
  presence: Presence;
  reason: string;
  completed: RepRecord | null;
  discarded: RepRecord | null;
  cadence_upm: number | null;
  session_quality: number | null;
  fps: number | null;
  live_checks: CheckResult[];
  arrival_gap_ms: number | null;
  clock_source: 'sender-monotonic' | 'server-arrival';
  detect_ms: number;
  detected_by: string;
  frames: {received: number; with_pose: number};
}

/** A coaching line plus where it came from. `source` is displayed, not hidden. */
export interface Cue {
  text: string;
  source: 'bedrock' | 'rules';
  label: string;
  model: string | null;
  latency_ms: number | null;
  reason: string;
  rep_key: string;
}

export interface CatalogueEntry {
  key: string;
  name: string;
  focus: string;
  view: 'side' | 'front';
  guidance: string;
  checks: string[];
}
