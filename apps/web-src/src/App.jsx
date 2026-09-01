import { useState, useCallback, useEffect } from 'react';
import { useAuth } from './context/AuthContext';
import { useTheme } from './context/ThemeContext';
import { useChatHistory } from './context/ChatHistoryContext';
import {
  Home, FileText, Image, ClipboardList, LogOut, Shield, Sparkles, Network, Sun, Moon,
  PanelLeftClose, MessageSquare, Monitor, BookCheck,
} from 'lucide-react';
import HealthDot from './components/HealthDot';
import LoginPage from './pages/LoginPage';
import HomePage from './pages/HomePage';
import AgentFlowPage from './pages/AgentFlowPage';
import GovernanceDashboard from './pages/GovernanceDashboard';
import TextEvaluatePage from './pages/TextEvaluatePage';
import ImageEvaluatePage from './pages/ImageEvaluatePage';
import AuditLogPage from './pages/AuditLogPage';
import ComputerUsePage from './pages/ComputerUsePage';
import GxpReviewPage from './pages/GxpReviewPage';
import sidebarLogo from './assets/sidebar-logo.png';

const EXPERIENCE = 'experience';

const TOOLS_NAV = [
  { id: 'governance', label: 'Governance', Icon: Shield },
  { id: 'computer', label: 'Computer Use', Icon: Monitor },
  { id: 'gxp', label: 'GxP Rewrite', Icon: BookCheck },
  { id: 'text', label: 'Prompt Lab', Icon: FileText },
  { id: 'image', label: 'Image Evaluate', Icon: Image },
  { id: 'audit', label: 'Audit Log', Icon: ClipboardList },
];

const TOOL_LABELS = Object.fromEntries(TOOLS_NAV.map((t) => [t.id, t.label]));

