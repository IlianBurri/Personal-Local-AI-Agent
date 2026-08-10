import { useEffect, useMemo, useRef } from 'react';
import { copyText } from '../clipboard.js';
import { renderMarkdown } from '../markdown.js';

const DEFAULT_SUGGESTIONS = [
  'Explain a concept',
  'Write some code',
  'Summarize text',
  'Draft an email',
  'Translate this',
  'Plan a project',
  'Debug my code',
  'Write a poem',
];

const SUGGESTION_ICONS = ['💡', '💻', '📝', '✉', '🌐', '📋', '🔍', '✨'];

function suggestionChips(suggestions) {
  const texts = Array.isArray(suggestions) && suggestions.length
    ? suggestions
    : DEFAULT_SUGGESTIONS;
  return texts.slice(0, 12).map((text, i) => ({
    text,
    icon: SUGGESTION_ICONS[i % SUGGESTION_ICONS.length],
  }));
}

export function Message({
  role,
  content,
  tools,
  streaming,
  isError,
  canRegenerate,
  onRegenerate,
}) {
  const html = useMemo(() => renderMarkdown(content || ''), [content]);
  const ref = useRef(null);

  // Event delegation: code-copy buttons + external links (webview bridge).
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const handler = (e) => {
      const copyBtn = e.target.closest('.code-copy');
      if (copyBtn) {
        const code =
          copyBtn.closest('.code-block')?.querySelector('code')?.innerText ?? '';
        copyText(code);
        copyBtn.textContent = 'Copied';
        setTimeout(() => {
          copyBtn.textContent = 'Copy';
        }, 1200);
        return;
      }
      const link = e.target.closest('a');
      if (link && link.href) {
        e.preventDefault();
        if (window.pywebview?.api?.open_external) {
          window.pywebview.api.open_external(link.href);
        } else {
          window.open(link.href, '_blank');
        }
      }
    };
    el.addEventListener('click', handler);
    return () => el.removeEventListener('click', handler);
  }, [html]);

  return (
    <div className={`msg msg-${role} ${isError ? 'msg-error' : ''}`}>
      <div className="msg-inner">
        {tools && tools.length > 0 && (
          <div className="tool-pills">
            {tools.map((t, i) => (
              <span
                key={i}
                className={`tool-pill ${
                  t.status === 'done' ? (t.ok ? 'ok' : 'err') : 'run'
                }`}
                title={t.name}
              >
                {t.status === 'start' ? '⟳' : t.ok ? '✓' : '✕'} {t.name}
              </span>
            ))}
          </div>
        )}

        {content ? (
          <div
            ref={ref}
            className={`markdown ${role === 'user' ? 'user-text' : ''}`}
            dangerouslySetInnerHTML={{ __html: html }}
          />
        ) : (
          !streaming &&
          !tools?.length && <div className="msg-empty">…</div>
        )}

        {canRegenerate && (
          <button
            className="btn-regenerate"
            onClick={onRegenerate}
            title="Regenerate response"
          >
            ↻ Regenerate
          </button>
        )}
      </div>
    </div>
  );
}

export function TypingDots() {
  return (
    <div className="msg msg-assistant">
      <div className="typing-dots">
        <span />
        <span />
        <span />
      </div>
    </div>
  );
}

export function EmptyState({ onChip, appName = 'Arca', tagline, suggestions }) {
  const chips = suggestionChips(suggestions);
  return (
    <div className="empty">
      <h1 className="empty-title">{appName}</h1>
      <p className="empty-sub">
        {tagline || 'Your models. Your machine. Your rules.'}
      </p>
      <div className="chips">
        {chips.map((s) => (
          <button key={s.text} className="chip" onClick={() => onChip(s.text)}>
            <span style={{ marginRight: 6 }}>{s.icon}</span>
            {s.text}
          </button>
        ))}
      </div>
    </div>
  );
}
