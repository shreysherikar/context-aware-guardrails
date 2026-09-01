import { useEffect } from 'react';
import { Mic, MicOff } from 'lucide-react';
import useVoiceInput from '../hooks/useVoiceInput';
import './VoiceInputButton.css';

export default function VoiceInputButton({
  value = '',
  onTranscript,
  onError,
  onListeningChange,
  disabled = false,
  className = '',
}) {
  const { listening, supported, toggle } = useVoiceInput({
    onTranscript,
    onError,
    disabled,
  });

  useEffect(() => {
    onListeningChange?.(listening);
  }, [listening, onListeningChange]);

  const classes = [
    'voice-input-btn',
    className,
    listening ? 'is-listening' : '',
    !supported ? 'is-unsupported' : '',
  ].filter(Boolean).join(' ');

  return (
    <button
      type="button"
      className={classes}
      onClick={() => toggle(value)}
      disabled={disabled || !supported}
      aria-pressed={listening}
      aria-label={
        !supported
          ? 'Voice input is not supported in this browser'
          : listening
            ? 'Stop voice input'
            : 'Start voice input'
      }
      title={
        !supported
          ? 'Voice input needs Chrome or Edge'
          : listening
            ? 'Listening — click to stop'
            : 'Speak a prompt'
      }
    >
      {supported ? <Mic size={16} strokeWidth={1.75} /> : <MicOff size={16} strokeWidth={1.75} />}
      {listening ? <span className="voice-input-pulse" aria-hidden="true" /> : null}
    </button>
  );
}