function formatHistoryTime(ts) {
  const date = new Date(ts);
  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();
  if (sameDay) {
    return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  }
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

export default function App() {
  const { auth, logout } = useAuth();
  const { resolved, toggleTheme } = useTheme();
  const {
    sessions: chatSessions,
    activeId: activeChatId,
    startNewSession,
    selectSession,
  } = useChatHistory();
  const [experienceMode, setExperienceMode] = useState('chat');
  const [tab, setTab] = useState(EXPERIENCE);
  const [menuOpen, setMenuOpen] = useState(false);
  const [chatKey, setChatKey] = useState(0);

  const isExperience = tab === EXPERIENCE;
  const isPipeline = isExperience && experienceMode === 'pipeline';
  const isChat = isExperience && experienceMode === 'chat';
  const isFullBleed = isExperience;
  const isGovernance = tab === 'governance';
  const isComputerUse = tab === 'computer';
  const isGxpReview = tab === 'gxp';

  const closeMenu = useCallback(() => setMenuOpen(false), []);
  const toggleMenu = useCallback(() => setMenuOpen((open) => !open), []);

  const openExperience = useCallback((mode) => {
    setExperienceMode(mode);
    setTab(EXPERIENCE);
  }, []);

  const openChat = useCallback(() => {
    startNewSession();
    setChatKey((k) => k + 1);
    openExperience('chat');
  }, [openExperience, startNewSession]);

  const openTool = useCallback((toolId) => {
    setTab(toolId);
    closeMenu();
  }, [closeMenu]);

  const handleNewSession = useCallback(() => {
    openChat();
  }, [openChat]);

  const handleSelectChat = useCallback((sessionId) => {
    selectSession(sessionId);
    setChatKey((k) => k + 1);
    openExperience('chat');
  }, [openExperience, selectSession]);

  const handleOpenHistory = useCallback(() => {
    setMenuOpen(true);
  }, []);

  useEffect(() => {
    if (!menuOpen) return undefined;
    const onKeyDown = (e) => {
      if (e.key === 'Escape') closeMenu();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [menuOpen, closeMenu]);

  if (!auth) {
    return <LoginPage />;
  }

  const activeLabel = isExperience
    ? (isPipeline ? 'Pipeline' : 'Chat')
    : (TOOL_LABELS[tab] || 'Console');

  const workspaceClass = [
    'workspace',
    isFullBleed ? 'workspace--fullbleed' : '',
    isPipeline ? 'workspace--flow' : '',
  ].filter(Boolean).join(' ');

  const mainClass = [
    'workspace-main',
    isFullBleed ? 'workspace-main--fullbleed' : '',
    isPipeline ? 'workspace-main--flow' : '',
  ].filter(Boolean).join(' ');

  return (
    <div className={`app-shell app-shell--landing${menuOpen ? ' menu-open' : ''}`}>
      <aside
        id="app-menu-drawer"
        className={`sidebar sidebar--expandable${menuOpen ? ' is-expanded' : ''}`}
      >
        <div className="sidebar-brand-row">
          <button
            type="button"
            className="sidebar-brand"
            onClick={toggleMenu}
            aria-label={menuOpen ? 'Collapse menu' : 'Expand menu'}
            aria-expanded={menuOpen}
            aria-controls="app-menu-panel"
          >
            <span className="sidebar-brand-mark">
              <img
                src={sidebarLogo}
                alt=""
                className="sidebar-brand-logo"
              />
              <span className="sidebar-brand-logo-fallback" style={{ display: 'none' }}>
                <Shield size={15} />
              </span>
            </span>
            <span className="sidebar-brand-copy">
              <span className="sidebar-brand-name">ContextGuard</span>
              <span className="sidebar-brand-tag">Policy layer</span>
            </span>
          </button>
          <button
            type="button"
            className="sidebar-collapse-btn"
            onClick={closeMenu}
            aria-label="Collapse menu"
            tabIndex={menuOpen ? 0 : -1}
            aria-hidden={!menuOpen}
          >
            <PanelLeftClose size={15} strokeWidth={1.75} />
          </button>
        </div>

        {!menuOpen && (
          <div className="sidebar-rail" aria-label="Quick navigation">
            <button
              type="button"
              className={`sidebar-rail-btn${isChat && isExperience ? ' active' : ''}`}
              onClick={openChat}
              title="Chat"
              aria-label="Chat"
            >
              <Sparkles size={18} strokeWidth={1.75} />
            </button>
            <button
              type="button"
              className={`sidebar-rail-btn${isPipeline && isExperience ? ' active' : ''}`}
              onClick={() => openExperience('pipeline')}
              title="Pipeline"
              aria-label="Pipeline"
            >
              <Network size={18} strokeWidth={1.75} />
            </button>
            <div className="sidebar-rail-divider" />
            {TOOLS_NAV.map((t) => (
              <button
                key={t.id}
                type="button"
                className={`sidebar-rail-btn${tab === t.id ? ' active' : ''}`}
                onClick={() => openTool(t.id)}
                title={t.label}
                aria-label={t.label}
              >
                <t.Icon size={18} strokeWidth={1.75} />
              </button>
            ))}
          </div>
        )}

        <div id="app-menu-panel" className="sidebar-panel">
          <div className="sidebar-section">
            <p className="sidebar-section-label">Experience</p>
            <div className="sidebar-mode-switch" role="group" aria-label="Chat or pipeline">
              <button
                type="button"
                className={`sidebar-mode-option${isChat && isExperience ? ' active' : ''}`}
                onClick={openChat}
                aria-pressed={isChat && isExperience}
              >
                <Sparkles size={14} strokeWidth={1.75} />
                Chat
              </button>
              <button
                type="button"
                className={`sidebar-mode-option${isPipeline && isExperience ? ' active' : ''}`}
                onClick={() => openExperience('pipeline')}
                aria-pressed={isPipeline && isExperience}
              >
                <Network size={14} strokeWidth={1.75} />
                Pipeline
              </button>
            </div>
          </div>

          <div className="sidebar-panel-body">
            <nav className="sidebar-tools" aria-label="Tools">
              <p className="sidebar-section-label">Tools</p>
              {TOOLS_NAV.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className={`sidebar-nav-item${tab === t.id ? ' active' : ''}`}
                  onClick={() => openTool(t.id)}
                  aria-current={tab === t.id ? 'page' : undefined}
                >
                  <t.Icon size={16} strokeWidth={1.75} />
                  <span>{t.label}</span>
                </button>
              ))}
            </nav>

            <nav className="sidebar-history" aria-label="Chat history">
              <p className="sidebar-section-label">History</p>
              {chatSessions.length === 0 ? (
                <p className="sidebar-history-empty">No chats yet</p>
              ) : (
                <ul className="sidebar-history-list">
                  {chatSessions.map((session) => (
                    <li key={session.id}>
                      <button
                        type="button"
                        className={`sidebar-history-item${activeChatId === session.id && isChat ? ' active' : ''}`}
                        onClick={() => handleSelectChat(session.id)}
                        aria-current={activeChatId === session.id && isChat ? 'true' : undefined}
                      >
                        <MessageSquare size={14} strokeWidth={1.75} aria-hidden="true" />
                        <span className="sidebar-history-title">{session.title}</span>
                        <span className="sidebar-history-time">{formatHistoryTime(session.updatedAt)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </nav>
          </div>

          <div className="sidebar-foot">
            <div className="sidebar-health-row">
              <HealthDot withLabel />
            </div>
            <button type="button" className="sidebar-nav-item" onClick={toggleTheme}>
              {resolved === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
              <span>{resolved === 'dark' ? 'Light mode' : 'Dark mode'}</span>
            </button>
            <div className="sidebar-user-card">
              <span className="sidebar-user-avatar" aria-hidden="true">
                {(auth.role || 'U').slice(0, 1).toUpperCase()}
              </span>
              <div className="sidebar-user-copy">
                <span className="sidebar-user-name">{auth.role || 'User'}</span>
                <span className="sidebar-user-meta">Signed in</span>
              </div>
              <button
                type="button"
                className="sidebar-user-logout"
                onClick={logout}
                aria-label="Sign out"
                title="Sign out"
              >
                <LogOut size={15} />
              </button>
            </div>
          </div>
        </div>

        {!menuOpen && (
          <div className="sidebar-rail-foot">
            <button
              type="button"
              className="sidebar-rail-btn"
              onClick={toggleTheme}
              title={resolved === 'dark' ? 'Light mode' : 'Dark mode'}
              aria-label={resolved === 'dark' ? 'Light mode' : 'Dark mode'}
            >
              {resolved === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
            </button>
            <button
              type="button"
              className="sidebar-rail-btn sidebar-rail-btn--danger"
              onClick={logout}
              title="Sign out"
              aria-label="Sign out"
            >
              <LogOut size={18} />
            </button>
          </div>
        )}
      </aside>

      <div className={workspaceClass}>
        {!isFullBleed && !isGovernance && !isComputerUse && !isGxpReview && (
          <header className="topbar">
            <div className="topbar-left">
              <p className="eyebrow">Guardrail console</p>
              <h1 className="topbar-title">{activeLabel}</h1>
            </div>
            <div className="topbar-right">
              <button type="button" className="topbar-link" onClick={openChat}>
                <Home size={14} />
                Chat
              </button>
              <a className="topbar-link" href="/agent">FieldAssist chat</a>
              <a className="topbar-link" href="/demo">Quick demo</a>
            </div>
          </header>
        )}

        <main className={mainClass} id="main-content">
          {isExperience && isChat && (
            <HomePage
              key={chatKey}
              onNewSession={handleNewSession}
              onOpenHistory={handleOpenHistory}
            />
          )}
          {isExperience && isPipeline && <AgentFlowPage />}
          {tab === 'governance' && <GovernanceDashboard />}
          {tab === 'computer' && <ComputerUsePage />}
          {tab === 'gxp' && <GxpReviewPage />}
          {tab === 'text' && <TextEvaluatePage />}
          {tab === 'image' && <ImageEvaluatePage />}
          {tab === 'audit' && <AuditLogPage />}
        </main>
      </div>
    </div>
  );
}
