import React, {useCallback, useEffect, useRef, useState} from 'react';
import {Pressable, StyleSheet, Text, View} from 'react-native';

import {Hud} from './components/Hud';
import {Setup} from './components/Setup';
import {DEFAULT_API_BASE, normaliseBase} from './config';
import {createSessionClient, type SessionClient, type Snapshot} from './sessionClient';
import {colors, type as t, spacing} from './theme';
import type {CatalogueEntry} from './types';

/**
 * Screen flow: setup -> live -> summary.
 *
 * The TV opens the session so the pairing code exists before any camera joins,
 * and the summary is read from the same session rather than accumulated on the
 * device. Restarting the app does not lose a set, because the app was never the
 * thing holding the numbers.
 *
 * `fetchImpl` is a prop for the same reason the Python engine takes an injected
 * detector: the behaviour worth testing is the polling and the screen
 * transitions, and that should not require a camera, a server, or a television.
 */

export type Screen = 'setup' | 'live' | 'summary';

export interface AppProps {
  fetchImpl?: typeof fetch;
  initialApiBase?: string;
}

export const App = ({fetchImpl = globalThis.fetch, initialApiBase = DEFAULT_API_BASE}: AppProps) => {
  const [apiBase, setApiBase] = useState(normaliseBase(initialApiBase) ?? initialApiBase);
  const [exercises, setExercises] = useState<CatalogueEntry[]>([]);
  const [reachable, setReachable] = useState<boolean | null>(null);
  const [screen, setScreen] = useState<Screen>('setup');
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const clientRef = useRef<SessionClient | null>(null);

  const probe = useCallback(async () => {
    setReachable(null);
    setExercises([]);
    try {
      const health = await fetchImpl(`${apiBase}/health`);
      if (!health.ok) throw new Error(`health ${health.status}`);
      const rows = await fetchImpl(`${apiBase}/exercises`);
      if (!rows.ok) throw new Error(`exercises ${rows.status}`);
      setExercises((await rows.json()) as CatalogueEntry[]);
      setReachable(true);
      setError(null);
    } catch (err) {
      setReachable(false);
      setError(err instanceof Error ? err.message : String(err));
    }
  }, [apiBase, fetchImpl]);

  useEffect(() => {
    probe();
    return () => {
      clientRef.current?.stop();
      clientRef.current = null;
    };
  }, [probe]);

  const start = useCallback(
    async (exercise: string, view: 'side' | 'front') => {
      setBusy(true);
      setError(null);
      const client = createSessionClient({baseUrl: apiBase, fetchImpl});
      client.subscribe(setSnapshot);
      try {
        await client.start({exercise, view});
        clientRef.current = client;
        setScreen('live');
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setBusy(false);
      }
    },
    [apiBase, fetchImpl],
  );

  const finish = useCallback(async () => {
    const client = clientRef.current;
    if (!client?.sessionId) {
      setScreen('setup');
      return;
    }
    try {
      const response = await fetchImpl(`${apiBase}/session/${client.sessionId}/stop`, {method: 'POST'});
      setSummary(await response.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSummary(null);
    }
    await client.stop();
    clientRef.current = null;
    setScreen('summary');
  }, [apiBase, fetchImpl]);

  const backToSetup = useCallback(() => {
    setSummary(null);
    setSnapshot(null);
    setScreen('setup');
    probe();
  }, [probe]);

  if (screen === 'setup') {
    return (
      <Setup
        apiBase={apiBase}
        exercises={exercises}
        reachable={reachable}
        busy={busy}
        error={reachable === false ? `no API answering at ${apiBase}` : error}
        onApiBaseChange={(value) => {
          const clean = normaliseBase(value);
          if (clean) setApiBase(clean);
        }}
        onStart={start}
      />
    );
  }

  if (screen === 'summary') {
    return <Summary state={summary} apiBase={apiBase} onAgain={backToSetup} />;
  }

  return (
    <Hud
      model={snapshot?.viewModel ?? null}
      status={snapshot?.status ?? 'connecting'}
      ageMs={snapshot?.lastGoodAgeMs ?? null}
      sessionCode={snapshot?.sessionId ?? null}
      apiBase={apiBase}
      onFinish={finish}
    />
  );
};

export interface SummaryProps {
  state: Record<string, unknown> | null;
  apiBase: string;
  onAgain: () => void;
}

/**
 * Post-set totals, read back from the server rather than remembered on device.
 *
 * With no session data the screen says so instead of showing zeros: a summary
 * of nothing looks exactly like a summary of a bad set.
 */
export const Summary = ({state, apiBase, onAgain}: SummaryProps) => {
  const reps = Number(state?.reps ?? 0);
  const lines: Array<[string, string]> = state
    ? [
        ['REPS', String(reps)],
        ['DISCARDED', String(state.no_reps ?? 0)],
        ['ABANDONED', String(state.abandoned_arcs ?? 0)],
        ['MEAN FORM', state.mean_quality == null ? '\u2014' : `${Math.round(Number(state.mean_quality) * 100)}%`],
        ['CADENCE', state.cadence_upm == null ? '\u2014' : `${Math.round(Number(state.cadence_upm))} /min`],
        ['WEAK POINT', String(state.lowest_check ?? 'nothing flagged')],
        ['DEPTH TARGET', `${String(state.depth_threshold)} (${String(state.depth_threshold_source)})`],
      ]
    : [];

  return (
    <View style={styles.summaryRoot}>
      <Text style={styles.brand}>SET COMPLETE</Text>
      {state ? (
        <View style={styles.summaryGrid}>
          {lines.map(([label, value]) => (
            <View key={label} style={styles.summaryCell}>
              <Text style={styles.summaryLabel}>{label}</Text>
              <Text style={styles.summaryValue}>{value}</Text>
            </View>
          ))}
        </View>
      ) : (
        <Text style={styles.summaryEmpty}>
          No totals came back from {apiBase}. The set may still be on the server; this screen
          will not guess at it.
        </Text>
      )}
      <Text style={styles.summaryHint}>
        {state
          ? 'Every figure above was read back from the server, not remembered on the device.'
          : 'Re-run a set to read its totals again.'}
      </Text>
      <AgainButton onAgain={onAgain} />
    </View>
  );
};

/**
 * Focusable way back. A `Text` with an onPress is tappable on a phone and
 * unreachable with a D-pad, which is the entire input model here.
 */
export const AgainButton = ({onAgain}: {onAgain: () => void}) => {
  const [focused, setFocused] = useState(false);
  return (
    <Pressable
      onPress={onAgain}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      hasTVPreferredFocus
      accessibilityRole="button"
      accessibilityLabel="Run another set"
      testID="again"
      style={[styles.again, focused ? styles.againFocused : null]}>
      <Text style={styles.againText}>ANOTHER SET</Text>
    </Pressable>
  );
};

const styles = StyleSheet.create({
  summaryRoot: {
    flex: 1,
    backgroundColor: colors.bg,
    paddingHorizontal: spacing.gutter,
    paddingTop: 64,
  },
  brand: {...t.title, color: colors.focus, letterSpacing: 8},
  summaryGrid: {flexDirection: 'row', flexWrap: 'wrap', marginTop: 36, gap: 22},
  summaryCell: {
    width: 280,
    borderWidth: 1,
    borderColor: colors.panelEdge,
    borderRadius: 10,
    backgroundColor: colors.panel,
    padding: 20,
  },
  summaryLabel: {...t.label, color: colors.accent},
  summaryValue: {...t.value, color: colors.ink, marginTop: 8},
  summaryEmpty: {...t.body, color: colors.inkDim, marginTop: 30, maxWidth: 780},
  summaryHint: {...t.label, color: colors.inkFaint, marginTop: 40},
  again: {
    alignSelf: 'flex-start',
    marginTop: 22,
    borderWidth: 1,
    borderColor: colors.panelEdge,
    borderRadius: 6,
    paddingHorizontal: 30,
    paddingVertical: 14,
  },
  againFocused: {borderColor: colors.focus, backgroundColor: 'rgba(53,224,200,0.12)'},
  againText: {...t.label, color: colors.ink, letterSpacing: 3},
});
