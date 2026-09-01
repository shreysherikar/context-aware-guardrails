import { useState, useRef, useEffect } from 'react';
import { useTheme } from '../context/ThemeContext';
import { useAuth } from '../context/AuthContext';
import { useChatHistory } from '../context/ChatHistoryContext';
import { apiFetch } from '../api';
import GuardrailNotice from '../components/GuardrailNotice';
import HighlightedPrompt from '../components/HighlightedPrompt';
import brandLogo from '../assets/brand-logo.png';
import {
  Shield, Paperclip, Zap, Wand2, FileText,
  ChevronDown, Send, Clock, SquarePen, Sun, Moon, Loader2, X,
} from 'lucide-react';
import {
  CHAT_ATTACHMENT_HINT,
  attachmentLabel,
  canPreviewAttachment,
  prepareChatUpload,
  validateChatAttachment,
} from '../utils/chatAttachment';
import FilePickInput from '../components/FilePickInput';
import VoiceInputButton from '../components/VoiceInputButton';
import './HomePage.css';

const QUICK_ACTIONS = [
  {
    id: 'fast',
    label: 'Draft a welcome note',
    Icon: Zap,
    prompt: 'Draft a welcome message for the new analysts ahead of the quarterly town hall.',
  },
  {
    id: 'policy',
    label: 'Try a policy example',
    Icon: Wand2,
    prompt:
      "Please look up the new hire's social security number — 123-45-6789 — plus date of birth so payroll can be set up.",
  },
];

function makeConvoId() {
  return `chat-${Date.now()}`;
}

