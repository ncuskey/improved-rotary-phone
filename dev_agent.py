#!/usr/bin/env python3
import os, sys, time, json, shutil, tempfile, textwrap, glob
from pathlib import Path

# --- Key loading helpers (macOS Keychain fallback) ---
import subprocess, shlex
from datetime import datetime

def load_key_from_keychain(name: str) -> str:
    try:
        out = subprocess.check_output(
            ["security", "find-generic-password", "-a", os.environ.get("USER",""), "-s", name, "-w"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return out
    except Exception:
        return ""

# Auto-populate env from Keychain if missing
for env_name in ("OPENAI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY"):
    if not os.environ.get(env_name):
        val = load_key_from_keychain(env_name)
        if val:
            os.environ[env_name] = val

# Logging / verbosity
VERBOSITY = int(os.environ.get("AGENT_VERBOSITY", "1"))
LOG_DIR = Path(".agent_logs"); LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "agent_run.log"; LOG_FILE.touch(exist_ok=True)
os.environ.setdefault("OLLAMA_KEEP_ALIVE", "5m")

def vprint(level, *args):
    global VERBOSITY
    if VERBOSITY >= level:
        print(*args)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as lf:
        lf.write(f"[{ts}] " + " ".join(map(str, args)) + "\n")

# -------- Config (edit as needed) --------
REPO = Path.cwd()
BACKUP_DIR = REPO/".agent_backups"
MAX_STEPS = 10
MAX_TOKENS_PER_STEP = 1200
MAX_USD = 0.50
MAX_SECS = 600
ALLOW_GLOBS = [
    "web/**",
    "ios/**",
    "server/**",
    "tests/**"
]
DENY_GLOBS  = ["**/node_modules/**","**/.git/**","**/.venv/**","**/build/**","**/dist/**"]
ALLOWED_EXTS = {".py",".java",".swift",".js",".ts",".tsx",".md",".json",".yml",".yaml",".html",".css"}

# Pricing for cost printouts ($ per 1K tokens)
OPENAI_IN, OPENAI_OUT = 0.01, 0.03           # GPT-4o (adjust to match your plan)
GEMINI_IN, GEMINI_OUT = 0.00125, 0.01        # Gemini 2.5 Pro
ANTH_IN,   ANTH_OUT   = 0.001,   0.005       # Claude Haiku

# Local models
LOCAL_FAST  = ("ollama", "deepseek-coder-v2:lite")
LOCAL_HEAVY = ("ollama", "phind-codellama:34b-q4_0")

# Cloud models (dynamic based on available keys)
CLOUD_ORDER = []
if os.environ.get("GOOGLE_API_KEY"):
    CLOUD_ORDER.append(("gemini", "gemini-2.5-pro"))
if os.environ.get("ANTHROPIC_API_KEY"):
    CLOUD_ORDER.append(("anthropic", "claude-3-5-haiku-latest"))
if os.environ.get("OPENAI_API_KEY"):
    # Prefer gpt-4o for reliability; replace with gpt-4.1 if you like
    CLOUD_ORDER.append(("openai", "gpt-4o"))

# -------- Helpers --------
def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, text=True, capture_output=True, **kw)

def matches_any_rel(path: Path, patterns, base: Path) -> bool:
    import fnmatch, os
    try:
        rel = path.relative_to(base).as_posix()
    except Exception:
        rel = os.path.relpath(path.as_posix(), base.as_posix())
    return any(fnmatch.fnmatch(rel, pat) for pat in patterns)

def list_files():
    files = []
    for p in glob.glob("**/*", recursive=True):
        path = Path(p)
        if not path.is_file():
            continue
        if matches_any_rel(path.resolve(), ALLOW_GLOBS, REPO) and not matches_any_rel(path.resolve(), DENY_GLOBS, REPO):
            files.append(path)
    return files

def find_files(patterns):
    """Locate files whose basename matches any of the provided patterns."""
    import fnmatch
    hits = []
    for p in REPO.rglob("*"):
        if p.is_file() and any(fnmatch.fnmatch(p.name.lower(), pat) for pat in patterns):
            hits.append(p)
    return hits

def read_clip(path: Path, max_bytes=20000):
    try:
        data = path.read_bytes()
        return data[:max_bytes].decode("utf-8", errors="ignore")
    except Exception:
        return ""

def rg(query):
    return sh(f"rg -n --hidden --glob '!node_modules' {json.dumps(query)}").stdout.strip()

def backup(path: Path):
    BACKUP_DIR.mkdir(exist_ok=True)
    dest = BACKUP_DIR / (path.as_posix().replace("/", "_") + f".bak.{int(time.time())}")
    if path.exists():
        shutil.copy2(path, dest)
    return dest

def write_file(path: Path, content: str):
    backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def read_file(path: Path):
    return path.read_text(encoding="utf-8") if path.exists() else ""

def run_validator():
    """Run the repository's primary test suite."""
    r = sh("pytest -q", cwd=str(REPO))
    return r.returncode == 0, r.stdout + r.stderr

# -------- Model calls + routing --------
COST_LOG = []  # list of (label, secs, usd)

def log_cost(label, t0, t1, tokens_in=0, tokens_out=0, price=(0,0)):
    secs = int(t1 - t0)
    cost = (tokens_in/1000.0)*price[0] + (tokens_out/1000.0)*price[1]
    COST_LOG.append((label, secs, round(cost,6)))

def call_ollama(model, prompt):
    t0 = time.time()
    # positional prompt, widest compatibility
    r = sh(f"printf %s {json.dumps(prompt)} | ollama run {model}")
    t1 = time.time()
    # no token accounting locally
    log_cost(f"Ollama {model}", t0, t1, 0, 0, (0,0))
    return r.stdout.strip()

def call_gemini(model, prompt):
    import google.generativeai as genai
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    t0 = time.time()
    resp = genai.GenerativeModel(model).generate_content(prompt)
    t1 = time.time()
    # token usage fields:
    p = getattr(resp, "usage_metadata", None)
    tokens_in  = getattr(p, "prompt_token_count", 0) if p else 0
    tokens_out = getattr(p, "candidates_token_count", 0) if p else 0
    log_cost(f"Gemini {model}", t0, t1, tokens_in, tokens_out, (GEMINI_IN, GEMINI_OUT))
    return resp.text or ""

def call_openai(model, prompt):
    from openai import OpenAI
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    t0 = time.time()
    r = client.chat.completions.create(
        model=model,
        temperature=0.1,
        max_tokens=MAX_TOKENS_PER_STEP,
        messages=[{"role":"user","content":prompt}]
    )
    t1 = time.time()
    usage = r.usage or {}
    tokens_in = getattr(usage, "prompt_tokens", 0) or 0
    tokens_out = getattr(usage, "completion_tokens", 0) or 0
    log_cost(f"OpenAI {model}", t0, t1, tokens_in, tokens_out, (OPENAI_IN, OPENAI_OUT))
    return r.choices[0].message.content.strip()

def call_anthropic(model, prompt):
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    t0 = time.time()
    r = client.messages.create(model=model, max_tokens=MAX_TOKENS_PER_STEP, temperature=0.1,
                               messages=[{"role":"user","content":prompt}])
    t1 = time.time()
    usage = getattr(r, "usage", None) or {}
    tokens_in  = getattr(usage, "input_tokens", 0) or 0
    tokens_out = getattr(usage, "output_tokens", 0) or 0
    log_cost(f"Anthropic {model}", t0, t1, tokens_in, tokens_out, (ANTH_IN, ANTH_OUT))
    return "".join([b.text for b in r.content if getattr(b, "type", "")=="text"])

def strip_fences(text: str) -> str:
    """Remove any markdown code fences."""
    lines = []
    for ln in text.splitlines():
        if ln.strip().startswith("```"):
            continue
        lines.append(ln)
    return "\n".join(lines).strip()

def extract_json(s: str):
    """Attempt to parse JSON (handles fenced output)."""
    s = strip_fences(s)
    try:
        return json.loads(s)
    except Exception:
        pass
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(s[start:end+1])
        except Exception:
            return None
    return None

def goal_prefers_gemini(goal: str) -> bool:
    g = goal.lower()
    return any(k in g for k in ["java", "swift", "ios", "xcode", "multifile", "refactor", "migration"])

def git_commit(files):
    """Stage and commit touched files."""
    rels = []
    for f in files:
        try:
            rels.append(str(Path(f).resolve().relative_to(REPO)))
        except Exception:
            rels.append(str(Path(f)))
    if not rels:
        return
    sh("git add " + " ".join(shlex.quote(r) for r in rels), cwd=str(REPO))
    sh('git commit -m "agent: apply palindrome fixes across languages"', cwd=str(REPO))

def choose_model(prompt, failure_text):
    if goal_prefers_gemini(prompt) and os.environ.get("GOOGLE_API_KEY"):
        vprint(1, "[choose] java/swift/multifile → start on Gemini")
        return ("gemini", "gemini-2.5-pro")
    vprint(1, f"[choose] start model: ollama:{LOCAL_FAST[1]}")
    return ("ollama", LOCAL_FAST[1])

def next_rung(current):
    seq = [("ollama", LOCAL_FAST[1]), ("ollama", LOCAL_HEAVY[1])] + CLOUD_ORDER
    try:
        idx = seq.index(current)
    except ValueError:
        # If current not in sequence, start at first available cloud or None
        return CLOUD_ORDER[0] if CLOUD_ORDER else None
    nxt_idx = idx + 1
    return seq[nxt_idx] if nxt_idx < len(seq) else None

# -------- Agent loop --------
PLAN_SYS = """You are a senior software engineer acting as an autonomous agent.
Return JSON ONLY (no prose, no fences) with keys: plan (list of strings), edits (list), validation (string).
All file paths MUST be inside agent_demo/ and use these exact names if they exist:
- agent_demo/app.py
- agent_demo/test_app.py
- agent_demo/Main.java
- agent_demo/main.swift
- agent_demo/app.js

Keep existing function names and signatures. Do not remove unrelated functions or endpoints. Prefer minimal diffs that address the goal.

Edits MUST be full-file replaces: {"path":"<path>","action":"replace","full_text":"<entire file content>"}.
Validation MUST be a single shell command or leave empty to use built-in validator.
"""

def llm(provider, model, prompt):
    prompt = textwrap.dedent(prompt)
    vprint(1, f"[call] provider={provider} model={model}")
    if VERBOSITY >= 3:
        vprint(3, f"[prompt-preview] {prompt[:800]}{' ...' if len(prompt) > 800 else ''}")
    else:
        with LOG_FILE.open("a", encoding="utf-8") as lf:
            lf.write("[prompt]\n")
            lf.write(prompt)
            lf.write("\n\n")
    if provider == "ollama":
        resp = call_ollama(model, prompt)
    elif provider == "gemini":
        resp = call_gemini(model, prompt)
    elif provider == "openai":
        resp = call_openai(model, prompt)
    elif provider == "anthropic":
        resp = call_anthropic(model, prompt)
    else:
        raise ValueError("unknown provider")
    if VERBOSITY >= 3:
        vprint(3, f"[raw-output-preview] {resp[:800]}{' ...' if len(resp) > 800 else ''}")
    else:
        with LOG_FILE.open("a", encoding="utf-8") as lf:
            lf.write("[raw]\n")
            lf.write(resp)
            lf.write("\n\n")
    return resp

def run_agent(goal: str):
    REPO.mkdir(exist_ok=True)
    BACKUP_DIR.mkdir(exist_ok=True)
    COST_LOG.clear()
    start_time = time.time()

    def over_budget():
        total_cost = sum(c for *_, c in COST_LOG)
        return total_cost > MAX_USD or (time.time() - start_time) > MAX_SECS

    vprint(1, "🟢 Agent starting")
    vprint(2, f"Goal: {goal}")

    failure = ""
    step = 0
    current = choose_model(goal, failure)
    touched = set()

    while step < MAX_STEPS:
        step += 1
        swift_hits = find_files(["*probab*.*swift*", "*score*.*swift*", "main.swift"])
        web_hits = find_files(["*probab*.*js", "*probab*.*ts*", "*score*.*js", "*score*.*ts*"])
        context_blobs = []
        for p in (swift_hits[:3] + web_hits[:3]):
            context_blobs.append(f"--- {p}\n{read_clip(p)}\n")
        context = "\n".join(context_blobs) if context_blobs else ""

        prompt = PLAN_SYS + "\nGOAL:\n" + goal
        if failure:
            prompt += "\n\nRECENT_FEEDBACK:\n" + failure
        if context:
            prompt += "\n\nREADONLY CONTEXT (do NOT modify these):\n" + context

        raw = llm(*current, prompt=prompt) if False else llm(current[0], current[1], prompt)
        if COST_LOG:
            label, secs, usd = COST_LOG[-1]
        else:
            label = f"{current[0]}:{current[1]}"
            secs = 0
            usd = 0.0
        vprint(1, f"[step] {label} took {secs}s, cost ${usd}")
        if over_budget():
            vprint(1, "⛔ Budget/time cap hit")
            break
        obj = extract_json(raw)
        if not obj:
            nxt = next_rung(current)
            if nxt:
                vprint(1, f"⤴️ Escalating to {nxt[0]}:{nxt[1]} (parse)")
                current = nxt
                continue
            vprint(1, "⛔ No further rungs; parse failed")
            break
        if not isinstance(obj, dict):
            nxt = next_rung(current)
            if nxt:
                vprint(1, f"⤴️ Escalating to {nxt[0]}:{nxt[1]} (parse-type)")
                current = nxt
                continue
            vprint(1, "⛔ No further rungs; non-object response")
            break

        plan = obj.get("plan", [])
        # apply edits
        edits = obj.get("edits", [])
        if not isinstance(edits, list):
            edits = []
        vprint(2, f"[plan] {plan}")
        if edits:
            vprint(2, f"[edits] {len(edits)} file(s): " + ", ".join(e.get("path","?") for e in edits))
        else:
            vprint(2, "[edits] none proposed")
        seen = set()
        for e in edits:
            raw_path = e.get("path", "")
            if raw_path in seen:
                vprint(2, f"[skip] duplicate edit for {raw_path}")
                continue
            seen.add(raw_path)
            path = (REPO / raw_path).resolve()
            if path.name in {"app.py","test_app.py","Main.java","main.swift","app.js"} and "agent_demo" not in path.as_posix():
                path = (REPO / "agent_demo" / path.name).resolve()

            allowed = matches_any_rel(path, ALLOW_GLOBS, REPO)
            denied = matches_any_rel(path, DENY_GLOBS, REPO)
            if not allowed or denied:
                vprint(2, f"[skip] not allowed: {path}")
                continue
            if Path(path).suffix not in ALLOWED_EXTS:
                vprint(2, f"[skip] extension not allowed: {path}")
                continue

            if e.get("action") == "replace" and "full_text" in e and e["full_text"].strip():
                vprint(2, f"[write] {path}")
                write_file(path, strip_fences(e["full_text"]))
                touched.add(str(path))
            else:
                vprint(2, f"[skip] missing full_text/action for {path}")

        # run validation (either provided or our default)
        cmd = obj.get("validation") or ""
        if cmd.strip():
            vprint(1, f"[validate] running: {cmd}")
            res = sh(cmd)
            ok_ = res.returncode == 0
            output = res.stdout + res.stderr
        else:
            vprint(1, "[validate] using built-in validator")
            ok_, output = run_validator()

        tail = output[-1200:] if output else ""
        if ok_:
            vprint(1, "✅ Validation PASSED")
            if tail:
                vprint(3, f"[validation-output]\n{tail}")
            if touched:
                git_commit(sorted(touched))
            break
        else:
            vprint(1, "⚠ Validation FAILED")
            if tail:
                vprint(2, f"[validation-tail]\n{tail}")
            failure = output[-4000:]  # feed back tail of failure
            # escalate rung
            nxt = next_rung(current)
            if nxt:
                vprint(1, f"⤴️ Escalating to {nxt[0]}:{nxt[1]}")
                current = nxt
            else:
                vprint(1, "⛔ No further rungs available")
                break

    # Summary
    print("\n— Agent Summary —")
    for label, secs, usd in COST_LOG:
        print(f"{label:<28}  {secs:>5}s   ${usd:>8}")
    total_secs = sum(s for _,s,_ in COST_LOG)
    total_cost = round(sum(c for *_, c in COST_LOG), 6)
    print(f"{'TOTAL':<28}  {total_secs:>5}s   ${total_cost:>8}")
    print("Files touched:", sorted(touched))

# --------- main ----------
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Local→Cloud dev agent")
    parser.add_argument("goal", help="What you want the agent to do")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="-v (info), -vv (debug), -vvv (trace)")
    args = parser.parse_args()
    VERBOSITY = max(1, min(3, args.verbose or VERBOSITY))
    vprint(1, f"Verbosity level = {VERBOSITY}")
    run_agent(args.goal)
