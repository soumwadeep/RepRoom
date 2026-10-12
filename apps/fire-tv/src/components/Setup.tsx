import React, {useMemo, useState} from 'react';
import {Pressable, ScrollView, StyleSheet, Text, View} from 'react-native';

import {normaliseBase} from '../config';
import {colors, type as t, spacing} from '../theme';
import type {CatalogueEntry} from '../types';

/**
 * Setup: point the TV at the API, choose the exercise, get a pairing code.
 *
 * The TV owns the session and the camera joins it, because the television is
 * the thing everybody is looking at. Once started, the screen shows a session
 * code and the address to open on the phone -- the pairing step has to be
 * visible on the big screen or the person on the couch cannot explain what is
 * happening to anyone else in the room.
 *
 * The address is entered with a keypad rather than a keyboard because Vega has
 * no text input that a remote can drive comfortably.
 */

const KEYS = [
  ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0'],
  ['.', ':', '/', 'h', 't', 'p', 's', 'B', 'C', 'E'],
];

export interface SetupProps {
  apiBase: string;
  exercises: CatalogueEntry[];
  reachable: boolean | null;
  busy: boolean;
  error: string | null;
  onApiBaseChange: (value: string) => void;
  onStart: (exercise: string, view: 'side' | 'front') => void;
}

export const Setup = ({
  apiBase,
  exercises,
  reachable,
  busy,
  error,
  onApiBaseChange,
  onStart,
}: SetupProps) => {
  const [draft, setDraft] = useState(apiBase);
  const [selected, setSelected] = useState<string | null>(exercises[0]?.key ?? null);
  const [focusedTile, setFocusedTile] = useState<string | null>(null);

  const valid = useMemo(() => normaliseBase(draft) !== null, [draft]);
  const entry = exercises.find((e) => e.key === selected);

  const press = (key: string) => {
    if (key === 'B') {
      setDraft((value) => value.slice(0, -1));
      return;
    }
    if (key === 'C') {
      setDraft('');
      return;
    }
    if (key === 'E') {
      onApiBaseChange(normaliseBase(draft) ?? draft);
      return;
    }
    setDraft((value) => value + key);
  };

  return (
    <View style={styles.root}>
      <Text style={styles.brand}>REPROOM</Text>
      <Text style={styles.subtitle}>CAMERA-COACHED REPS ON THE BIG SCREEN</Text>

      <View style={styles.columns}>
        <View style={styles.left}>
          <Text style={styles.section}>SESSION API ADDRESS</Text>
          <View style={styles.draftBox}>
            <Text style={styles.draft} testID="api-draft">
              {draft.length ? draft : 'type an address'}
            </Text>
          </View>
          {KEYS.map((row, rowIndex) => (
            <View key={rowIndex} style={styles.keyRow}>
              {row.map((key) => (
                <KeyButton
                  key={`${rowIndex}-${key}`}
                  label={key}
                  onPress={() => press(key)}
                />
              ))}
            </View>
          ))}
          <Text style={[styles.hint, valid ? styles.hintOk : styles.hintBad]}>
            {valid
              ? `E commits. API ${reachable === null ? 'unknown' : reachable ? 'reachable' : 'unreachable'}`
              : 'not a valid host or URL'}
          </Text>
        </View>

        <View style={styles.right}>
          <Text style={styles.section}>CHOOSE AN EXERCISE</Text>
          <ScrollView style={styles.picker} showsVerticalScrollIndicator={false}>
            {exercises.length === 0 ? (
              <Text style={styles.hint}>
                The API is not answering, so there is nothing to choose. Fix the
                address above first.
              </Text>
            ) : null}
            {exercises.map((item, index) => (
              <Pressable
                key={item.key}
                onPress={() => {
                  setSelected(item.key);
                  onStart(item.key, item.view);
                }}
                onFocus={() => {
                  setSelected(item.key);
                  setFocusedTile(item.key);
                }}
                onBlur={() => setFocusedTile(null)}
                accessibilityRole="button"
                accessibilityLabel={`Start ${item.name}`}
                hasTVPreferredFocus={index === 0}
                style={[
                  styles.tile,
                  focusedTile === item.key ? styles.tileFocused : null,
                  selected === item.key && focusedTile !== item.key ? styles.tileSelected : null,
                ]}>
                <Text style={styles.tileName}>{item.name.toUpperCase()}</Text>
                <Text style={styles.tileMeta}>
                  {item.view} camera · {item.focus}
                </Text>
                <Text style={styles.tileChecks}>{item.checks.join(' · ')}</Text>
              </Pressable>
            ))}
          </ScrollView>
          {error ? <Text style={styles.error}>{error}</Text> : null}
          {busy ? <Text style={styles.hint}>opening session…</Text> : null}
          {entry && !busy ? (
            <Text style={styles.hint}>
              Press select to start. The camera page joins with the code this screen shows.
            </Text>
          ) : null}
        </View>
      </View>
    </View>
  );
};