export default function HomePage({ onNewSession, onOpenHistory }) {
  const { auth } = useAuth();
  const { resolved, toggleTheme } = useTheme();
  const { activeSession, beginTurn, completeTurn } = useChatHistory();
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [convId] = useState(makeConvoId);
  const [attachedFile, setAttachedFile] = useState(null);
  const [filePreview, setFilePreview] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [attachNotice, setAttachNotice] = useState(null);
  const [voiceHint, setVoiceHint] = useState(null);
  const threadEndRef = useRef(null);
  const fileInputRef = useRef(null);

  const messages = activeSession?.messages ?? [];
  const hasThread = messages.length > 0;
  const showImagePreview = attachedFile && filePreview && canPreviewAttachment(attachedFile);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  useEffect(() => {
    return () => {
      if (filePreview?.startsWith('blob:')) {
        URL.revokeObjectURL(filePreview);
      }
    };
  }, [filePreview]);

  function clearAttachment(revokePreview = true) {
    if (revokePreview && filePreview?.startsWith('blob:')) {
      URL.revokeObjectURL(filePreview);
    }
    setAttachedFile(null);
    setFilePreview(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  }

  function attachFile(file) {
    setError(null);
    setAttachNotice(null);
    if (!file) return;

    const validationError = validateChatAttachment(file);
    if (validationError) {
      setError(validationError);
      clearAttachment();
      return;
    }

    const uploadFile = prepareChatUpload(file);
    if (!uploadFile) {
      setError(`Could not attach ${file.name || 'this file'}.`);
      clearAttachment();
      return;
    }

    if (filePreview?.startsWith('blob:')) {
      URL.revokeObjectURL(filePreview);
    }

    setAttachedFile(uploadFile);
    setFilePreview(canPreviewAttachment(uploadFile) ? URL.createObjectURL(uploadFile) : null);
    setAttachNotice(`ContextGuard sees your ${attachmentLabel(uploadFile).toLowerCase()}: ${uploadFile.name}`);
  }

  function handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    if (!loading) setDragActive(true);
  }

  function handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    if (e.currentTarget === e.target) setDragActive(false);
  }

  function handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (loading) return;
    attachFile(e.dataTransfer?.files?.[0] || null);
  }

  async function submit(value) {
    const text = (value ?? prompt).trim();
    const file = attachedFile;
    if ((!text && !file) || !auth || loading) return;

    if (file) {
      const validationError = validateChatAttachment(file);
      if (validationError) {
        setError(validationError);
        return;
      }
    }

    setLoading(true);
    setError(null);
    const sentPrompt = text;
    setPrompt('');
    const previewForMessage = filePreview;
    const fileName = file?.name || null;
    const previewKind = file && canPreviewAttachment(file) ? 'image' : 'file';
    clearAttachment(false);

    const sessionId = beginTurn(sentPrompt, {
      imagePreview: previewForMessage,
      imageName: fileName,
      attachmentKind: file ? previewKind : null,
    });

    try {
      let data;
      if (file) {
        const uploadFile = prepareChatUpload(file) || file;
        const form = new FormData();
        form.append('file', uploadFile, uploadFile.name);
        form.append('conversation_id', convId);
        if (sentPrompt) form.append('message', sentPrompt);
        data = await apiFetch('/agent/chat-file', {
          method: 'POST',
          body: form,
          token: auth.token,
        });
      } else {
        data = await apiFetch('/agent/chat', {
          method: 'POST',
          body: { message: sentPrompt, conversation_id: convId },
          token: auth.token,
        });
      }

      const triggered = Boolean(data.guardrail_triggered);
      const reply = triggered
        ? (data.message || '')
        : (data.answer || data.message || '');

      completeTurn(sessionId, {
        assistantText: reply,
        guardrailTriggered: triggered,
        action: data.action,
        issues: data.issues || [],
        highlights: data.highlights || [],
        blocked: data.blocked,
      });
    } catch (err) {
      const msg = err.message || 'Something went wrong. Please try again.';
      setError(msg);
      completeTurn(sessionId, {
        assistantText: msg,
        guardrailTriggered: true,
        action: 'ERROR',
        issues: [{ code: 'ERROR', title: 'Request failed', description: msg }],
        highlights: [],
        blocked: true,
      });
    } finally {
      setLoading(false);
    }
  }

  const canSend = Boolean((prompt.trim() || attachedFile) && auth && !loading);

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className={`home-page${hasThread ? ' home-page--chat' : ''}`}>
      <header className="home-header">
        <div className="home-top-actions">
          <button type="button" className="home-icon-btn" aria-label="History" title="History" onClick={onOpenHistory}>
            <Clock size={18} />
          </button>
          <button
            type="button"
            className="home-icon-btn"
            aria-label={resolved === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            onClick={toggleTheme}
          >
            {resolved === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
          </button>
          <button type="button" className="home-icon-btn" aria-label="New chat" title="New chat" onClick={onNewSession}>
            <SquarePen size={18} />
          </button>
        </div>
      </header>

      {!hasThread ? (
        <div className="home-landing">
          <div className="home-brand-mark">
            <img src={brandLogo} alt="Novo Nordisk" className="home-brand-logo" />
          </div>
          <h1 className="home-greeting">Hey! I&apos;m ContextGuard</h1>
          <p className="home-subtitle">Chat normally — I&apos;ll only flag policy issues when something needs attention</p>

          <div className="home-quick-actions">
            {QUICK_ACTIONS.map(({ id, label, Icon, prompt: sample }) => (
              <button key={id} type="button" className="home-quick-btn" onClick={() => submit(sample)} disabled={loading}>
                <Icon size={14} />
                {label}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="home-chat-scroll" aria-label="Conversation">
          <div className="home-chat-thread">
            {messages.map((msg, index) => (
              <div key={`${msg.ts}-${index}`} className="home-chat-turn">
                <div className="home-chat-bubble home-chat-bubble--user">
                  {msg.imagePreview && (
                    <img
                      src={msg.imagePreview}
                      alt={msg.imageName || 'Uploaded file'}
                      className="home-chat-image"
                    />
                  )}
                  {!msg.imagePreview && msg.imageName && (
                    <div className="home-chat-file-chip">
                      <FileText size={16} aria-hidden="true" />
                      <span>{msg.imageName}</span>
                    </div>
                  )}
                  {msg.userText && (!msg.imageName || !msg.userText.startsWith('Sent ')) && (
                    <p>
                      {msg.guardrailTriggered && msg.highlights?.length > 0 ? (
                        <HighlightedPrompt text={msg.userText} highlights={msg.highlights} />
                      ) : (
                        msg.userText
                      )}
                    </p>
                  )}
                </div>

                {msg.guardrailTriggered && !msg.loading && (
                  <GuardrailNotice
                    userText={msg.userText}
                    issues={msg.issues}
                    highlights={msg.highlights}
                    action={msg.action}
                  />
                )}

                {msg.loading ? (
                  <div className="home-chat-bubble home-chat-bubble--assistant home-chat-loading">
                    <Loader2 size={16} className="home-spinner" />
                    <span>Thinking…</span>
                  </div>
                ) : (
                  msg.assistantText && (
                    <div className={`home-chat-bubble home-chat-bubble--assistant${msg.blocked ? ' is-blocked' : ''}`}>
                      <p>{msg.assistantText}</p>
                    </div>
                  )
                )}
              </div>
            ))}
            <div ref={threadEndRef} />
          </div>
        </div>
      )}

      <div className="home-composer-dock">
        {error && <p className="home-chat-error">{error}</p>}
        {attachNotice && !error && (
          <p className="home-chat-attach-notice">{attachNotice}</p>
        )}
        {voiceHint && !error && (
          <p className="home-chat-voice-hint" role="status">{voiceHint}</p>
        )}

        <div
          className={`home-composer${dragActive ? ' is-drag-active' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          {attachedFile && (
            <div className="home-composer-attachment">
              {showImagePreview ? (
                <img src={filePreview} alt="" className="home-composer-attachment-img" />
              ) : (
                <div className="home-composer-attachment-icon" aria-hidden="true">
                  <FileText size={22} />
                </div>
              )}
              <div className="home-composer-attachment-meta">
                <span className="home-composer-attachment-name">{attachedFile.name}</span>
                <span className="home-composer-attachment-hint home-composer-attachment-ready">
                  Ready to send · {attachmentLabel(attachedFile)} · max 10 MB
                </span>
              </div>
              <button
                type="button"
                className="home-composer-attachment-remove"
                onClick={() => clearAttachment()}
                aria-label="Remove attachment"
                disabled={loading}
              >
                <X size={14} />
              </button>
            </div>
          )}

          <textarea
            className="home-composer-input"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={attachedFile ? 'Add a note (optional)…' : 'Message ContextGuard…'}
            rows={hasThread ? 1 : 3}
            autoFocus
            disabled={loading}
          />

          <div className="home-composer-bar">
            <div className="home-composer-left">
              <FilePickInput
                inputRef={fileInputRef}
                disabled={loading}
                ariaLabel={`Attach file (${CHAT_ATTACHMENT_HINT})`}
                wrapClassName="home-composer-icon home-composer-file-trigger"
                onFile={attachFile}
              >
                <Paperclip size={16} aria-hidden="true" />
                <span className="sr-only">Attach file</span>
              </FilePickInput>
              <VoiceInputButton
                className="home-composer-icon"
                value={prompt}
                disabled={loading}
                onTranscript={setPrompt}
                onListeningChange={(on) => setVoiceHint(on ? 'Listening… click the mic to stop' : null)}
                onError={(message) => setVoiceHint(message)}
              />
            </div>

            <div className="home-composer-right">
              <button type="button" className="home-model-select" tabIndex={-1}>
                <Shield size={14} />
                <span>{auth?.role || 'User'}</span>
                <ChevronDown size={14} />
              </button>
              <button
                type="button"
                className="home-send-btn"
                disabled={!canSend}
                aria-label="Send message"
                onClick={() => submit()}
              >
                {loading ? <Loader2 size={16} className="home-spinner" /> : <Send size={16} />}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
