import { useCallback, useEffect, useState } from 'react';
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  RefreshControl,
  SafeAreaView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { apiFetch } from '../api';
import Badge from '../components/ui/Badge';
import { Banner } from '../components/ui/primitives';
import ScreenHeader from '../components/ui/ScreenHeader';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../hooks/use-theme';
import { extractAction, getDecisionMeta } from '../lib/decision';

function truncateId(id) {
  if (!id) return '—';
  return id.length > 14 ? `${id.slice(0, 8)}…${id.slice(-4)}` : id;
}

function formatTimestamp(ts) {
  if (!ts) return '—';
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return String(ts);
  return date.toLocaleString();
}

function EventRow({ event }) {
  const theme = useTheme();
  const { label, colors } = getDecisionMeta(extractAction(event));

  return (
    <View style={[styles.row, { backgroundColor: theme.surfaceRaised, borderColor: theme.border }]}>
      <View style={styles.rowTop}>
        <Text style={[styles.timestamp, { color: theme.textSecondary }]}>
          {formatTimestamp(event.timestamp || event.created_at)}
        </Text>
        <Badge label={label} colors={colors} size="small" />
      </View>
      <View style={styles.rowMeta}>
        <Text style={[styles.metaText, { color: theme.text }]}>
          conv: <Text style={styles.metaValue}>{truncateId(event.conversation_id)}</Text>
        </Text>
        <Text style={[styles.metaText, { color: theme.text }]}>
          role: <Text style={styles.metaValue}>{event.role || event.user_role || '—'}</Text>
        </Text>
      </View>
      {event.prompt ? (
        <Text style={[styles.promptText, { color: theme.textSecondary }]} numberOfLines={2}>
          {event.prompt}
        </Text>
      ) : null}
    </View>
  );
}

/**
 * AuditLogScreen — Phase 7. GET /audit/events, rendered with FlatList (not a
 * raw .map()/ScrollView — required for performant list rendering in RN).
 * Prompts may come back redacted for REWRITE-outcome events; that's expected
 * backend privacy-preserving behavior, not a bug.
 */
export default function AuditLogScreen() {
  const theme = useTheme();
  const { auth } = useAuth();
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);

  const fetchEvents = useCallback(async () => {
    if (!auth) return;
    setError(null);
    try {
      const data = await apiFetch('/audit/events?limit=50', { token: auth.token });
      setEvents(Array.isArray(data) ? data : data?.events || []);
    } catch (err) {
      setError(err.message || 'Failed to load audit events.');
    }
  }, [auth]);

  useEffect(() => {
    // Standard fetch-on-mount pattern; the eslint-plugin-react-hooks
    // set-state-in-effect rule flags any setState from an effect's async
    // completion callback, including ordinary data fetching like this.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchEvents().finally(() => setLoading(false));
  }, [fetchEvents]);

  async function handleRefresh() {
    setRefreshing(true);
    await fetchEvents();
    setRefreshing(false);
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: theme.background }]}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.flex}
      >
        <View style={styles.headerWrap}>
          <ScreenHeader
            title="Audit Log"
            subtitle="Recent guardrail decisions via GET /audit/events"
          />
        </View>

        {error && (
          <View style={styles.headerWrap}>
            <Banner tone="error" title="Couldn't load audit events" message={error} />
          </View>
        )}

        <FlatList
          data={events}
          keyExtractor={(item, index) =>
            item.id?.toString() || item.event_id?.toString() || String(index)
          }
          renderItem={({ item }) => <EventRow event={item} />}
          contentContainerStyle={styles.listContent}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />}
          ItemSeparatorComponent={() => <View style={styles.separator} />}
          ListEmptyComponent={
            !loading ? (
              <Text style={[styles.emptyText, { color: theme.textSecondary }]}>
                No audit events yet. Evaluate a prompt or image to see it appear here.
              </Text>
            ) : null
          }
        />
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  flex: {
    flex: 1,
  },
  headerWrap: {
    paddingHorizontal: 16,
    paddingTop: 16,
  },
  listContent: {
    paddingHorizontal: 16,
    paddingBottom: 24,
    flexGrow: 1,
  },
  separator: {
    height: 10,
  },
  row: {
    borderRadius: 12,
    borderWidth: 1,
    padding: 14,
    gap: 8,
  },
  rowTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  timestamp: {
    fontSize: 12,
  },
  rowMeta: {
    flexDirection: 'row',
    gap: 16,
  },
  metaText: {
    fontSize: 13,
  },
  metaValue: {
    fontWeight: '600',
  },
  promptText: {
    fontSize: 13,
    lineHeight: 18,
    fontStyle: 'italic',
  },
  emptyText: {
    fontSize: 14,
    textAlign: 'center',
    marginTop: 40,
    paddingHorizontal: 24,
    lineHeight: 20,
  },
});
