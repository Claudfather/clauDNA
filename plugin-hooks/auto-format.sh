#!/bin/bash
# Auto-format hook for Claude Code
# Runs after Write/Edit operations to format code

# Read the hook event from stdin
EVENT=$(cat)

# Extract the file path from the event
FILE_PATH=$(echo "$EVENT" | grep -o '"file_path":"[^"]*"' | cut -d'"' -f4)

# Exit if no file path found
if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Format based on file extension
case "$FILE_PATH" in
    *.py)
        # Python: use ruff if available
        if command -v ruff &> /dev/null; then
            ruff format "$FILE_PATH" 2>/dev/null
            ruff check --fix "$FILE_PATH" 2>/dev/null
        fi
        ;;
    *.js|*.jsx|*.ts|*.tsx|*.json|*.md)
        # JavaScript/TypeScript/JSON/Markdown: use prettier if available
        if command -v prettier &> /dev/null; then
            prettier --write "$FILE_PATH" 2>/dev/null
        fi
        ;;
    *.sql)
        # SQL: use sqlfluff if available
        if command -v sqlfluff &> /dev/null; then
            sqlfluff fix "$FILE_PATH" 2>/dev/null
        fi
        ;;
esac

exit 0
