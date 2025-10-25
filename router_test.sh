#!/usr/bin/env bash
set -euo pipefail

# =======================
# CONFIG — edit if needed
# =======================
LOCAL_FAST_MODEL="deepseek-coder-v2:lite"
LOCAL_HEAVY_MODEL="phind-codellama:34b-q4_0"
USE_GEMINI=1
USE_ANTHROPIC=1
USE_OPENAI=1

# --- Pricing (edit to match your billing plan) ---
# All per 1K tokens (USD)
OPENAI_IN=0.01;      OPENAI_OUT=0.03          # GPT-4 Turbo
GEMINI_IN=0.00125;   GEMINI_OUT=0.01          # Gemini 2.5 Pro
ANTHROPIC_IN=0.001;  ANTHROPIC_OUT=0.005      # Claude 3.5 Haiku

# Workspace
WORKDIR="$(pwd)/router_demo"
FAIL_LOG="$WORKDIR/last_failure.txt"
LANG="python"  # default; override with -l
MAX_LOCAL_ATTEMPTS_FAST=2
MAX_LOCAL_ATTEMPTS_HEAVY=1

# Verbosity
VERBOSE="${VERBOSE:-0}"
vprint() {
  local lvl="${1:-1}"
  shift
  if [ "$VERBOSE" -ge "$lvl" ]; then
    printf "%s\n" "$*"
  fi
}

