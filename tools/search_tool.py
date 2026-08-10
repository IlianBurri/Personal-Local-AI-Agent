import re

import requests
from typing import List

MAX_FETCH_BYTES = 2 * 1024 * 1024  # 2 MB


def web_search(query: str, max_results: int = 5) -> List[str]:
    """Perform a simple web search using DuckDuckGo instant answer API.

    Returns a list of textual results (abstracts / related topics).
    """
    url = "https://api.duckduckgo.com/"
    params = {"q": query, "format": "json", "t": "ai-agent"}
    r = requests.get(url, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    results = []
    if data.get("AbstractText"):
        results.append(data.get("AbstractText"))
    related = data.get("RelatedTopics", [])
    for item in related:
        if len(results) >= max_results:
            break
        if isinstance(item, dict):
            text = item.get("Text")
            if text:
                results.append(text)
        elif isinstance(item, list) and item:
            # sometimes RelatedTopics contains lists
            t = item[0].get("Text") if isinstance(item[0], dict) else None
            if t:
                results.append(t)
    return results


def fetch_url(url: str) -> str:
    """Fetch a web page and return its readable text content.

    Only http(s) URLs are allowed. Scripts, styles and markup are stripped;
    the result is capped so the model never receives a wall of noise.
    """
    if not url.startswith(("http://", "https://")):
        return '{"error": "Only http(s) URLs are supported"}'
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "arca-agent/1.0"})
        r.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - surfaced to the model as a result
        return '{"error": "Request failed: %s"}' % exc
    content_type = r.headers.get("Content-Type", "")
    if "text" not in content_type and "html" not in content_type and "json" not in content_type:
        return '{"error": "Unsupported content type: %s"}' % content_type
    body = r.content[:MAX_FETCH_BYTES].decode("utf-8", errors="ignore")
    if not body:
        return '{"error": "Empty page"}'

    text = _html_to_text(body)
    if len(text) > 20000:
        text = text[:20000] + "\n...[truncated]"
    return text


def _html_to_text(html: str) -> str:
    """Crude but effective HTML→text: drop scripts/styles/tags, collapse space."""
    text = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;?", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&#\d+;", " ", text)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    collapsed = []
    for ln in lines:
        if ln == " " and collapsed and collapsed[-1] == " ":
            continue
        collapsed.append(ln)
    return "\n".join(collapsed)
