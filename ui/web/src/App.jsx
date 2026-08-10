import { useCallback, useEffect, useRef, useState } from 'react';
import {
  accentColor,
  accentRgba,
  del,
  getJSON,
  patchJSON,
  postJSON,
  streamChat,
} from './api.js';
import Composer from './components/Composer.jsx';
import Header from './components/Header.jsx';
import { EmptyState, Message, TypingDots } from './components/Messages.jsx';
import SettingsModal from './components/SettingsModal.jsx';
import Sidebar from './components/Sidebar.jsx';

export function lastAssistantIndex(msgs) {
  for (let i = msgs.length - 1; i >= 0; i -= 1) {
    if (msgs[i].role === 'assistant') return i;
  }
  return -1;
}

export default function App() {
  const [chats, setChats] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [config, setConfig] = useState(null);
  const [models, setModels] = useState([]);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  const [provider, setProvider] = useState('ollama');
  const [model, setModel] = useState('');
  const [input, setInput] = useState('');

  const [streaming, setStreaming] = useState(false);
  const [streamText, setStreamText] = useState('');
  const [streamTools, setStreamTools] = useState([]);
  const [streamNotices, setStreamNotices] = useState([]);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const scrollRef = useRef(null);
  const streamRef = useRef(null);
  const genIdRef = useRef(null);
  const activeIdRef = useRef(null);
  const streamingRef = useRef(false);
  const streamTextRef = useRef('');
  const streamNoticesRef = useRef([]);
  const configRef = useRef(null);

  const applyTheme = (dark, accent, font, width) => {
    const root = document.documentElement;
    root.classList.toggle('light', !dark);
    const color = accentColor(accent);
    root.style.setProperty('--accent', color);
    root.style.setProperty('--accent-strong', color);
    root.style.setProperty('--accent-soft', accentRgba(accent, 0.09));
    root.style.setProperty('--base-font-size', `${font ?? 14}px`);
    root.style.setProperty('--chat-max-width', `${width ?? 740}px`);
  };

  const refreshChats = useCallback(async () => {
    try {
      setChats(await getJSON('/api/chats'));
    } catch {
      /* ignore */
    }
  }, []);

  const openChat = useCallback(async (id) => {
    activeIdRef.current = id;
    setActiveId(id);
    setMessages([]);
    try {
      setMessages(await getJSON(`/api/chats/${id}/messages`));
    } catch {
      /* ignore */
    }
  }, []);

  const loadModels = useCallback(async (prov) => {
    let list = [];
    try {
      const data = await getJSON(`/api/models?provider=${encodeURIComponent(prov)}`);
      list = data.models || [];
    } catch {
      list = [];
    }
    setModels(list);
    const saved = configRef.current?.providers?.[prov]?.model;
    if (saved && list.includes(saved)) setModel(saved);
    else if (list.length) setModel(list[0]);
    else setModel('');
    return list;
  }, []);

  const init = useCallback(async () => {
    try {
      const [c, cfg, st] = await Promise.all([
        getJSON('/api/chats'),
        getJSON('/api/config'),
        getJSON('/api/status'),
      ]);
      configRef.current = cfg;
      setChats(c);
      setConfig(cfg);
      applyTheme(
        cfg.ui?.dark ?? true,
        cfg.ui?.accent ?? 'mint',
        cfg.ui?.font_size ?? 14,
        cfg.ui?.chat_width ?? 740
      );
      setStatus(st);
      setProvider(cfg.provider || 'ollama');
      await loadModels(cfg.provider || 'ollama');
      if (c.length) await openChat(c[0].id);
    } catch (err) {
      console.error('init failed', err);
    } finally {
      setLoading(false);
    }
  }, [loadModels, openChat]);

  useEffect(() => {
    init();
  }, [init]);

  useEffect(() => {
    streamTextRef.current = streamText;
  }, [streamText]);

  useEffect(() => {
    streamingRef.current = streaming;
  }, [streaming]);

  useEffect(() => {
    streamNoticesRef.current = streamNotices;
  }, [streamNotices]);

  // Auto-scroll while streaming / on new messages.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 140;
    if (streaming || nearBottom) el.scrollTop = el.scrollHeight;
  }, [messages, streamText, streaming]);

  // ------------------------------------------------------------------
  // Chat actions
  // ------------------------------------------------------------------
  const commitStream = (errorMsg = null) => {
    const text = streamTextRef.current;
    const notices = streamNoticesRef.current;
    setStreaming(false);
    setStreamText('');
    setStreamTools([]);
    setStreamNotices([]);
    const appended = [];
    if (errorMsg) {
      appended.push({ role: 'assistant', content: errorMsg, isError: true });
    } else if (text.trim()) {
      appended.push({ role: 'assistant', content: text });
    }
    notices.forEach((n) => appended.push({ role: 'notice', content: n }));
    if (appended.length) setMessages((m) => [...m, ...appended]);
    refreshChats();
  };

  const beginStream = (payload) => {
    setStreaming(true);
    setStreamText('');
    setStreamTools([]);
    setStreamNotices([]);
    genIdRef.current = null;
    streamRef.current = streamChat(payload, {
      onMeta: (meta) => {
        genIdRef.current = meta.gen_id;
        if (meta.chat_id && meta.chat_id !== activeIdRef.current) {
          activeIdRef.current = meta.chat_id;
          setActiveId(meta.chat_id);
        }
        if (meta.title) refreshChats();
      },
      onToken: (tok) => {
        if (!streamingRef.current) return;
        // Keep the ref in sync synchronously so commitStream always sees
        // the exact latest text (no dropped final chunk on `done`).
        setStreamText((t) => {
          const next = t + tok;
          streamTextRef.current = next;
          return next;
        });
      },
      onTool: (tool) => {
        if (!streamingRef.current) return;
        setStreamTools((ts) => [...ts, tool]);
      },
      onNotice: (msg) => {
        if (!streamingRef.current) return;
        setStreamNotices((ns) => [...ns, msg]);
      },
      onDone: () => commitStream(),
      onError: (msg) => commitStream(msg),
    });
  };

  const send = (text) => {
    if (streaming || !config) return;
    setMessages((m) => [...m, { role: 'user', content: text }]);
    setInput('');
    beginStream({
      chat_id: activeId,
      provider,
      model,
      text,
    });
  };

  const regenerate = () => {
    if (streaming || !config || !activeId) return;
    setMessages((m) => {
      const i = lastAssistantIndex(m);
      return i === -1 ? m : m.slice(0, i);
    });
    beginStream({ chat_id: activeId, provider, model, regenerate: true });
  };

  const stop = () => {
    if (!streaming) return;
    streamRef.current?.abort();
    if (genIdRef.current) {
      postJSON('/api/stop', { gen_id: genIdRef.current }).catch(() => {});
    }
    commitStream();
  };

  const newChat = async () => {
    if (streaming) return;
    try {
      const data = await postJSON('/api/chats', {});
      setMessages([]);
      activeIdRef.current = data.id;
      setActiveId(data.id);
      await refreshChats();
    } catch {
      /* ignore */
    }
  };

  const renameChat = async (id, title) => {
    if (!title.trim()) return;
    try {
      await patchJSON(`/api/chats/${id}`, { title });
      await refreshChats();
    } catch {
      /* ignore */
    }
  };

  const deleteChat = async (id) => {
    try {
      await del(`/api/chats/${id}`);
    } catch {
      /* ignore */
    }
    const remaining = chats.filter((c) => c.id !== id);
    setChats(remaining);
    if (id === activeIdRef.current) {
      if (remaining.length) await openChat(remaining[0].id);
      else {
        activeIdRef.current = null;
        setActiveId(null);
        setMessages([]);
      }
    }
  };

  // ------------------------------------------------------------------
  // Provider / model / theme / settings
  // ------------------------------------------------------------------
  const changeProvider = async (p) => {
    if (p === provider) return;
    setProvider(p);
    postJSON('/api/config', { provider: p }).catch(() => {});
    await loadModels(p);
    setStatus((s) => (s ? { ...s, provider: p } : s));
  };

  const changeModel = (m) => {
    if (!m) return;
    setModel(m);
    postJSON('/api/config', { models: { [provider]: m } }).catch(() => {});
  };

  const toggleTheme = () => {
    const dark = !(config?.ui?.dark ?? true);
    applyTheme(
      dark,
      config?.ui?.accent,
      config?.ui?.font_size,
      config?.ui?.chat_width
    );
    setConfig((c) => (c ? { ...c, ui: { ...c.ui, dark } } : c));
    postJSON('/api/config', { ui: { dark } }).catch(() => {});
  };

  const handleSettingsSave = async (payload) => {
    try {
      await postJSON('/api/config', payload);
    } catch {
      /* ignore */
    }
    const cfg = await getJSON('/api/config').catch(() => null);
    if (cfg) {
      configRef.current = cfg;
      setConfig(cfg);
      applyTheme(
        cfg.ui?.dark ?? true,
        cfg.ui?.accent ?? 'mint',
        cfg.ui?.font_size ?? 14,
        cfg.ui?.chat_width ?? 740
      );
      setProvider(cfg.provider || 'ollama');
      await loadModels(cfg.provider || 'ollama');
    }
    setStatus(await getJSON('/api/status').catch(() => null));
  };

  if (loading) {
    return <div className="app-loading">Arca</div>;
  }

  return (
    <div className="app">
      <Sidebar
        chats={chats}
        activeId={activeId}
        dark={config?.ui?.dark ?? true}
        appName={config?.ui?.app_name || 'Arca'}
        onNew={newChat}
        onSelect={openChat}
        onRename={renameChat}
        onDelete={deleteChat}
        onToggleTheme={toggleTheme}
        onOpenSettings={() => setSettingsOpen(true)}
      />
      <div className="main">
        <Header
          provider={provider}
          model={model}
          models={models}
          status={status}
          onProviderChange={changeProvider}
          onModelChange={changeModel}
          onOpenSettings={() => setSettingsOpen(true)}
        />
        <div className="chat-scroll" ref={scrollRef}>
          <div className="chat-col">
            {messages.length === 0 && !streaming ? (
              <EmptyState
                onChip={setInput}
                appName={config?.ui?.app_name || 'Arca'}
                tagline={config?.ui?.tagline}
                suggestions={config?.ui?.suggestions}
              />
            ) : (
              <>
                {messages.map((m, i) => (
                  <Message
                    key={i}
                    role={m.role}
                    content={m.content}
                    isError={m.isError}
                    canRegenerate={
                      !streaming &&
                      m.role === 'assistant' &&
                      i === lastAssistantIndex(messages)
                    }
                    onRegenerate={regenerate}
                  />
                ))}
                {streaming &&
                  streamNotices.map((n, i) => (
                    <Message key={`notice-${i}`} role="notice" content={n} />
                  ))}
                {streaming && (
                  <Message
                    role="assistant"
                    content={streamText}
                    tools={streamTools}
                    streaming
                  />
                )}
                {streaming && !streamText && streamTools.length === 0 && (
                  <TypingDots />
                )}
              </>
            )}
          </div>
        </div>
        <Composer
          value={input}
          onChange={setInput}
          onSend={send}
          streaming={streaming}
          onStop={stop}
          model={model}
        />
      </div>
      {settingsOpen && (
        <SettingsModal
          config={config}
          onClose={() => setSettingsOpen(false)}
          onSave={handleSettingsSave}
        />
      )}
    </div>
  );
}
