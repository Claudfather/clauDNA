# =============================================================================
# Git Worktree Aliases for Claude Code
# Add to ~/.zshrc: cat /path/to/clauDNA/shell/zshrc-additions.sh >> ~/.zshrc
# Then reload: source ~/.zshrc
# =============================================================================

# Create a new worktree: wt-new feature-name
wt-new() {
    if [ -z "$1" ]; then
        echo "Usage: wt-new <branch-name>"
        return 1
    fi
    local repo_root=$(git rev-parse --show-toplevel 2>/dev/null)
    if [ -z "$repo_root" ]; then
        echo "Not in a git repository"
        return 1
    fi
    local repo_name=$(basename "$repo_root")
    local worktree_path="${repo_root}-worktrees/$1"
    git worktree add -b "$1" "$worktree_path" && cd "$worktree_path"
    echo "Created worktree at $worktree_path"
}

# List all worktrees: wt-list
alias wt-list='git worktree list'

# Remove a worktree: wt-rm worktree-path
wt-rm() {
    if [ -z "$1" ]; then
        echo "Usage: wt-rm <worktree-path-or-name>"
        return 1
    fi
    git worktree remove "$1" && echo "Removed worktree: $1"
}

# Quick jump aliases (set these per-session as needed)
# Usage: wt-set a /path/to/worktree  -> then use 'za' to jump there
wt-set() {
    if [ -z "$1" ] || [ -z "$2" ]; then
        echo "Usage: wt-set <letter> <path>"
        echo "Example: wt-set a ~/Projects/myrepo-worktrees/feature-x"
        return 1
    fi
    alias "z$1"="cd $2"
    echo "Set z$1 -> $2"
}

# =============================================================================
# Usage:
#
#   cd ~/Projects/myrepo          # Go to main repo
#   wt-new feature-a              # Create worktree for feature-a
#   wt-new feature-b              # Create worktree for feature-b
#
#   wt-set a ~/Projects/myrepo-worktrees/feature-a
#   wt-set b ~/Projects/myrepo-worktrees/feature-b
#
#   za                            # Jump to feature-a worktree
#   zb                            # Jump to feature-b worktree
#
#   wt-list                       # List all worktrees
#   wt-rm feature-a               # Remove worktree when done
# =============================================================================
