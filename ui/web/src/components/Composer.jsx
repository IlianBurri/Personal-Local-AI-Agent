import { useEffect, useRef } from 'react';

export default function Composer({
  value,
  onChange,
  onSend,
  streaming,
  onStop,
  model,
}) {
  const taRef = useRef(null);

  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`;
  }, [value]);

  const submit = () => {
    const text = value.trim();
    if (!text || streaming) return;
    onSend(text);
  };

  return (
    <div className="composer-wrap">
      <div className="composer">
        <textarea
          ref={taRef}
          className="composer-input"
          rows={1}
          placeholder="Message Arca…"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          disabled={streaming}
        />
        {streaming ? (
          <button
            className="btn-stop"
            onClick={onStop}
            title="Stop generating"
            aria-label="Stop generating"
          >
            \u25A0
          </button>
        ) : (
          <button
            className="btn-send"
            onClick={submit}
            disabled={!value.trim()}
            title="Send"
            aria-label="Send"
          >
            ↑
          </button>
        )}
      </div>
      {model && <div className="composer-hint">{model}</div>}
    </div>
  );
}
