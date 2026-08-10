export const PROVIDERS = ['ollama', 'openai', 'anthropic'];

export const ACCENTS = {
  graphite: '#64748b',
  mint: '#0aff9d',
  azure: '#3b82f6',
  amethyst: '#8b5cf6',
  amber: '#f59e0b',
};

export const DEFAULT_ACCENT = 'mint';

/** Resolve a stored accent (preset name or #hex) to a CSS color. */
export function accentColor(accent) {
  if (!accent) return ACCENTS[DEFAULT_ACCENT];
  if (ACCENTS[accent]) return ACCENTS[accent];
  return /^#[0-9a-fA-F]{3,8}$/.test(accent) ? accent : ACCENTS[DEFAULT_ACCENT];
}

/** Convert '#rrggbb' to 'rgba(r,g,b,a)' for soft/hover surfaces. */
export function accentRgba(accent, alpha) {
  let hex = accentColor(accent).replace('#', '');
  if (hex.length === 3) {
    hex = hex.split('').map((c) => c + c).join('');
  }
  const n = parseInt(hex.slice(0, 6), 16);
  if (Number.isNaN(n)) return `rgba(10,255,157,${alpha})`;
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  return `rgba(${r},${g},${b},${alpha})`;
}

async function request(url, options = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} ${res.statusText}`);
  }
  return res;
}

export async function getJSON(url) {
  const res = await request(url);
  return res.json();
}

export async function postJSON(url, body) {
  const res = await request(url, { method: 'POST', body: JSON.stringify(body || {}) });
  return res.json();
}

export async function patchJSON(url, body) {
  const res = await request(url, { method: 'PATCH', body: JSON.stringify(body || {}) });
  return res.json();
}

export async function del(url) {
  await request(url, { method: 'DELETE' });
}

/**
 * POST /api/chat and consume the SSE stream.
 *
 * Events handled: meta, token, tool, done, error.
 * Token events are batched (~40 ms) so markdown re-renders stay cheap
 * while the model is streaming.
 *
 * Returns `{ abort() }` synchronously so the caller can stop the
 * generation. Transport errors (non-200, aborted mid-flight) surface
 * through `onError`, never as unhandled rejections.
 */
export function streamChat(payload, handlers = {}) {
  const controller = new AbortController();
  const { onMeta, onToken, onTool, onDone, onError, onNotice } = handlers;

  let pending = '';
  let flushTimer = null;
  const flushNow = () => {
    if (flushTimer) {
      clearTimeout(flushTimer);
      flushTimer = null;
    }
    if (pending) {
      const chunk = pending;
      pending = '';
      onToken?.(chunk);
    }
  };
  const flushSoon = () => {
    if (flushTimer) return;
    flushTimer = setTimeout(flushNow, 40);
  };

  const run = async () => {
    try {
      const res = await request('/api/chat', {
        method: 'POST',
        body: JSON.stringify(payload),
        signal: controller.signal,
      });
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let sep;
        while ((sep = buffer.indexOf('\n\n')) !== -1) {
          const raw = buffer.slice(0, sep);
          buffer = buffer.slice(sep + 2);
          const lines = raw.split('\n');
          const dataLine = lines.find((l) => l.startsWith('data: '));
          if (!dataLine) continue;
          let data;
          try {
            data = JSON.parse(dataLine.slice(6));
          } catch {
            continue;
          }
          const eventLine = lines.find((l) => l.startsWith('event: '));
          const event = eventLine ? eventLine.slice(7) : 'message';

          if (event === 'meta') onMeta?.(data);
          else if (event === 'token') {
            if (data.text) {
              pending += data.text;
              flushSoon();
            }
          } else if (event === 'tool') onTool?.(data);
          else if (event === 'notice') onNotice?.(data?.message || '');
          else if (event === 'done') {
            flushNow();
            onDone?.(data);
          } else if (event === 'error') {
            flushNow();
            onError?.(data.message || 'Unknown error');
          }
        }
      }
      flushNow();
    } catch (err) {
      // Aborted by the caller (stop) — not an error.
      if (err && err.name === 'AbortError') return;
      onError?.(err?.message || 'Connection lost');
    }
  };

  run();

  return { abort: () => controller.abort() };
}
