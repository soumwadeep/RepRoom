import React, {useState} from 'react';
import {Pressable, StyleSheet, Text, View} from 'react-native';

import {colors, tones, type as t, spacing} from '../theme';
import type {CheckRow, Line, ViewModel} from '../format';

/**
 * The live HUD. Pure: it takes a view model and renders it.
 *
 * Every element here has a source measurement behind it or is explicitly drawn
 * as a dash with a reason. That is not a style choice -- the alternative is a
 * screen that reports numbers nobody measured, which is the fastest way to make
 * a camera in the living room untrustworthy.
 */

export interface HudProps {
  model: ViewModel | null;
  status: string;
  ageMs: number | null;
  sessionCode: string | null;
  apiBase: string;
  onFinish: () => void;
}

export const Hud = ({model, status, ageMs, sessionCode, apiBase, onFinish}: HudProps) => {
  const stale = status === 'stale' || status === 'error';
  if (!model) {
    return (
      <View style={styles.empty}>
        <Text style={styles.emptyTitle}>NO SESSION</Text>
        <Text style={styles.emptyBody}>
          Pick an exercise and the TV will start polling the session API. Nothing
          here is drawn until a frame has been measured.
        </Text>
      </View>
    );
  }

  const hero = model.hero;
  return (
    <View style={styles.root} testID="hud">
      <View style={styles.topBand}>
        <View style={styles.titleBlock}>
          <Text style={styles.exerciseName}>{model.exercise?.name ?? 'Unknown exercise'}</Text>
          <Text style={styles.exerciseFocus}>{model.exercise?.focus ?? ''}</Text>
        </View>
        <StatusPill line={model.presence} stale={stale} ageMs={ageMs} />
      </View>

      {model.warning ? <Banner line={model.warning} /> : null}

      <View style={styles.mainRow}>
        <View style={styles.counterBlock}>
          <Text style={styles.heroValue} testID="rep-count">
            {hero.value}
          </Text>
          <Text style={styles.heroUnit}>REPS COUNTED</Text>
          <View style={styles.attemptRow}>
            <Metric label="DISCARDED" value={String(hero.discarded)} tone="warn" hint="arc too short or too fast" />
            <Metric label="ABANDONED" value={String(hero.abandoned)} tone="muted" hint="left frame mid-rep" />
            <Metric label="FORM" value={model.score.text} tone={model.score.tone} hint={model.score.caption ?? ''} />
          </View>

          {model.coach ? (
            <View style={styles.coach} testID="coach">
              <Text style={styles.coachLabel}>{model.coach.label}</Text>
              <Text style={[styles.coachText, {color: tones[model.coach.tone]}]}>{model.coach.text}</Text>
            </View>
          ) : null}
        </View>

        <View style={styles.sideColumn}>
          <Panel title="RATES">
            <Row label="CADENCE" value={model.rates.cadence} />
            <Row label="TEMPO" value={model.rates.tempo} />
            <Row label="FEED" value={model.rates.fps} />
            {model.rates.gate.blocked ? (
              <Text style={styles.panelNote}>{model.rates.gate.caption}</Text>
            ) : null}
          </Panel>

          <Panel title="LAST REP">
            {model.checks.length === 0 ? (
              <Text style={styles.panelNote}>
                No completed rep yet. Checks appear the moment one does.
              </Text>
            ) : (
              model.checks.map((row, index) => (
                <CheckRowView key={`${row.label}-${index}`} row={row} />
              ))
            )}
          </Panel>
        </View>
      </View>

      <View style={styles.footer}>
        <View style={styles.pairing}>
          <Text style={styles.pairLabel}>CAMERA JOINS WITH CODE</Text>
          <Text style={styles.pairCode} testID="session-code">
            {sessionCode ?? '\u2014'}
          </Text>
          <Text style={styles.footerText}>{apiBase}/capture</Text>
        </View>
        <Text style={styles.footerText}>
          depth target {model.raw.depth_threshold} · {model.raw.depth_threshold_source} · camera
          view {model.raw.view} · frames {model.raw.frames?.received ?? 0}
        </Text>
        <FinishButton onPress={onFinish} />
      </View>

      {stale ? (
        <View style={styles.staleVeil} testID="stale-veil">
          <Text style={styles.staleTitle}>SIGNAL LOST</Text>
          <Text style={styles.staleBody}>
            Last reading {ageMs === null ? 'never' : `${Math.round(ageMs / 1000)}s`} ago. These
            figures are frozen, not current.
          </Text>
        </View>
      ) : null}
    </View>
  );
};

export const StatusPill = ({
  line,
  stale,
  ageMs,
}: {
  line: Line;
  stale: boolean;
  ageMs: number | null;
}) => {
  const tone = stale ? 'muted' : line.tone;
  return (
    <View style={[styles.pill, {borderColor: tones[tone]}]}>
      <View style={[styles.pillDot, {backgroundColor: tones[tone]}]} />
      <Text style={[styles.pillText, {color: tones[tone]}]}>{line.text.toUpperCase()}</Text>
      {stale && ageMs !== null ? (
        <Text style={styles.pillAge}>{Math.round(ageMs / 1000)}s</Text>
      ) : null}
    </View>
  );
};

export const Banner = ({line}: {line: Line}) => (
  <View style={[styles.banner, {borderColor: tones[line.tone]}]}>
    <Text style={[styles.bannerText, {color: tones[line.tone]}]}>{line.text}</Text>
  </View>
);

export const Panel = ({title, children}: {title: string; children: React.ReactNode}) => (
  <View style={styles.panel}>
    <Text style={styles.panelTitle}>{title}</Text>
    {children}
  </View>
);

