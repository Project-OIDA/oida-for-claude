#!/usr/bin/env python3
"""OIDA for Claude — Claude Code session JSONL -> transcript {turns, tool_calls}.

Deliberate reduction (session-ingestion plan): every user/assistant turn verbatim
(redacted) + a tool-call LOG (tool name + redacted, truncated input). `tool_result`
bodies are dropped — ~90% of transcript bytes and the biggest secret-leak surface.
Every string is passed through redact() before it leaves this module. Tolerant:
an unparseable line is skipped, never fatal (unknown schema -> skip, never crash).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from redact import redact  # noqa: E402

MAX_TOOL_INPUT = 2000  # a redacted tool input is provenance, not payload — truncate hard.


def _text_of(content):
    """A message `content` is a string or a list of typed parts; return the
    concatenated text-part text only."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = [p["text"] for p in content
               if isinstance(p, dict) and p.get("type") == "text" and isinstance(p.get("text"), str)]
        return "\n".join(out)
    return ""


def _tool_uses(content):
    if not isinstance(content, list):
        return []
    calls = []
    for part in content:
        if isinstance(part, dict) and part.get("type") == "tool_use":
            raw = part.get("input")
            inp = json.dumps(raw, ensure_ascii=False) if raw is not None else None
            calls.append((str(part.get("name") or "tool"), inp))
    return calls


def parse_lines(lines):
    """Core parser over an iterable of JSONL strings (testable without a file)."""
    turns, tool_calls = [], []
    for line in lines:
        line = (line or "").strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue  # unknown/partial line -> skip, never crash
        msg = obj.get("message") if isinstance(obj, dict) else None
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        ts = obj.get("timestamp") if isinstance(obj.get("timestamp"), str) else None
        content = msg.get("content")
        text = _text_of(content).strip()
        if text:
            turn = {"role": role, "text": redact(text)}
            if ts:
                turn["at"] = ts
            turns.append(turn)
        for name, inp in _tool_uses(content):  # tool_result parts are ignored here
            call = {"name": name}
            if inp:
                call["input"] = redact(inp)[:MAX_TOOL_INPUT]
            if ts:
                call["at"] = ts
            tool_calls.append(call)
    return {"turns": turns, "tool_calls": tool_calls}


def parse_transcript(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return parse_lines(f)
    except OSError:
        return {"turns": [], "tool_calls": []}


def _self_test():
    lines = [
        json.dumps({"timestamp": "2026-07-21T10:00:00Z", "message": {"role": "user", "content": "Ship the sessions connector"}}),
        json.dumps({"message": {"role": "assistant", "content": [
            {"type": "text", "text": "On it."},
            {"type": "tool_use", "name": "Bash", "input": {"cmd": "export TOKEN=ghp_0123456789abcdefghijklmnopqrstuvwxyz"}},
        ]}}),
        json.dumps({"message": {"role": "user", "content": [
            {"type": "tool_result", "content": "SECRET OUTPUT sk-ant-api03-shouldnotappear"},
        ]}}),
        "not json at all",
        json.dumps({"type": "summary", "summary": "meta line, no message"}),
    ]
    out = parse_lines(lines)
    assert [t["role"] for t in out["turns"]] == ["user", "assistant"], out["turns"]
    assert out["turns"][0]["text"] == "Ship the sessions connector"
    assert out["tool_calls"][0]["name"] == "Bash"
    # the secret is gone and a redaction marker is present (which specific marker
    # wins depends on pattern order — what matters is the token never survives)
    assert "ghp_0123456789" not in out["tool_calls"][0]["input"], out["tool_calls"][0]
    assert "«redacted" in out["tool_calls"][0]["input"], out["tool_calls"][0]
    # tool_result body is dropped entirely — its secret never reaches the envelope
    blob = json.dumps(out)
    assert "sk-ant-api03-shouldnotappear" not in blob and "SECRET OUTPUT" not in blob
    print("OK self-test: transcript (turns / tool_calls / tool_result dropped / redacted)")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        _self_test()
    else:
        print(json.dumps(parse_transcript(sys.argv[1]), indent=2))
