#!/usr/bin/env python3
"""OIDA for Claude — cross-OS/WSL discovery of local Claude data sources.

Ported ~verbatim from control8's ctrl8 `sources.py` (single source of truth for
where Claude Code writes transcripts). Pure assembly functions (testable with
injected inputs) + thin public wrappers that wire the real environment. No
third-party deps. `--self-test` checks the pure branches.

Claude Code CLI transcripts: `<home>/.claude/projects` on all platforms, plus the
Windows-side root under `/mnt/c/Users/<W>` when running in WSL2.

Cowork (Claude Desktop agent-mode) discovery is kept for parity, but OIDA client
v1 is repo-scoped and ingests only CLI sessions — repo-less Cowork chats are out
of v1 (at KVA they arrive via the control8 connector instead).
"""
import argparse, os, sys, glob as _glob, subprocess

SYSTEM_PROFILES = {"Default", "Default User", "Public", "All Users", "desktop.ini",
                   "Administrator", "WDAGUtilityAccount"}
MSIX_GLOB = os.path.join("AppData", "Local", "Packages", "Claude_*", "LocalCache", "Roaming", "Claude")


def detect_wsl():
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    for p in ("/proc/sys/kernel/osrelease", "/proc/version"):
        try:
            with open(p, encoding="utf-8", errors="ignore") as f:
                if "microsoft" in f.read().lower():
                    return True
        except OSError:
            pass
    return False


def windows_user_profiles(run=subprocess.run, listdir=os.listdir, isdir=os.path.isdir):
    """The CURRENT Windows user's `/mnt/c/Users/<W>` (privacy: never read several users' data)."""
    for cmd in (["powershell.exe", "-NoProfile", "-Command", "$env:USERPROFILE"],
                ["cmd.exe", "/c", "echo %USERPROFILE%"]):
        try:
            r = run(cmd, capture_output=True, text=True, timeout=8, cwd="/mnt/c")
            lines = [line.strip() for line in (r.stdout or "").splitlines() if line.strip()]
            prof = lines[-1] if lines else ""
            if prof[:9].lower() == "c:\\users\\":
                user = prof.split("\\")[2]
                if user:
                    return ["/mnt/c/Users/" + user]
        except Exception:
            pass
    base = "/mnt/c/Users"
    if not isdir(base):
        return []
    try:
        names = [n for n in listdir(base) if n not in SYSTEM_PROFILES and isdir(os.path.join(base, n))]
    except OSError:
        return []
    me = (os.environ.get("USER") or "").lower()
    match = [n for n in names if n.lower() == me]
    if match:
        return [os.path.join(base, match[0])]

    def _has_claude(n):
        p = os.path.join(base, n)
        return isdir(os.path.join(p, ".claude")) or \
            isdir(os.path.join(p, "AppData", "Roaming", "Claude", "local-agent-mode-sessions"))
    with_data = [n for n in names if _has_claude(n)]
    if len(with_data) == 1:
        return [os.path.join(base, with_data[0])]
    if len(names) == 1:
        return [os.path.join(base, names[0])]
    return []  # genuinely ambiguous -> skip the Windows side


def assemble_cli_roots(home, is_wsl, win_profiles):
    roots = [os.path.join(home, ".claude", "projects")]
    if is_wsl:
        roots += [os.path.join(w, ".claude", "projects") for w in win_profiles]
    return roots


def _existing(paths, exists=os.path.exists):
    return [p for p in paths if exists(p)]


def claude_code_roots():
    is_wsl = detect_wsl()
    wp = windows_user_profiles() if is_wsl else []
    return _existing(assemble_cli_roots(os.path.expanduser("~"), is_wsl, wp))


def describe():
    return {"is_wsl": detect_wsl(), "platform": sys.platform, "cli_roots": claude_code_roots()}


def _self_test():
    assert assemble_cli_roots("/home/bob", False, []) == ["/home/bob/.claude/projects"]
    wsl_cli = assemble_cli_roots("/home/bob", True, ["/mnt/c/Users/bob"])
    assert wsl_cli == ["/home/bob/.claude/projects", "/mnt/c/Users/bob/.claude/projects"], wsl_cli

    class _R:  # noqa
        stdout = "C:\\Users\\alice\r\n"
    assert windows_user_profiles(run=lambda *a, **k: _R()) == ["/mnt/c/Users/alice"]

    def _boom(*a, **k):
        raise OSError("no powershell")
    _prev_user = os.environ.get("USER")
    os.environ["USER"] = "__nomatch__"
    try:
        assert windows_user_profiles(run=_boom, listdir=lambda b: ["Default", "carol"],
                                     isdir=lambda p: True) == ["/mnt/c/Users/carol"]
        assert windows_user_profiles(run=_boom, listdir=lambda b: ["alice", "bob"],
                                     isdir=lambda p: True) == []
    finally:
        if _prev_user is None:
            os.environ.pop("USER", None)
        else:
            os.environ["USER"] = _prev_user
    print("OK self-test: sources (cli roots / win-user resolution)")


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args(argv)
    if args.self_test:
        _self_test()
        return 0
    import json
    print(json.dumps(describe(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
