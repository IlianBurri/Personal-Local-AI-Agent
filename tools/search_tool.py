import requests
from typing import List


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