/**
 * One keypad key.
 *
 * Focus is tracked locally because Vega's Pressable state callback exposes
 * `pressed` but not `focused`, and a television cannot point at anything else:
 * without a visible focus ring on this screen the address is impossible to
 * enter. That is the only reason this component exists.
 */
export const KeyButton = ({label, onPress}: {label: string; onPress: () => void}) => {
  const [focused, setFocused] = useState(false);
  const spoken =
    label === 'B'
      ? 'backspace'
      : label === 'C'
      ? 'clear'
      : label === 'E'
      ? 'use this address'
      : label;
  return (
    <Pressable
      onPress={onPress}
      onFocus={() => setFocused(true)}
      onBlur={() => setFocused(false)}
      accessibilityRole="button"
      accessibilityLabel={spoken}
      style={[styles.key, focused ? styles.keyFocused : null]}>
      <Text style={styles.keyText}>{label}</Text>
    </Pressable>
  );
};

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: colors.bg,
    paddingHorizontal: spacing.gutter,
    paddingTop: 48,
  },
  brand: {...t.title, color: colors.focus, letterSpacing: 10},
  subtitle: {...t.label, color: colors.inkFaint, marginTop: 4},
  columns: {flexDirection: 'row', flex: 1, marginTop: 32, gap: 48},
  left: {flex: 1},
  right: {flex: 1.1},
  section: {...t.label, color: colors.accent, marginBottom: 12},
  draftBox: {
    height: 74,
    borderWidth: 1,
    borderColor: colors.panelEdge,
    borderRadius: 8,
    backgroundColor: colors.panel,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 14,
  },
  draft: {...t.value, color: colors.ink},
  keyRow: {flexDirection: 'row', gap: 8, marginBottom: 8},
  key: {
    width: 62,
    height: 62,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: colors.panelEdge,
    backgroundColor: colors.panel,
    alignItems: 'center',
    justifyContent: 'center',
  },
  keyFocused: {borderColor: colors.focus, backgroundColor: 'rgba(53,224,200,0.14)'},
  keyText: {...t.value, color: colors.ink},
  hint: {...t.label, color: colors.inkFaint, marginTop: 10},
  hintOk: {color: colors.good},
  hintBad: {color: colors.warn},
  error: {...t.label, color: colors.bad, marginTop: 10},
  picker: {maxHeight: 420},
  tile: {
    borderWidth: 1,
    borderColor: colors.panelEdge,
    borderRadius: 10,
    backgroundColor: colors.panel,
    padding: 18,
    marginBottom: 12,
  },
  tileSelected: {borderColor: colors.inkFaint},
  tileFocused: {
    borderColor: colors.focus,
    backgroundColor: 'rgba(53,224,200,0.10)',
    transform: [{scale: 1.01}],
  },
  tileName: {...t.body, color: colors.ink, fontWeight: '700'},
  tileMeta: {...t.label, color: colors.inkDim, marginTop: 6},
  tileChecks: {...t.label, color: colors.inkFaint, marginTop: 4},
});
