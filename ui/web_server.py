from flask import Flask, request, jsonify, send_from_directory, Response, stream_with_context
from pathlib import Path
import threading
import webbrowser
import json

from core.config import load_config
from core.clients import OpenAIClient, AnthropicClient, OllamaClient

# Serve static files from ui/web/
WEB_DIR = Path(__file__).resolve().parent / "web"
app = Flask(__name__, static_folder=str(WEB_DIR))


@app.after_request
def add_cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/<path:filename>")
def static_files(filename):
    return send_from_directory(WEB_DIR, filename)


def _build_client(provider, model, conf):
    if provider == "openai":
        key = conf.get("openai", {}).get("api_key")
        if not key:
            raise ValueError("OpenAI API key not configured")
        return OpenAIClient(key, model=model or None)
    elif provider == "anthropic":
        key = conf.get("anthropic", {}).get("api_key")
        if not key:
            raise ValueError("Anthropic API key not configured")
        return AnthropicClient(key, model=model or None)
    else:
        base = conf.get("ollama", {}).get("base_url", "http://localhost:11434")
        return OllamaClient(base_url=base, model=model or None)


def _build_messages(data):
    messages = []
    if data.get("system"):
        messages.append({"role": "system", "content": data["system"]})
    if isinstance(data.get("history"), list):
        messages.extend(data["history"])
    messages.append({"role": "user", "content": data["message"]})
    return messages


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True)
    if not data or "message" not in data:
        return jsonify({"error": "missing 'message' field"}), 400
    cfg = load_config()
    provider = data.get("provider") or cfg.get("provider") or "openai"
    try:
        client = _build_client(provider, data.get("model"), cfg.get("providers", {}))
        out = [str(t) for t in client.stream_chat(_build_messages(data)) if t is not None]
        return jsonify({"reply": "".join(out)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat/stream", methods=["POST"])
def api_chat_stream():
    data = request.get_json(force=True)
    if not data or "message" not in data:
        return jsonify({"error": "missing 'message' field"}), 400
    cfg = load_config()
    provider = data.get("provider") or cfg.get("provider") or "openai"
    try:
        client = _build_client(provider, data.get("model"), cfg.get("providers", {}))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    messages = _build_messages(data)

    def event_stream():
        try:
            for tok in client.stream_chat(messages):
                if tok is None:
                    continue
                yield f"data: {json.dumps(str(tok))}\n\n"
            yield "event: done\ndata: {}\n\n"
        except Exception as e:
            yield f"event: error\ndata: {json.dumps(str(e))}\n\n"

    return Response(stream_with_context(event_stream()), mimetype="text/event-stream")


def run(host="127.0.0.1", port=5000, open_browser=True):
    if open_browser:
        threading.Timer(0.9, lambda: webbrowser.open(f"http://{host}:{port}")).start()
    app.run(host=host, port=port, debug=False)


if __name__ == "__main__":
    run()
