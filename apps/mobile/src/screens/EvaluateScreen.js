import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';

import ScreenHeader from '../components/ui/ScreenHeader';
import { useTheme } from '../hooks/use-theme';
import ImageEvaluateScreen from './ImageEvaluateScreen';
import TextEvaluateScreen from './TextEvaluateScreen';

const MODES = [
  { key: 'text', label: 'Text', endpoint: '/guardrail/evaluate' },
  { key: 'image', label: 'Image', endpoint: '/guardrail/evaluate-image' },
];

/**
 * Container for the Evaluate tab. Holds the Text/Image mode toggle and the
 * shared scroll/keyboard scaffolding; TextEvaluateScreen and
 * ImageEvaluateScreen each own their own request + result state so switching
 * modes doesn't require lifting state up.
 */
export default function EvaluateScreen() {
  const theme = useTheme();
  const [mode, setMode] = useState('text');
  const active = MODES.find((m) => m.key === mode);

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: theme.background }]}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.keyboardView}
        keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
      >
        <ScrollView
          style={styles.scrollView}
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
        >
          <ScreenHeader
            title="Evaluate"
            subtitle={`Send a request through the full guardrail pipeline via POST ${active.endpoint}`}
          />

          <View
            style={[
              styles.toggleRow,
              { backgroundColor: theme.backgroundElement, borderColor: theme.border },
            ]}
          >
            {MODES.map((m) => {
              const isActive = m.key === mode;
              return (
                <TouchableOpacity
                  key={m.key}
                  style={[
                    styles.toggleButton,
                    isActive && { backgroundColor: theme.backgroundSelected },
                  ]}
                  onPress={() => setMode(m.key)}
                  accessibilityLabel={`Switch to ${m.label} evaluate`}
                  accessibilityState={{ selected: isActive }}
                >
                  <Text
                    style={[
                      styles.toggleLabel,
                      { color: isActive ? theme.text : theme.textSecondary },
                    ]}
                  >
                    {m.label}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>

          {mode === 'text' ? <TextEvaluateScreen /> : <ImageEvaluateScreen />}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  keyboardView: {
    flex: 1,
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    padding: 16,
  },
  toggleRow: {
    flexDirection: 'row',
    borderRadius: 10,
    borderWidth: 1,
    padding: 4,
    marginBottom: 20,
    gap: 4,
  },
  toggleButton: {
    flex: 1,
    paddingVertical: 8,
    borderRadius: 8,
    alignItems: 'center',
  },
  toggleLabel: {
    fontSize: 14,
    fontWeight: '600',
  },
});
