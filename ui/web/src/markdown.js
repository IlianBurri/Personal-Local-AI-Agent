import hljs from 'highlight.js';
import { Marked } from 'marked';
import DOMPurify from 'dompurify';
import 'highlight.js/styles/github-dark.css';

const esc = (s) =>
  String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

export const marked = new Marked();

marked.use({
  gfm: true,
  breaks: true,
  renderer: {
    // Renders fenced code as a bordered block with a language header and
    // a copy button (clicks are handled via event delegation in Message).
    code(code, infostring) {
      const lang = (infostring || '').split(/\s+/)[0];
      let highlighted;
      if (lang && hljs.getLanguage(lang)) {
        highlighted = hljs.highlight(code, { language: lang }).value;
      } else {
        highlighted = hljs.highlightAuto(code).value;
      }
      return (
        '<div class="code-block">' +
        `<div class="code-head"><span class="code-lang">${esc(lang || 'code')}</span>` +
        '<button class="code-copy" type="button">Copy</button></div>' +
        `<pre><code class="hljs language-${esc(lang || '')}">${highlighted}</code></pre>` +
        '</div>'
      );
    },
  },
});

export function renderMarkdown(text) {
  const raw = marked.parse(text || '');
  return DOMPurify.sanitize(raw);
}
