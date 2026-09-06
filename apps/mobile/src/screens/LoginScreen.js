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

import { apiFetch } from '../api';
import { Banner, Button, TextField } from '../components/ui/primitives';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../hooks/use-theme';

const EXAMPLE_ROLES = ['clinician', 'marketing', 'admin', 'employee'];

/**
 * LoginScreen for AUTH_DEV_MODE login.
 * Calls POST /auth/dev-token to get a token (same as web app).
 */
export default function LoginScreen() {
  const theme = useTheme();
  const { login } = useAuth();
  const [role, setRole] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit() {
    const r = role.trim();
    if (!r) return;

    setLoading(true);
    setError(null);

    try {
      const data = await apiFetch('/auth/dev-token', {
        method: 'POST',
        body: { role: r },
      });

      if (!data?.token) {
        throw { status: 0, message: 'No token in response.', type: 'server' };
      }

      await login(data.token, r);
    } catch (err) {
      // err is an ApiError: { status, message, type, body }
      if (err.status === 404) {
        setError(
          'Dev token issuance is disabled on this server. ' +
            'Set AUTH_DEV_MODE=true on the backend and redeploy to enable it.'
        );
      } else {
        setError(err.message || 'Login failed — check the backend is running.');
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: theme.background }]}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.keyboardView}
      >
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
        >
          <View style={styles.content}>
            <Text style={[styles.brand, { color: theme.text }]}>ContextGuard</Text>
            <Text style={[styles.title, { color: theme.textSecondary }]}>Sign in</Text>
            <View style={[styles.rule, { backgroundColor: theme.border }]} />

            <View style={styles.form}>
              <TextField
                label="Role"
                value={role}
                onChangeText={setRole}
                placeholder="e.g. clinician, marketing, admin…"
                autoCapitalize="none"
                autoCorrect={false}
                autoComplete="off"
                autoFocus
                style={styles.field}
              />

              <View style={styles.chipRow}>
                {EXAMPLE_ROLES.map((r) => (
                  <TouchableOpacity
                    key={r}
                    style={[
                      styles.chip,
                      { backgroundColor: theme.backgroundElement, borderColor: theme.border },
                    ]}
                    onPress={() => setRole(r)}
                    accessibilityLabel={`Set role to ${r}`}
                  >
                    <Text style={[styles.chipText, { color: theme.text }]}>{r}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              {error && <Banner tone="error" title="Sign-in failed" message={error} />}

              <View style={styles.spacer} />

              <Button
                title="Continue"
                onPress={handleSubmit}
                loading={loading}
                disabled={!role.trim()}
              />

              <Text style={[styles.footnote, { color: theme.textSecondary }]}>
                Dev-mode JWT via POST /auth/dev-token. Token persists on-device. Role is embedded in
                the JWT for policy enforcement.
              </Text>
            </View>
          </View>
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
  scrollContent: {
    flexGrow: 1,
  },
  content: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 24,
    paddingVertical: 40,
  },
  brand: {
    fontSize: 28,
    fontWeight: '700',
    marginBottom: 8,
    textAlign: 'center',
  },
  title: {
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 16,
    textAlign: 'center',
  },
  rule: {
    height: 1,
    marginBottom: 32,
  },
  form: {
    width: '100%',
    gap: 16,
  },
  field: {
    marginBottom: 0,
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  chip: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 16,
    borderWidth: 1,
  },
  chipText: {
    fontSize: 14,
    fontWeight: '500',
  },
  spacer: {
    height: 4,
  },
  footnote: {
    fontSize: 12,
    lineHeight: 18,
    textAlign: 'center',
  },
});
