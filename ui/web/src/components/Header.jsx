import { PROVIDERS } from '../api.js';

export default function Header({
  provider,
  model,
  models,
  status,
  onProviderChange,
  onModelChange,
  onOpenSettings,
}) {
  const healthy = status
    ? provider === 'ollama'
      ? status.ollama_reachable
      : status.has_key
    : false;
  const hint = status
    ? provider === 'ollama'
      ? status.ollama_reachable
        ? 'Ollama reachable'
        : 'Ollama not reachable'
      : status.has_key
        ? 'API key configured'
        : 'No API key configured'
    : '…';

  return (
    <header className="header">
      <div className="header-status" title={hint}>
        <span className={`dot ${healthy ? 'ok' : 'bad'}`} />
        <span className="header-status-text">{healthy ? 'Ready' : 'Offline'}</span>
      </div>

      <select
        className="select"
        value={provider}
        onChange={(e) => onProviderChange(e.target.value)}
        title="Provider"
      >
        {PROVIDERS.map((p) => (
          <option key={p} value={p}>
            {p}
          </option>
        ))}
      </select>

      <select
        className="select select-model"
        value={model}
        onChange={(e) => onModelChange(e.target.value)}
        title="Model"
      >
        {models.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>

      <div className="header-spacer" />

      <button
        className="icon-btn"
        onClick={onOpenSettings}
        title="Settings"
        aria-label="Settings"
      >
        \u2699
      </button>
    </header>
  );
}