# =======================
# Helpers
# =======================
say()  { printf "\n\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "\033[32m✔ %s\033[0m\n" "$*"; }
warn() { printf "\033[33m⚠ %s\033[0m\n" "$*"; }
fail() { printf "\033[31m✘ %s\033[0m\n" "$*"; }
have(){ command -v "$1" >/dev/null 2>&1; }
secs() { date +%s; }

# Timings / cost
declare -a LOG_STEP LOG_TIME LOG_COST
log_add() {
  local label="$1" dur="$2" cost="$3"
  LOG_STEP+=("$label"); LOG_TIME+=("$dur"); LOG_COST+=("$cost")
}

# Auto-load keys from Keychain if absent
: "${OPENAI_API_KEY:=$(security find-generic-password -a "$USER" -s OPENAI_API_KEY -w 2>/dev/null || true)}"
: "${GOOGLE_API_KEY:=$(security find-generic-password -a "$USER" -s GOOGLE_API_KEY -w 2>/dev/null || true)}"
: "${ANTHROPIC_API_KEY:=$(security find-generic-password -a "$USER" -s ANTHROPIC_API_KEY -w 2>/dev/null || true)}"

usage() {
  cat <<USAGE
Usage: $(basename "$0") [-l python|java|swift|js]

Runs local→local-heavy→cloud ladder and prints time & cost per step.
USAGE
}

# =======================
# Sample problems + validators per language
# =======================
init_repo_python() {
  mkdir -p "$WORKDIR"
  cat > "$WORKDIR/app.py" <<'PY'
def is_palindrome(s: str) -> bool:
    """
    Return True if s is a palindrome (ignoring case and non-alphanumerics).
    BUG: this implementation is wrong on punctuation/mixed case.
    """
    return s == s[::-1]
PY
  cat > "$WORKDIR/test_app.py" <<'PY'
import sys, importlib.util, pathlib, traceback
p = pathlib.Path(__file__).parent / "app.py"
spec = importlib.util.spec_from_file_location("app", str(p))
app = importlib.util.module_from_spec(spec); spec.loader.exec_module(app)

def run_tests():
    assert app.is_palindrome("racecar") is True
    assert app.is_palindrome("RaceCar") is True
    assert app.is_palindrome("A man, a plan, a canal: Panama!") is True
    assert app.is_palindrome("hello") is False
    assert app.is_palindrome("No 'x' in Nixon") is True

if __name__ == "__main__":
    try:
        run_tests()
        print("ALL_PASS")
    except Exception:
        traceback.print_exc()
        print("FAIL")
        sys.exit(1)
PY
}

validate_python() {
  python "$WORKDIR/test_app.py" > /dev/null 2> "$FAIL_LOG"
}

mk_prompt_python() {
  local CURRENT="$1" FEEDBACK="$2"
  cat <<PROMPT
You are a senior software engineer. Fix the bug in the Python file below so that all tests pass.
Return ONLY the corrected file content for app.py with no fences, no prose — just the code.

### app.py
${CURRENT}

### Requirements
- Normalize to case-insensitive
- Ignore all non-alphanumeric characters
- Keep the same function name and signature
- Be clear and efficient
$( [ -n "$FEEDBACK" ] && printf "\n### Test feedback\n%s\n" "$FEEDBACK" )
PROMPT
}

# --- Java ---
init_repo_java() {
  mkdir -p "$WORKDIR"
  cat > "$WORKDIR/Main.java" <<'JAVA'
public class Main {
    public static boolean isPalindrome(String s) {
        // BUG: case-sensitive and doesn't strip non-alphanumerics
        String rev = new StringBuilder(s).reverse().toString();
        return s.equals(rev);
    }
    public static void main(String[] args) {
        if (!isPalindrome("racecar")) System.exit(1);
        if (!isPalindrome("RaceCar")) System.exit(1);
        if (!isPalindrome("A man, a plan, a canal: Panama!")) System.exit(1);
        if (isPalindrome("hello")) System.exit(1);
        if (!isPalindrome("No 'x' in Nixon")) System.exit(1);
        System.out.println("ALL_PASS");
    }
}
JAVA
}
validate_java() {
  pushd "$WORKDIR" >/dev/null
  if ! javac Main.java 2> "$FAIL_LOG"; then popd >/dev/null; return 1; fi
  if ! java Main > /dev/null 2>> "$FAIL_LOG"; then popd >/dev/null; return 1; fi
  popd >/dev/null
}
mk_prompt_java() {
  local CURRENT="$1" FEEDBACK="$2"
  cat <<PROMPT
Fix the Java class below so all checks in main() pass.
Return ONLY the corrected file content for Main.java with no fences, no prose.

### Main.java
${CURRENT}

### Requirements
- Case-insensitive palindrome
- Ignore non-alphanumeric characters
- Keep class name Main and method signatures
$( [ -n "$FEEDBACK" ] && printf "\n### Run feedback\n%s\n" "$FEEDBACK" )
PROMPT
}

# --- Swift ---
init_repo_swift() {
  mkdir -p "$WORKDIR"
  cat > "$WORKDIR/main.swift" <<'SWIFT'
import Foundation

func isPalindrome(_ s: String) -> Bool {
    // BUG: doesn't normalize case or strip non-alphanumerics
    return String(s.reversed()) == s
}

func assert(_ cond: Bool) {
    if !cond { exit(1) }
}

assert(isPalindrome("racecar"))
assert(isPalindrome("RaceCar"))
assert(isPalindrome("A man, a plan, a canal: Panama!"))
assert(!isPalindrome("hello"))
assert(isPalindrome("No 'x' in Nixon"))
print("ALL_PASS")
SWIFT
}
validate_swift() {
  pushd "$WORKDIR" >/dev/null
  if ! swiftc main.swift -o .swiftcheck 2> "$FAIL_LOG"; then popd >/dev/null; return 1; fi
  if ! ./.swiftcheck > /dev/null 2>> "$FAIL_LOG"; then popd >/dev/null; return 1; fi
  popd >/dev/null
}
mk_prompt_swift() {
  local CURRENT="$1" FEEDBACK="$2"
  cat <<PROMPT
Fix the Swift file so tests at bottom pass.
Return ONLY the corrected file content for main.swift with no fences, no prose.

### main.swift
${CURRENT}

### Requirements
- Case-insensitive
- Ignore non-alphanumeric characters
- Keep function signature and test structure
$( [ -n "$FEEDBACK" ] && printf "\n### Run feedback\n%s\n" "$FEEDBACK" )
PROMPT
}

# --- JS (Node) ---
init_repo_js() {
  mkdir -p "$WORKDIR"
  cat > "$WORKDIR/app.js" <<'JS'
function isPalindrome(s){
  // BUG: case-sensitive, no filtering
  return s === s.split('').reverse().join('');
}
function assert(cond){ if(!cond) process.exit(1); }
assert(isPalindrome("racecar"));
assert(isPalindrome("RaceCar"));
assert(isPalindrome("A man, a plan, a canal: Panama!"));
assert(!isPalindrome("hello"));
assert(isPalindrome("No 'x' in Nixon"));
console.log("ALL_PASS");
module.exports = { isPalindrome };
JS
}
validate_js() {
  if ! have node; then echo "Node not installed" > "$FAIL_LOG"; return 1; fi
  node "$WORKDIR/app.js" > /dev/null 2> "$FAIL_LOG"
}
mk_prompt_js() {
  local CURRENT="$1" FEEDBACK="$2"
  cat <<PROMPT
Fix the JS file so Node assertions pass.
Return ONLY the corrected file content for app.js with no fences, no prose.

### app.js
${CURRENT}

### Requirements
- Case-insensitive
- Ignore non-alphanumeric characters
- Keep function signature and test structure
$( [ -n "$FEEDBACK" ] && printf "\n### Run feedback\n%s\n" "$FEEDBACK" )
PROMPT
}

# =======================
# Core funcs
# =======================
check_env() {
  have jq || { fail "jq not installed (brew install jq)"; exit 1; }
  have ollama || { fail "ollama not installed"; exit 1; }
  if [ "$USE_OPENAI" -ne 0 ] && [ -z "${OPENAI_API_KEY:-}" ];   then fail "OPENAI_API_KEY not set"; exit 1; fi
  if [ "$USE_GEMINI" -ne 0 ] && [ -z "${GOOGLE_API_KEY:-}" ];   then fail "GOOGLE_API_KEY not set"; exit 1; fi
  if [ "$USE_ANTHROPIC" -ne 0 ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then fail "ANTHROPIC_API_KEY not set"; exit 1; fi
}

validate() {
  case "$LANG" in
    python) validate_python ;;
    java)   validate_java ;;
    swift)  validate_swift ;;
    js)     validate_js ;;
  esac
}

