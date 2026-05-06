#!/usr/bin/env bash
# Claude Code statusLine
# Shows: branch context | lines changed | model | context usage

input=$(cat)

# --- Extract fields from stdin JSON ---
cwd=$(echo "$input" | jq -r '.cwd // empty')
model=$(echo "$input" | jq -r '.model.display_name // empty')
used_pct=$(echo "$input" | jq -r '.context_window.used_percentage // empty')
lines_added=$(echo "$input" | jq -r '.cost.total_lines_added // 0')
lines_removed=$(echo "$input" | jq -r '.cost.total_lines_removed // 0')

# --- Git branch (smart display) ---
branch=""
if [ -n "$cwd" ]; then
  raw_branch=$(git -C "$cwd" --no-optional-locks symbolic-ref --short HEAD 2>/dev/null)
  if [ -n "$raw_branch" ]; then
    case "$raw_branch" in
      implement/*)
        slug="${raw_branch#implement/}"
        branch="implementing: ${slug}"
        ;;
      design/*)
        slug="${raw_branch##*/}"
        branch="designing: ${slug}"
        ;;
      feature/*)
        slug="${raw_branch#feature/}"
        branch="feature: ${slug}"
        ;;
      fix/*)
        slug="${raw_branch#fix/}"
        branch="fixing: ${slug}"
        ;;
      main|master)
        branch="main"
        ;;
      *)
        branch="$raw_branch"
        ;;
    esac
  fi
fi

# --- Lines changed this session ---
lines_display=""
if [ "$lines_added" != "0" ] || [ "$lines_removed" != "0" ]; then
  lines_display="+${lines_added}/-${lines_removed}"
fi

# --- Context usage ---
ctx_display=""
if [ -n "$used_pct" ]; then
  ctx_int=$(printf "%.0f" "$used_pct" 2>/dev/null)
  ctx_display="${ctx_int}%"
fi

# --- Assemble ---
parts=()
[ -n "$branch" ] && parts+=("$branch")
[ -n "$lines_display" ] && parts+=("$lines_display")
[ -n "$model" ] && parts+=("$model")
[ -n "$ctx_display" ] && parts+=("$ctx_display")

output=""
for part in "${parts[@]}"; do
  if [ -z "$output" ]; then
    output="$part"
  else
    output="$output | $part"
  fi
done

printf "%s" "$output"
