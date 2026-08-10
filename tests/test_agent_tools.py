"""Unit tests for the agentic tool set (edit, search, fetch, git)."""

from types import SimpleNamespace

from tools import registry
from tools.file_tool import edit_file, read_file
from tools.grep_tool import grep_code
from tools.search_tool import fetch_url


# ---------------------------------------------------------------------------
# edit_file / read_file
# ---------------------------------------------------------------------------


def test_edit_file_first_occurrence(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello world\nhello again\n")

    res = edit_file(str(f), "hello world", "HELLO WORLD")
    assert '"ok": true' in res and '"replacements": 1' in res
    assert read_file(str(f)) == "HELLO WORLD\nhello again\n"


def test_edit_file_ambiguous_fails(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("HELLO world\nHELLO again\n")

    res = edit_file(str(f), "HELLO", "X")
    assert "occurs 2 times" in res
    assert read_file(str(f)).count("HELLO") == 2  # untouched


def test_edit_file_replace_all(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("a,b,a,c,a\n")

    res = edit_file(str(f), "a", "z", replace_all=True)
    assert '"replacements": 3' in res
    assert read_file(str(f)) == "z,b,z,c,z\n"


def test_edit_file_not_found(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello\n")
    assert "not found" in edit_file(str(f), "nope", "x")
    assert "not found" in edit_file(str(tmp_path / "missing.txt"), "x", "y")


def test_read_file_line_window(tmp_path):
    f = tmp_path / "big.txt"
    f.write_text("\n".join(f"line {i}" for i in range(1, 101)))

    out = read_file(str(f), offset=10, limit=3)
    assert "lines 10-12" in out
    assert "line 10" in out and "line 12" in out and "line 13" not in out


def test_read_file_refuses_huge_file(tmp_path, monkeypatch):
    f = tmp_path / "huge.txt"
    f.write_text("x" * 4096)
    monkeypatch.setattr("tools.file_tool.MAX_FILE_READ", 1024)
    out = read_file(str(f))
    assert "too large" in out


# ---------------------------------------------------------------------------
# grep_code
# ---------------------------------------------------------------------------


def test_grep_code_finds_matches_and_skips_junk(tmp_path):
    sub = tmp_path / "src"
    sub.mkdir()
    (sub / "a.py").write_text("def foo():\n    return 1\n")
    (sub / "b.py").write_text("x = 1\n")

    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "junk.js").write_text("def foo():\n")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "lib.py").write_text("def foo():\n")
    (sub / ".hidden.py").write_text("def foo():\n")

    results = grep_code("def foo", str(tmp_path))
    assert len(results) == 1
    assert "a.py:1" in results[0]


def test_grep_code_invalid_regex(tmp_path):
    results = grep_code("(unclosed", str(tmp_path))
    assert any('"error"' in r for r in results)


def test_grep_code_missing_path(tmp_path):
    results = grep_code("foo", str(tmp_path / "nope"))
    assert any('"error"' in r for r in results)


# ---------------------------------------------------------------------------
# fetch_url
# ---------------------------------------------------------------------------


def test_fetch_url_strips_html(monkeypatch):
    class FakeResp:
        headers = {"Content-Type": "text/html"}
        content = (
            b"<html><head><script>var x = 1;</script></head>"
            b"<body><h1>Title</h1><p>Hello <b>world</b></p></body></html>"
        )

        def raise_for_status(self):
            pass

    monkeypatch.setattr("tools.search_tool.requests.get", lambda *a, **k: FakeResp())
    text = fetch_url("https://example.com")
    assert "Title" in text
    assert "Hello world" in text
    assert "var x" not in text


def test_fetch_url_rejects_non_http(monkeypatch):
    assert "http(s)" in fetch_url("file:///etc/passwd")


def test_fetch_url_error_surfaces(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("connection reset")

    monkeypatch.setattr("tools.search_tool.requests.get", boom)
    assert "connection reset" in fetch_url("https://example.com")


# ---------------------------------------------------------------------------
# git_status
# ---------------------------------------------------------------------------


def _git_result(returncode, stdout):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr="")


def test_git_status_reads_repo_state(monkeypatch, tmp_path):
    import tools.git_tool as gt

    def fake_run(args, **kwargs):
        if "rev-parse" in args:
            return _git_result(0, "main\n")
        if "status" in args:
            return _git_result(0, " M foo.py\n?? new.txt\n")
        return _git_result(0, "abc123 2026-08-10 init commit\n")

    monkeypatch.setattr(gt.subprocess, "run", fake_run)
    res = gt.git_status(str(tmp_path))
    assert res["branch"] == "main"
    assert res["changes"] == [" M foo.py", "?? new.txt"]
    assert res["recent_commits"] == ["abc123 2026-08-10 init commit"]


def test_git_status_not_a_repo(monkeypatch, tmp_path):
    import tools.git_tool as gt

    monkeypatch.setattr(
        gt.subprocess, "run", lambda *a, **k: _git_result(128, "")
    )
    res = gt.git_status(str(tmp_path))
    assert "error" in res


# ---------------------------------------------------------------------------
# Registry hardening
# ---------------------------------------------------------------------------


def test_tool_output_truncation_is_marked(monkeypatch):
    monkeypatch.setattr(registry, "MAX_TOOL_OUTPUT", 50)
    registry.TOOL_SPECS["_test_huge"] = registry._spec(
        "_test_huge",
        "test",
        {"type": "object", "properties": {}, "required": []},
        lambda: "z" * 500,
    )
    try:
        ok, text = registry.execute_tool("_test_huge", {})
        assert ok is True
        assert "truncated" in text
        assert len(text) < 200
    finally:
        del registry.TOOL_SPECS["_test_huge"]


def test_registry_exposes_new_tools():
    names = set(registry.tool_names())
    assert {
        "edit_file",
        "grep_code",
        "fetch_url",
        "git_status",
    } <= names
