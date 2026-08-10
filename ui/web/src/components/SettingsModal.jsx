import { useEffect, useState } from 'react';
import { ACCENTS, PROVIDERS, accentColor, getJSON } from '../api.js';

export default function SettingsModal({ config, onClose, onSave }) {
  const [openaiKey, setOpenaiKey] = useState('');
  const [anthropicKey, setAnthropicKey] = useState('');
  const [baseUrl, setBaseUrl] = useState(
    config.providers?.ollama?.base_url || 'http://localhost:11434'
  );
  const [temperature, setTemperature] = useState(config.generation?.temperature ?? 0.7);
  const [maxTokens, setMaxTokens] = useState(config.generation?.max_tokens ?? 1024);
  const [enableTools, setEnableTools] = useState(config.generation?.enable_tools ?? true);
  const [allowShell, setAllowShell] = useState(config.generation?.allow_shell ?? false);
  const [systemPrompt, setSystemPrompt] = useState(
    config.generation?.system_prompt ?? ''
  );
  const [maxToolRounds, setMaxToolRounds] = useState(
    config.generation?.max_tool_rounds ?? 10
  );
  const [modelsByProvider, setModelsByProvider] = useState({});
  const [selected, setSelected] = useState({});
  const [accent, setAccent] = useState(config.ui?.accent || 'mint');
  const [dark, setDark] = useState(config.ui?.dark ?? true);
  const [fontSize, setFontSize] = useState(config.ui?.font_size ?? 14);
  const [chatWidth, setChatWidth] = useState(config.ui?.chat_width ?? 740);
  const [appName, setAppName] = useState(config.ui?.app_name ?? 'Arca');
  const [tagline, setTagline] = useState(config.ui?.tagline ?? '');
  const [suggestionsText, setSuggestionsText] = useState(
    (config.ui?.suggestions || []).join('\n')
  );
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      const out = {};
      const prefs = {};
      for (const p of PROVIDERS) {
        try {
          out[p] = (await getJSON(`/api/models?provider=${p}`)).models || [];
        } catch {
          out[p] = [];
        }
        prefs[p] = config.providers?.[p]?.model || out[p]?.[0] || '';
      }
      setModelsByProvider(out);
      setSelected(prefs);
    })();
  }, [config]);

  const save = async () => {
    setSaving(true);
    const payload = {
      api_keys: {
        openai: openaiKey.trim(),
        anthropic: anthropicKey.trim(),
      },
      ollama: { base_url: baseUrl.trim() },
      models: selected,
      generation: {
        temperature,
        max_tokens: maxTokens,
        enable_tools: enableTools,
        allow_shell: allowShell,
        system_prompt: systemPrompt,
        max_tool_rounds: maxToolRounds,
      },
      ui: {
        dark,
        accent,
        font_size: fontSize,
        chat_width: chatWidth,
        app_name: appName,
        tagline,
        suggestions: suggestionsText
          .split('\n')
          .map((s) => s.trim())
          .filter(Boolean),
      },
    };
    await onSave(payload);
    setSaving(false);
    onClose();
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2 className="modal-title">Settings</h2>

        <div className="modal-body">
          <h3>API Keys</h3>
          <label className="field">
            <span>OpenAI API Key</span>
            <input
              type="password"
              placeholder="Not set"
              value={openaiKey}
              onChange={(e) => setOpenaiKey(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Anthropic API Key</span>
            <input
              type="password"
              placeholder="Not set"
              value={anthropicKey}
              onChange={(e) => setAnthropicKey(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Ollama Base URL</span>
            <input
              type="text"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          </label>

          <h3>Default Models</h3>
          {PROVIDERS.map((p) => (
            <label className="field" key={p}>
              <span>{p}</span>
              <select
                value={selected[p] || ''}
                onChange={(e) =>
                  setSelected((s) => ({ ...s, [p]: e.target.value }))
                }
              >
                {(modelsByProvider[p] || []).map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
          ))}

          <h3>Generation</h3>
          <label className="field">
            <span>
              Temperature <b>{temperature.toFixed(2)}</b>
            </span>
            <input
              type="range"
              min={0}
              max={100}
              value={Math.round(temperature * 100)}
              onChange={(e) => setTemperature(Number(e.target.value) / 100)}
            />
          </label>
          <label className="field">
            <span>Max tokens</span>
            <input
              type="number"
              min={64}
              max={128000}
              step={256}
              value={maxTokens}
              onChange={(e) => setMaxTokens(Number(e.target.value))}
            />
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={enableTools}
              onChange={(e) => setEnableTools(e.target.checked)}
            />
            <span>Enable tool use (files, code search, web)</span>
          </label>
          <label className="check-row">
            <input
              type="checkbox"
              checked={allowShell}
              onChange={(e) => setAllowShell(e.target.checked)}
            />
            <span>Allow shell commands</span>
          </label>

          <h3>Agent</h3>
          <div className="area-field">
            <span>
              System prompt{' '}
              <i style={{ color: 'var(--text-quiet)' }}>
                (guides every reply; leave empty to use the model default)
              </i>
            </span>
            <textarea
              rows={4}
              value={systemPrompt}
              placeholder="e.g. You are a senior software engineer. Always explain your reasoning, prefer minimal diffs, and run the tests before finishing."
              onChange={(e) => setSystemPrompt(e.target.value)}
            />
          </div>
          <label className="field">
            <span>Max tool rounds</span>
            <input
              type="number"
              min={1}
              max={50}
              value={maxToolRounds}
              onChange={(e) => setMaxToolRounds(Number(e.target.value))}
            />
          </label>

          <h3>Appearance</h3>
          <div className="accent-row">
            {Object.entries(ACCENTS).map(([name, color]) => (
              <button
                key={name}
                type="button"
                className={`accent-dot ${accent === name ? 'active' : ''}`}
                style={{ background: color }}
                onClick={() => setAccent(name)}
                title={name}
                aria-label={name}
              />
            ))}
            <label className="accent-custom" title="Custom color">
              <input
                type="color"
                value={accentColor(accent)}
                onChange={(e) => setAccent(e.target.value)}
              />
              <span className={`accent-custom-label ${ACCENTS[accent] ? '' : 'active'}`}>
                Custom
              </span>
            </label>
          </div>
          <label className="check-row">
            <input
              type="checkbox"
              checked={dark}
              onChange={(e) => setDark(e.target.checked)}
            />
            <span>Dark mode</span>
          </label>
          <label className="field">
            <span>
              Font size <b>{fontSize}px</b>
            </span>
            <input
              type="range"
              min={12}
              max={20}
              value={fontSize}
              onChange={(e) => setFontSize(Number(e.target.value))}
            />
          </label>
          <label className="field">
            <span>
              Chat width <b>{chatWidth}px</b>
            </span>
            <input
              type="range"
              min={560}
              max={1000}
              step={10}
              value={chatWidth}
              onChange={(e) => setChatWidth(Number(e.target.value))}
            />
          </label>
          <label className="field">
            <span>App name</span>
            <input
              type="text"
              value={appName}
              onChange={(e) => setAppName(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Tagline</span>
            <input
              type="text"
              value={tagline}
              onChange={(e) => setTagline(e.target.value)}
            />
          </label>
          <div className="area-field">
            <span>
              Suggestion chips{' '}
              <i style={{ color: 'var(--text-quiet)' }}>(one per line)</i>
            </span>
            <textarea
              rows={5}
              value={suggestionsText}
              placeholder={'Explain a concept\nWrite some code\n…'}
              onChange={(e) => setSuggestionsText(e.target.value)}
            />
          </div>
        </div>

        <div className="modal-actions">
          <button className="btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button className="btn-primary" onClick={save} disabled={saving}>
            {saving ? 'Saving\u2026' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
