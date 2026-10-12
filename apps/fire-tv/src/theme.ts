/**
 * HUD theme.
 *
 * Sized for a 10-foot viewing distance: the rep count is the only thing that
 * must be legible from the far end of the sofa, and status is carried by colour
 * before it is carried by words. Every tone maps to a meaning that has a
 * matching word on screen, so colour is never the only channel -- a muted grey
 * dash always arrives with "not measurable" in prose.
 */

export const colors = {
  ink: '#E8F5FF',
  inkDim: '#7F9BB3',
  inkFaint: '#42586B',
  bg: '#04070D',
  panel: '#0A1420',
  panelEdge: '#16324A',
  focus: '#35E0C8',
  good: '#3BE08E',
  warn: '#FFB347',
  bad: '#FF6B6B',
  muted: '#5A7185',
  accent: '#1E88FF',
};

export const tones: Record<string, string> = {
  good: colors.good,
  warn: colors.warn,
  bad: colors.bad,
  muted: colors.muted,
};

export const type = {
  hero: {fontSize: 190, lineHeight: 200, fontWeight: '700' as const},
  heroUnit: {fontSize: 26, lineHeight: 34, letterSpacing: 6} as const,
  title: {fontSize: 34, lineHeight: 42, fontWeight: '600' as const},
  body: {fontSize: 22, lineHeight: 30} as const,
  label: {fontSize: 13, lineHeight: 18, letterSpacing: 3} as const,
  value: {fontSize: 30, lineHeight: 36, fontWeight: '600' as const} as const,
};

export const spacing = {
  gutter: 56,
  band: 24,
  cell: 18,
};
