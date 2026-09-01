import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from './AuthContext';

const ChatHistoryContext = createContext(null);

const MAX_SESSIONS = 40;
const TITLE_LEN = 42;

function storageKey(role) {
  return `cg-chat-history-${role || 'guest'}`;
}

function normalizeSession(session) {
  if (!session) return session;
  if (Array.isArray(session.messages) && session.messages.length > 0) {
    return session;
  }
  if (Array.isArray(session.prompts) && session.prompts.length > 0) {
    return {
      ...session,
      messages: session.prompts.map((p) => ({
        userText: p.text,
        assistantText: '',
        guardrailTriggered: false,
        action: 'ALLOW',
        issues: [],
        highlights: [],
        blocked: false,
        ts: p.ts,
      })),
    };
  }
  return { ...session, messages: [] };
}

function loadSessions(role) {
  try {
    const raw = sessionStorage.getItem(storageKey(role));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.map(normalizeSession);
  } catch {
    return [];
  }
}

function saveSessions(role, sessions) {
  try {
    sessionStorage.setItem(storageKey(role), JSON.stringify(stripPreviewForStorage(sessions)));
  } catch {
    /* ignore quota errors */
  }
}

function makeTitle(text, imageName) {
  const trimmed = (text || '').trim();
  if (trimmed) {
    if (trimmed.length <= TITLE_LEN) return trimmed;
    return `${trimmed.slice(0, TITLE_LEN).trim()}…`;
  }
  if (imageName) {
    const name = imageName.length <= TITLE_LEN ? imageName : `${imageName.slice(0, TITLE_LEN)}…`;
    return `Image · ${name}`;
  }
  return 'Image';
}

function stripPreviewForStorage(sessions) {
  return sessions.map((session) => ({
    ...session,
    messages: (session.messages || []).map(({ imagePreview, ...rest }) => rest),
  }));
}

function newSession(exchange) {
  const now = Date.now();
  return {
    id: crypto.randomUUID(),
    title: makeTitle(exchange.userText, exchange.imageName),
    messages: [exchange],
    createdAt: now,
    updatedAt: now,
  };
}

export function ChatHistoryProvider({ children }) {
  const { auth } = useAuth();
  const role = auth?.role;
  const [sessions, setSessions] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const activeIdRef = useRef(null);

  useEffect(() => {
    activeIdRef.current = activeId;
  }, [activeId]);

  useEffect(() => {
    setSessions(loadSessions(role));
    setActiveId(null);
    activeIdRef.current = null;
  }, [role]);

  useEffect(() => {
    if (!role) return;
    saveSessions(role, sessions);
  }, [role, sessions]);

  const activeSession = useMemo(
    () => sessions.find((s) => s.id === activeId) ?? null,
    [sessions, activeId],
  );

  const startNewSession = useCallback(() => {
    setActiveId(null);
    activeIdRef.current = null;
  }, []);

  const selectSession = useCallback((id) => {
    setActiveId(id);
    activeIdRef.current = id;
  }, []);

  const beginTurn = useCallback((userText, meta = {}) => {
    const trimmed = (userText || '').trim();
    const hasImage = Boolean(meta.imagePreview);
    if (!trimmed && !hasImage) return null;

    const entry = {
      userText: trimmed || (meta.imageName ? `Sent ${meta.imageName}` : 'Sent an attachment'),
      imagePreview: meta.imagePreview || null,
      imageName: meta.imageName || null,
      attachmentKind: meta.attachmentKind || (meta.imagePreview ? 'image' : null),
      inputType: meta.imagePreview || meta.attachmentKind ? (meta.attachmentKind || 'image') : 'text',
      assistantText: '',
      guardrailTriggered: false,
      action: 'PENDING',
      issues: [],
      highlights: [],
      blocked: false,
      loading: true,
      ts: Date.now(),
    };

    let sessionId = null;

    setSessions((prev) => {
      const now = Date.now();
      const currentId = activeIdRef.current;
      const existing = currentId ? prev.find((s) => s.id === currentId) : null;

      if (existing) {
        sessionId = existing.id;
        const updated = {
          ...existing,
          messages: [...(existing.messages || []), entry],
          updatedAt: now,
        };
        return [updated, ...prev.filter((s) => s.id !== existing.id)].slice(0, MAX_SESSIONS);
      }

      const created = newSession(entry);
      sessionId = created.id;
      return [created, ...prev].slice(0, MAX_SESSIONS);
    });

    if (sessionId) {
      setActiveId(sessionId);
      activeIdRef.current = sessionId;
    }
    return sessionId;
  }, []);

  const completeTurn = useCallback((sessionId, update) => {
    if (!sessionId) return;

    setSessions((prev) => {
      const idx = prev.findIndex((s) => s.id === sessionId);
      if (idx === -1) return prev;

      const session = prev[idx];
      const messages = [...(session.messages || [])];
      if (messages.length === 0) return prev;

      const last = messages[messages.length - 1];
      messages[messages.length - 1] = {
        ...last,
        ...update,
        loading: false,
        ts: last.ts || Date.now(),
      };

      const updated = {
        ...session,
        messages,
        updatedAt: Date.now(),
      };

      const rest = prev.filter((s) => s.id !== session.id);
      return [updated, ...rest].slice(0, MAX_SESSIONS);
    });
  }, []);

  const value = useMemo(
    () => ({
      sessions,
      activeId,
      activeSession,
      startNewSession,
      selectSession,
      beginTurn,
      completeTurn,
    }),
    [sessions, activeId, activeSession, startNewSession, selectSession, beginTurn, completeTurn],
  );

  return (
    <ChatHistoryContext.Provider value={value}>
      {children}
    </ChatHistoryContext.Provider>
  );
}

export function useChatHistory() {
  const ctx = useContext(ChatHistoryContext);
  if (!ctx) throw new Error('useChatHistory must be used within ChatHistoryProvider');
  return ctx;
}