mk_prompt() {
  local CURRENT="$1" FEEDBACK="$2"
  case "$LANG" in
    python) mk_prompt_python "$CURRENT" "$FEEDBACK" ;;
    java)   mk_prompt_java   "$CURRENT" "$FEEDBACK" ;;
    swift)  mk_prompt_swift  "$CURRENT" "$FEEDBACK" ;;
    js)     mk_prompt_js     "$CURRENT" "$FEEDBACK" ;;
  esac
}

init_repo() {
  rm -rf "$WORKDIR"; mkdir -p "$WORKDIR"
  case "$LANG" in
    python) init_repo_python ;;
    java)   init_repo_java ;;
    swift)  init_repo_swift ;;
    js)     init_repo_js ;;
  esac
}

apply_answer() {
  sed -E 's/^```(python|py|java|swift|js)?$//; s/^```$//; s/^```//; s/```$//' | sed $'s/\r$//' > "$1"
}

prompt_fix_local() {
  local model="$1" file="$2" label="$3"
  local CURRENT FEEDBACK INSTR t0 t1
  CURRENT="$(cat "$file")"
  FEEDBACK="$( [ -s "$FAIL_LOG" ] && tail -n 50 "$FAIL_LOG" || true )"
  INSTR="$(mk_prompt "$CURRENT" "$FEEDBACK")"
  say "Ollama → $model"
  t0=$(secs)
  if [ "$VERBOSE" -ge 2 ]; then
    printf "%s\n" "---- prompt (first 40 lines) ----"
    printf "%s\n" "$INSTR" | head -n 40
    echo "----"
  fi
  printf "%s" "$INSTR" | ollama run "$model" | apply_answer "$file"
  t1=$(secs)
  log_add "$label" "$((t1 - t0))" "0"
}

prompt_fix_gemini() {
  local file="$1" label="$2"
  local CURRENT FEEDBACK INSTR t0 t1 prompt out p_tokens c_tokens cost
  CURRENT="$(cat "$file")"
  FEEDBACK="$( [ -s "$FAIL_LOG" ] && tail -n 50 "$FAIL_LOG" || true )"
  INSTR="$(mk_prompt "$CURRENT" "$FEEDBACK")"
  say "Gemini 2.5 Pro (API)"
  t0=$(secs)
  if [ "$VERBOSE" -ge 2 ]; then
    printf "%s\n" "---- prompt (first 40 lines) ----"
    printf "%s\n" "$INSTR" | head -n 40
    echo "----"
  fi
  prompt="$(jq -n --arg t "$INSTR" '{contents:[{parts:[{text:$t}]}]}')"
  out="$(curl -sS -H "Content-Type: application/json" \
      -d "$prompt" \
      "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-pro:generateContent?key=${GOOGLE_API_KEY}")"
  printf "%s" "$out" | jq -r '.candidates[0].content.parts[0].text // ""' | apply_answer "$file"
  t1=$(secs)
  p_tokens=$(printf "%s" "$out" | jq -r '.usageMetadata.promptTokenCount // 0')
  c_tokens=$(printf "%s" "$out" | jq -r '.usageMetadata.candidatesTokenCount // 0')
  # $ = (p/1000)*GEMINI_IN + (c/1000)*GEMINI_OUT
  cost=$(python - <<PY 2>/dev/null || echo "0"
p=$p_tokens; c=$c_tokens
print(round((p/1000.0)*$GEMINI_IN + (c/1000.0)*$GEMINI_OUT, 6))
PY
)
  log_add "$label" "$((t1 - t0))" "$cost"
}

