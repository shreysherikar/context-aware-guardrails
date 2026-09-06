/**
 * Below are the colors that are used in the app. The colors are defined in the light and dark mode.
 * There are many other ways to style your app. For example, [Nativewind](https://www.nativewind.dev/), [Tamagui](https://tamagui.dev/), [unistyles](https://reactnativeunistyles.vercel.app), etc.
 */

import '@/global.css';

import { Platform } from 'react-native';

export const Colors = {
  light: {
    text: '#0B0D12',
    background: '#F7F8FA',
    backgroundElement: '#FFFFFF',
    backgroundSelected: '#E8ECF3',
    textSecondary: '#5B6270',
    border: '#E2E5EA',
    brand: '#2F6FED',
    brandText: '#FFFFFF',
    danger: '#D64545',
    surfaceRaised: '#FFFFFF',
  },
  dark: {
    text: '#F4F6FA',
    background: '#0B0D12',
    backgroundElement: '#161A22',
    backgroundSelected: '#232838',
    textSecondary: '#9AA2B1',
    border: '#242A36',
    brand: '#5B8DEF',
    brandText: '#0B0D12',
    danger: '#F2837A',
    surfaceRaised: '#1B2029',
  },
} as const;

/**
 * Guardrail decision colors. Intentionally NOT theme-split (light/dark) beyond
 * a single "on" foreground — these are semantic status colors (ALLOW/BLOCK/etc)
 * and must stay recognizable in both color schemes, unlike neutral UI chrome.
 */
export const DecisionColors = {
  ALLOW: { fg: '#1B7F3A', bg: '#E3F6E9', border: '#39B36B' },
  REWRITE: { fg: '#1D5FC2', bg: '#E5EEFD', border: '#4B86EE' },
  CLARIFY: { fg: '#B5680A', bg: '#FDF0DD', border: '#E79A2E' },
  REVIEW: { fg: '#B0400F', bg: '#FCE7DC', border: '#E56B33' },
  BLOCK: { fg: '#B4222A', bg: '#FBE1E1', border: '#E14A50' },
  UNKNOWN: { fg: '#565D6B', bg: '#EEF0F3', border: '#9AA2B1' },
} as const;

export type ThemeColor = keyof typeof Colors.light & keyof typeof Colors.dark;

export const Fonts = Platform.select({
  ios: {
    /** iOS `UIFontDescriptorSystemDesignDefault` */
    sans: 'system-ui',
    /** iOS `UIFontDescriptorSystemDesignSerif` */
    serif: 'ui-serif',
    /** iOS `UIFontDescriptorSystemDesignRounded` */
    rounded: 'ui-rounded',
    /** iOS `UIFontDescriptorSystemDesignMonospaced` */
    mono: 'ui-monospace',
  },
  default: {
    sans: 'normal',
    serif: 'serif',
    rounded: 'normal',
    mono: 'monospace',
  },
  web: {
    sans: 'var(--font-display)',
    serif: 'var(--font-serif)',
    rounded: 'var(--font-rounded)',
    mono: 'var(--font-mono)',
  },
});

export const Spacing = {
  half: 2,
  one: 4,
  two: 8,
  three: 16,
  four: 24,
  five: 32,
  six: 64,
} as const;

export const BottomTabInset = Platform.select({ ios: 50, android: 80 }) ?? 0;
export const MaxContentWidth = 800;
