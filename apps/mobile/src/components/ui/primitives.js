import { forwardRef } from 'react';
import {
  ActivityIndicator,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';

import { Spacing } from '../../constants/theme';
import { useTheme } from '../../hooks/use-theme';

/** A rounded, bordered surface used for cards/sections throughout the app. */
export function Card({ style, children }) {
  const theme = useTheme();
  return (
    <View
      style={[
        styles.card,
        { backgroundColor: theme.surfaceRaised, borderColor: theme.border },
        style,
      ]}
    >
      {children}
    </View>
  );
}

/** Primary/secondary/danger button with a built-in loading + disabled state. */
export function Button({
  title,
  onPress,
  loading = false,
  disabled = false,
  variant = 'primary',
  accessibilityLabel,
}) {
  const theme = useTheme();
  const isDisabled = disabled || loading;

  const variantStyle =
    variant === 'primary'
      ? { backgroundColor: isDisabled ? theme.backgroundSelected : theme.brand }
      : variant === 'danger'
        ? { backgroundColor: 'transparent', borderWidth: 1, borderColor: theme.danger }
        : { backgroundColor: 'transparent', borderWidth: 1, borderColor: theme.border };

  const textColor =
    variant === 'primary'
      ? isDisabled
        ? theme.textSecondary
        : theme.brandText
      : variant === 'danger'
        ? theme.danger
        : theme.text;

  return (
    <TouchableOpacity
      style={[styles.button, variantStyle]}
      onPress={onPress}
      disabled={isDisabled}
      accessibilityLabel={accessibilityLabel || title}
      accessibilityState={{ busy: loading, disabled: isDisabled }}
    >
      {loading ? (
        <ActivityIndicator color={textColor} />
      ) : (
        <Text style={[styles.buttonText, { color: textColor }]}>{title}</Text>
      )}
    </TouchableOpacity>
  );
}

/** Labelled text input matching the app's field styling. Forwards its ref to the underlying TextInput. */
export const TextField = forwardRef(function TextField(
  { label, style, inputStyle, ...inputProps },
  ref
) {
  const theme = useTheme();
  return (
    <View style={style}>
      {label ? <Text style={[styles.label, { color: theme.textSecondary }]}>{label}</Text> : null}
      <TextInput
        ref={ref}
        style={[
          styles.input,
          {
            borderColor: theme.border,
            color: theme.text,
            backgroundColor: theme.backgroundElement,
          },
          inputStyle,
        ]}
        placeholderTextColor={theme.textSecondary}
        {...inputProps}
      />
    </View>
  );
});

/** Inline status banner (error / warning / info) with a semantic color. */
export function Banner({ tone = 'info', title, message }) {
  const palette = {
    info: { bg: '#E5EEFD', border: '#4B86EE', fg: '#1D5FC2' },
    warning: { bg: '#FDF0DD', border: '#E79A2E', fg: '#B5680A' },
    error: { bg: '#FBE1E1', border: '#E14A50', fg: '#B4222A' },
  }[tone];

  return (
    <View style={[styles.banner, { backgroundColor: palette.bg, borderColor: palette.border }]}>
      {title ? <Text style={[styles.bannerTitle, { color: palette.fg }]}>{title}</Text> : null}
      {message ? <Text style={[styles.bannerText, { color: palette.fg }]}>{message}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: 14,
    borderWidth: 1,
    padding: Spacing.three,
  },
  button: {
    height: 50,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
  },
  buttonText: {
    fontSize: 16,
    fontWeight: '600',
  },
  label: {
    fontSize: 13,
    fontWeight: '600',
    marginBottom: Spacing.two,
    textTransform: 'uppercase',
    letterSpacing: 0.3,
  },
  input: {
    height: 46,
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: Spacing.three,
    fontSize: 15,
  },
  banner: {
    borderRadius: 10,
    borderWidth: 1,
    padding: Spacing.three,
    gap: 4,
  },
  bannerTitle: {
    fontSize: 13,
    fontWeight: '700',
  },
  bannerText: {
    fontSize: 13,
    lineHeight: 18,
  },
});