export const Row = ({label, value}: {label: string; value: string}) => (
  <View style={styles.row}>
    <Text style={styles.rowLabel}>{label}</Text>
    <Text style={styles.rowValue}>{value}</Text>
  </View>
);

export const Metric = ({
  label,
  value,
  tone,
  hint,
}: {
  label: string;
  value: string;
  tone: string;
  hint: string;
}) => (
  <View style={styles.metric}>
    <Text style={styles.metricLabel}>{label}</Text>
    <Text style={[styles.metricValue, {color: tones[tone] ?? colors.ink}]}>{value}</Text>
    {hint ? <Text style={styles.metricHint}>{hint}</Text> : null}
  </View>
);

export const CheckRowView = ({row}: {row: CheckRow}) => (
  <View style={styles.row} testID={`check-${row.label}`}>
    <Text style={styles.rowLabel}>{row.label.toUpperCase()}</Text>
    <Text style={[styles.rowValue, {color: tones[row.tone] ?? colors.ink}]}>{row.value}</Text>
    <Text style={styles.rowDetail}>
      {row.status === 'not_measurable' ? 'not measured' : row.detail}
    </Text>
  </View>
);

/**
 * Focus is tracked by hand.
 *
 * Vega's `Pressable` state callback exposes `pressed` but not `focused`, so the
 * highlight a television needs has to come from onFocus/onBlur. Worth knowing
 * before the second component in this app tries to style focus the mobile way.
 */
export const FinishButton = ({onPress}: {onPress: () => void}) => {
  const [focused, setFocused] = useState(false);
  return (
    <Pressable
      onPress={onPress}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      accessibilityRole="button"
      accessibilityLabel="Finish this set"
      testID="finish-set"
      style={[styles.finish, focused ? styles.finishFocused : null]}>
      <Text style={styles.finishText}>FINISH SET</Text>
    </Pressable>
  );
};

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bg,
    paddingHorizontal: spacing.gutter,
    paddingTop: 40,
    paddingBottom: 28,
  },
  empty: {flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center'},
  emptyTitle: {...t.label, color: colors.focus},
  emptyBody: {...t.body, color: colors.inkDim, maxWidth: 720, textAlign: 'center', marginTop: 12},
  topBand: {flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between'},
  titleBlock: {flex: 1},
  exerciseName: {...t.title, color: colors.ink},
  exerciseFocus: {...t.label, color: colors.inkFaint, marginTop: 6},
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 18,
    paddingVertical: 10,
  },
  pillDot: {width: 10, height: 10, borderRadius: 5, marginRight: 10},
  pillText: {...t.label, fontWeight: '700'},
  pillAge: {...t.label, color: colors.inkFaint, marginLeft: 10},
  banner: {
    borderWidth: 1,
    borderLeftWidth: 4,
    borderRadius: 6,
    padding: 14,
    marginTop: 18,
  },
  bannerText: {...t.body},
  mainRow: {flexDirection: 'row', flex: 1, marginTop: 28, gap: 40},
  counterBlock: {flex: 1.15, justifyContent: 'center'},
  heroValue: {...t.hero, color: colors.ink, fontVariant: ['tabular-nums']},
  heroUnit: {...t.label, color: colors.focus, marginTop: -8},
  attemptRow: {flexDirection: 'row', marginTop: 34, gap: 28},
  metric: {minWidth: 150},
  metricLabel: {...t.label, color: colors.inkFaint},
  metricValue: {...t.value, marginTop: 6},
  metricHint: {...t.label, color: colors.inkFaint, marginTop: 4, maxWidth: 180},
  sideColumn: {flex: 1, gap: 20},
  coach: {
    marginTop: 30,
    borderLeftWidth: 3,
    borderLeftColor: colors.panelEdge,
    paddingLeft: 18,
  },
  coachLabel: {...t.label, color: colors.inkFaint},
  coachText: {...t.body, color: colors.ink, marginTop: 6, maxWidth: 720},
  panel: {
    backgroundColor: colors.panel,
    borderWidth: 1,
    borderColor: colors.panelEdge,
    borderRadius: 10,
    padding: 20,
  },
  panelTitle: {...t.label, color: colors.accent, marginBottom: 12},
  panelNote: {...t.label, color: colors.inkFaint},
  row: {flexDirection: 'row', alignItems: 'center', paddingVertical: 8},
  rowLabel: {...t.label, color: colors.inkDim, width: 170},
  rowValue: {...t.value, color: colors.ink, minWidth: 120},
  rowDetail: {...t.label, color: colors.inkFaint, flex: 1, marginLeft: 12},
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: 24,
  },
  pairing: {gap: 2},
  pairLabel: {...t.label, color: colors.accent},
  pairCode: {...t.value, color: colors.focus, letterSpacing: 6},
  footerText: {...t.label, color: colors.inkFaint},
  finish: {
    borderWidth: 1,
    borderColor: colors.panelEdge,
    borderRadius: 6,
    paddingHorizontal: 26,
    paddingVertical: 12,
  },
  finishFocused: {borderColor: colors.focus, backgroundColor: 'rgba(53,224,200,0.12)'},
  finishText: {...t.label, color: colors.ink},
  staleVeil: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    height: 120,
    backgroundColor: 'rgba(4,7,13,0.94)',
    borderTopWidth: 2,
    borderTopColor: colors.warn,
    alignItems: 'center',
    justifyContent: 'center',
  },
  staleTitle: {...t.label, color: colors.warn, letterSpacing: 6},
  staleBody: {...t.body, color: colors.inkDim, marginTop: 6},
});
