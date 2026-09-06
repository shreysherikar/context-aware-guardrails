import { StyleSheet, Text, View } from 'react-native';

/**
 * Renders a decision badge (ALLOW/REWRITE/CLARIFY/REVIEW/BLOCK) with the
 * colors resolved by src/lib/decision.js's getDecisionMeta.
 */
export default function Badge({ label, colors, size = 'medium' }) {
  return (
    <View
      style={[
        styles.badge,
        size === 'small' && styles.badgeSmall,
        { backgroundColor: colors.bg, borderColor: colors.border },
      ]}
    >
      <Text
        style={[styles.text, size === 'small' && styles.textSmall, { color: colors.fg }]}
        numberOfLines={1}
      >
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    alignSelf: 'flex-start',
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 999,
    borderWidth: 1.5,
  },
  badgeSmall: {
    paddingHorizontal: 10,
    paddingVertical: 3,
  },
  text: {
    fontSize: 14,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  textSmall: {
    fontSize: 11,
  },
});