prompt_fix_haiku() {
  local file="$1" label="$2"
  local CURRENT FEEDBACK INSTR t0 t1 out p_tokens c_tokens cost req
  CURRENT="$(cat "$file")"
  FEEDBACK="$( [ -s "$FAIL_LOG" ] && tail -n 50 "$FAIL_LOG" || true )"
  INSTR="$(mk_prompt "$CURRENT" "$FEEDBACK")"
  say "Claude 3.5 Haiku (API)"
  req="$(jq -n --arg p "$INSTR" '{
    model:"claude-3-5-haiku-latest",
    max_tokens:1200,
    temperature:0.1,
    messages:[{role:"user", content:$p}]
  }')"
  t0=$(secs)
  if [ "$VERBOSE" -ge 2 ]; then
    printf "%s\n" "---- prompt (first 40 lines) ----"
    printf "%s\n" "$INSTR" | head -n 40
    echo "----"
  fi
  out="$(curl -sS https://api.anthropic.com/v1/messages \
      -H "x-api-key: $ANTHROPIC_API_KEY" \
      -H "anthropic-version: 2023-06-01" \
      -H "content-type: application/json" \
      -d "$req")"
  printf "%s" "$out" | jq -r '.content[0].text // ""' | apply_answer "$file"
  t1=$(secs)
  p_tokens=$(printf "%s" "$out" | jq -r '.usage.input_tokens // 0')
  c_tokens=$(printf "%s" "$out" | jq -r '.usage.output_tokens // 0')
  cost=$(python - <<PY 2>/dev/null || echo "0"
p=$p_tokens; c=$c_tokens
print(round((p/1000.0)*$ANTHROPIC_IN + (c/1000.0)*$ANTHROPIC_OUT, 6))
PY
)
  log_add "$label" "$((t1 - t0))" "$cost"
}

prompt_fix_openai() {
  local file="$1" label="$2"
  local CURRENT FEEDBACK INSTR t0 t1 out p_tokens c_tokens cost req
  CURRENT="$(cat "$file")"
  FEEDBACK="$( [ -s "$FAIL_LOG" ] && tail -n 50 "$FAIL_LOG" || true )"
  INSTR="$(mk_prompt "$CURRENT" "$FEEDBACK")"
  say "OpenAI GPT-4 Turbo (API)"
  req="$(jq -n --arg p "$INSTR" '{
    model:"gpt-4-turbo",
    temperature:0.1,
    messages:[{role:"user", content:$p}],
    max_tokens:1200
  }')"
  t0=$(secs)
  if [ "$VERBOSE" -ge 2 ]; then
    printf "%s\n" "---- prompt (first 40 lines) ----"
    printf "%s\n" "$INSTR" | head -n 40
    echo "----"
  fi
  out="$(curl -sS https://api.openai.com/v1/chat/completions \
      -H "Authorization: Bearer '"$OPENAI_API_KEY"'" \
      -H "Content-Type: application/json" \
      -d "$req")"
  printf "%s" "$out" | jq -r '.choices[0].message.content // ""' | apply_answer "$file"
  t1=$(secs)
  p_tokens=$(printf "%s" "$out" | jq -r '.usage.prompt_tokens // 0')
  c_tokens=$(printf "%s" "$out" | jq -r '.usage.completion_tokens // 0')
  cost=$(python - <<PY 2>/dev/null || echo "0"
p=$p_tokens; c=$c_tokens
print(round((p/1000.0)*$OPENAI_IN + (c/1000.0)*$OPENAI_OUT, 6))
PY
)
  log_add "$label" "$((t1 - t0))" "$cost"
}

# =======================
# CLI args
# =======================
while getopts ":l:h" opt; do
  case $opt in
    l) LANG="$OPTARG" ;;
    h) usage; exit 0 ;;
    \?) usage; exit 1 ;;
  esac
 done
case "$LANG" in python|java|swift|js) ;; *) usage; exit 1 ;; esac

# =======================
# Main
# =======================
check_env
init_repo

