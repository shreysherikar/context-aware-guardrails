import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../hooks/use-theme';

/** Consistent header used at the top of every authenticated screen. */
export default function ScreenHeader({ title, subtitle }) {
  const theme = useTheme();
  const { logout } = useAuth();

  return (
    <View style={styles.headerTop}>
      <View style={styles.headerText}>
        <Text style={[styles.title, { color: theme.text }]}>{title}</Text>
        {subtitle ? (
          <Text style={[styles.subtitle, { color: theme.textSecondary }]}>{subtitle}</Text>
        ) : null}
      </View>
      <TouchableOpacity
        style={[
          styles.logoutButton,
          { backgroundColor: theme.backgroundElement, borderColor: theme.border },
        ]}
        onPress={logout}
        accessibilityLabel="Log out"
      >
        <Text style={[styles.logoutButtonText, { color: theme.textSecondary }]}>Log out</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  headerTop: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    gap: 12,
    marginBottom: 24,
  },
  headerText: {
    flex: 1,
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
    marginBottom: 6,
  },
  subtitle: {
    fontSize: 14,
    lineHeight: 20,
  },
  logoutButton: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    borderWidth: 1,
  },
  logoutButtonText: {
    fontSize: 13,
    fontWeight: '600',
  },
});
