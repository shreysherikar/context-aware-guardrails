import * as ImagePicker from 'expo-image-picker';
import { File } from 'expo-file-system';
import { Image } from 'expo-image';
import { useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { apiFetch } from '../api';
import ResultCard from '../components/ResultCard';
import { Banner, Button, Card } from '../components/ui/primitives';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../hooks/use-theme';

// Keep these in sync with the backend's actual accepted types/size limit -
// see services/optical_guardrail/validation.py in the main repo.
const MAX_BYTES = 10 * 1024 * 1024; // 10MB
const ACCEPTED_MIME = ['image/png', 'image/jpeg', 'image/webp'];

function makeConvoId() {
  return `convo-img-${Date.now()}`;
}

function guessMimeType(uri) {
  const ext = uri.split('.').pop()?.toLowerCase();
  if (ext === 'png') return 'image/png';
  if (ext === 'webp') return 'image/webp';
  return 'image/jpeg';
}

/**
 * ImageEvaluateScreen — Phase 8. Uses expo-image-picker (no <input type="file">
 * equivalent exists in RN) and POSTs multipart/form-data to
 * /guardrail/evaluate-image, matching the web app's validation limits.
 */
export default function ImageEvaluateScreen() {
  const theme = useTheme();
  const { auth } = useAuth();
  const [asset, setAsset] = useState(null);
  const [convId, setConvId] = useState(makeConvoId);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  async function handlePickImage() {
    setError(null);
    setResult(null);

    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setError('Photo library access is required to pick an image.');
      return;
    }

    const pickerResult = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 1,
    });

    if (pickerResult.canceled || !pickerResult.assets?.length) return;

    const picked = pickerResult.assets[0];
    const mimeType = picked.mimeType || guessMimeType(picked.uri);

    if (!ACCEPTED_MIME.includes(mimeType)) {
      setError(`Unsupported image type (${mimeType}). Use PNG, JPEG, or WEBP.`);
      return;
    }
    if (picked.fileSize && picked.fileSize > MAX_BYTES) {
      setError('Image is larger than the 10MB limit.');
      return;
    }

    setAsset({ ...picked, mimeType });
  }

  async function handleSubmit() {
    if (!auth || !asset) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const formData = new FormData();
      const file = new File(asset.uri);

      formData.append('image', file);
      formData.append('conversation_id', convId);

      const data = await apiFetch('/guardrail/evaluate-image', {
        method: 'POST',
        body: formData,
        token: auth.token,
      });

      setResult(data);
    } catch (err) {
      if (err.type === 'unavailable' && err.body) {
        setResult(err.body);
        setError(`Generation temporarily unavailable: ${err.message}`);
      } else {
        setError(err.message || 'Request failed.');
      }
    } finally {
      setLoading(false);
    }
  }

  function handleReset() {
    setAsset(null);
    setResult(null);
    setError(null);
    setConvId(makeConvoId());
  }

  return (
    <View style={styles.content}>
      <Text style={[styles.helperText, { color: theme.textSecondary }]}>
        Pick an image to evaluate through POST /guardrail/evaluate-image. PNG, JPEG, or WEBP, up to
        10MB.
      </Text>

      {asset ? (
        <Card style={styles.previewCard}>
          <Image source={{ uri: asset.uri }} style={styles.preview} contentFit="cover" />
          <Button title="Choose a different image" onPress={handlePickImage} variant="secondary" />
        </Card>
      ) : (
        <Button title="Choose an image" onPress={handlePickImage} variant="secondary" />
      )}

      {error && !result && <Banner tone="error" title="Error" message={error} />}
      {error && result && <Banner tone="warning" title="Warning" message={error} />}

      <Button title="Evaluate image" onPress={handleSubmit} loading={loading} disabled={!asset} />

      {(asset || result) && <Button title="Start over" onPress={handleReset} variant="secondary" />}

      {result && (
        <Card style={styles.resultCard}>
          <Text style={[styles.resultTitle, { color: theme.text }]}>Evaluation result</Text>
          <ResultCard data={result} />
        </Card>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  content: {
    gap: 16,
  },
  helperText: {
    fontSize: 13,
    lineHeight: 18,
  },
  previewCard: {
    gap: 12,
    alignItems: 'stretch',
  },
  preview: {
    width: '100%',
    aspectRatio: 4 / 3,
    borderRadius: 10,
  },
  resultCard: {
    marginTop: 4,
    gap: 8,
  },
  resultTitle: {
    fontSize: 18,
    fontWeight: '700',
    marginBottom: 8,
  },
});
