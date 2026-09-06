import { StyleSheet, Text, View } from 'react-native';

import { useTheme } from '../hooks/use-theme';
import {
  extractAction,
  extractGeneratedResponse,
  extractReason,
  getDecisionMeta,
} from '../lib/decision';
import Badge from './ui/Badge';

/**
 * Displays a /guardrail/evaluate (or /guardrail/evaluate-image) result:
 * decision badge, reason, and the generated response when one is present.
 */
export default function ResultCard({ data }) {
  const theme = useTheme();
  if (!data) return null;

  const { label, colors } = getDecisionMeta(extractAction(data));
  const reason = extractReason(data);
  const llmResponse = extractGeneratedResponse(data);

  return (
    <View style={styles.container}>
      <Badge label={label} colors={colors} />

      <View style={styles.section}>
        <Text style={[styles.sectionLabel, { color: theme.textSecondary }]}>Reason</Text>
        <Text style={[styles.reasonText, { color: theme.text }]}>{reason}</Text>
      </View>

      {llmResponse && (
        <View style={styles.section}>
          <Text style={[styles.sectionLabel, { color: theme.textSecondary }]}>
            Generated response
          </Text>
          <View
            style={[
              styles.responseBox,
              { backgroundColor: theme.backgroundElement, borderColor: theme.border },
            ]}
          >
            <Text style={[styles.responseText, { color: theme.text }]}>{llmResponse}</Text>
          </View>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    gap: 16,
  },
  section: {
    gap: 8,
  },
  sectionLabel: {
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  reasonText: {
    fontSize: 15,
    lineHeight: 22,
  },
  responseBox: {
    padding: 14,
    borderRadius: 10,
    borderWidth: 1,
  },
  responseText: {
    fontSize: 15,
    lineHeight: 22,
  },
});