# pick target file by language
case "$LANG" in
  python) FILE="$WORKDIR/app.py" ;;
  java)   FILE="$WORKDIR/Main.java" ;;
  swift)  FILE="$WORKDIR/main.swift" ;;
  js)     FILE="$WORKDIR/app.js" ;;
esac

say "Step 0: Validate baseline (should FAIL) — language: $LANG"
if validate; then fail "Baseline unexpectedly passed"; exit 1; else ok "Baseline fails as expected"; fi

# Tier 1 — Local fast (2 tries w/ feedback)
for i in $(seq 1 $MAX_LOCAL_ATTEMPTS_FAST); do
  prompt_fix_local "$LOCAL_FAST_MODEL" "$FILE" "Tier 1 (Local fast #$i)"
  if validate; then ok "Fixed at Tier 1 (attempt $i)"; break; fi
  say "Tier 1 attempt $i failed; retrying/escalating…"
  if [ -s "$FAIL_LOG" ] && [ "$VERBOSE" -ge 1 ]; then
    echo "---- validator tail ----"
    tail -n 25 "$FAIL_LOG"
    echo "------------------------"
  fi
done
if validate; then
  :
else
  # Tier 2 — Local heavy
  for i in $(seq 1 $MAX_LOCAL_ATTEMPTS_HEAVY); do
    prompt_fix_local "$LOCAL_HEAVY_MODEL" "$FILE" "Tier 2 (Local heavy #$i)"
    if validate; then ok "Fixed at Tier 2 (attempt $i)"; break; fi
    say "Tier 2 attempt $i failed; retrying/escalating…"
    if [ -s "$FAIL_LOG" ] && [ "$VERBOSE" -ge 1 ]; then
      echo "---- validator tail ----"
      tail -n 25 "$FAIL_LOG"
      echo "------------------------"
    fi
  done
fi

# Tiers 3–4 (APIs)
if ! validate; then
  if [ "$USE_GEMINI" -ne 0 ]; then
    prompt_fix_gemini "$FILE" "Tier 3 (Gemini 2.5 Pro)"
    if validate; then
      ok "Fixed at Tier 3"
    else
      say "Tier 3 failed; escalating…"
      if [ -s "$FAIL_LOG" ] && [ "$VERBOSE" -ge 1 ]; then
        echo "---- validator tail ----"
        tail -n 25 "$FAIL_LOG"
        echo "------------------------"
      fi
    fi
  fi
fi
if ! validate && [ "$USE_ANTHROPIC" -ne 0 ]; then
  prompt_fix_haiku "$FILE" "Tier 3.5 (Claude Haiku)"
  if validate; then
    ok "Fixed at Tier 3.5"
  else
    say "Tier 3.5 failed; escalating…"
    if [ -s "$FAIL_LOG" ] && [ "$VERBOSE" -ge 1 ]; then
      echo "---- validator tail ----"
      tail -n 25 "$FAIL_LOG"
      echo "------------------------"
    fi
  fi
fi
if ! validate && [ "$USE_OPENAI" -ne 0 ]; then
  prompt_fix_openai "$FILE" "Tier 4 (GPT-4 Turbo)"
  if validate; then
    ok "Fixed at Tier 4"
  else
    if [ -s "$FAIL_LOG" ] && [ "$VERBOSE" -ge 1 ]; then
      echo "---- validator tail ----"
      tail -n 25 "$FAIL_LOG"
      echo "------------------------"
    fi
  fi
fi

# Final verdict
if validate; then
  ok "SUCCESS — ladder fixed it"
else
  fail "All tiers attempted; still failing. Inspect $FILE and $FAIL_LOG."
fi

# Summary
say "Summary (time & cost)"
total_t=0; total_c=0
n=${#LOG_STEP[@]}
printf "%-28s  %8s  %10s\n" "Step" "secs" "USD"
for idx in $(seq 0 $((n-1))); do
  s="${LOG_STEP[$idx]}"; t="${LOG_TIME[$idx]}"; c="${LOG_COST[$idx]}"
  printf "%-28s  %8s  %10s\n" "$s" "$t" "$c"
  total_t=$((total_t + t))
  total_c=$(python - <<PY 2>/dev/null || echo "0"
a=$total_c; b="$c"
try:
    print(round(float(a)+float(b),6))
except:
    print(a)
PY
)
done
printf "%-28s  %8s  %10s\n" "TOTAL" "$total_t" "$total_c"
