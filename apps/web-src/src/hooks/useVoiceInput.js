import { useCallback, useEffect, useRef, useState } from 'react';

function getSpeechRecognition() {
  if (typeof window === 'undefined') return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

export function isVoiceInputSupported() {
  return Boolean(getSpeechRecognition());
}

export default function useVoiceInput({ onTranscript, onError, disabled = false } = {}) {
  const [listening, setListening] = useState(false);
  const [supported] = useState(() => isVoiceInputSupported());
  const recognitionRef = useRef(null);
  const baseTextRef = useRef('');
  const finalTextRef = useRef('');
  const onTranscriptRef = useRef(onTranscript);
  const onErrorRef = useRef(onError);

  useEffect(() => {
    onTranscriptRef.current = onTranscript;
    onErrorRef.current = onError;
  }, [onTranscript, onError]);

  const stop = useCallback(() => {
    try {
      recognitionRef.current?.stop();
    } catch {
      /* already stopped */
    }
    recognitionRef.current = null;
    setListening(false);
  }, []);

  useEffect(() => {
    if (disabled) stop();
  }, [disabled, stop]);

  useEffect(() => () => {
    try {
      recognitionRef.current?.abort();
    } catch {
      /* ignore */
    }
  }, []);

  const toggle = useCallback((currentValue = '') => {
    const SpeechRecognition = getSpeechRecognition();
    if (!SpeechRecognition) {
      onErrorRef.current?.('Voice input is not supported in this browser. Try Chrome or Edge.');
      return;
    }

    if (recognitionRef.current) {
      stop();
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.lang = navigator.language || 'en-US';

    baseTextRef.current = currentValue || '';
    finalTextRef.current = '';

    recognition.onresult = (event) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const piece = event.results[i][0]?.transcript || '';
        if (event.results[i].isFinal) {
          finalTextRef.current = `${finalTextRef.current} ${piece}`.replace(/\s+/g, ' ').trim();
        } else {
          interim += piece;
        }
      }
      const prefix = baseTextRef.current.trim();
      const spoken = `${finalTextRef.current} ${interim}`.replace(/\s+/g, ' ').trim();
      const next = [prefix, spoken].filter(Boolean).join(prefix && spoken ? ' ' : '');
      onTranscriptRef.current?.(next);
    };

    recognition.onerror = (event) => {
      if (event.error === 'aborted' || event.error === 'no-speech') return;
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        onErrorRef.current?.('Microphone access was blocked. Allow it in the browser and try again.');
      } else {
        onErrorRef.current?.('Voice input failed. Check your microphone and try again.');
      }
      recognitionRef.current = null;
      setListening(false);
    };

    recognition.onend = () => {
      recognitionRef.current = null;
      setListening(false);
    };

    recognitionRef.current = recognition;
    try {
      recognition.start();
      setListening(true);
    } catch {
      recognitionRef.current = null;
      setListening(false);
      onErrorRef.current?.('Could not start the microphone.');
    }
  }, [stop]);

  return { listening, supported, toggle, stop };
}
