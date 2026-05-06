# Review Dimensions

Evaluate the PR across these dimensions:

| Dimension | What to check |
|-----------|--------------|
| **Correctness** | Does the code do what the PR claims? Are there logic errors, off-by-ones, race conditions? |
| **Design** | Does the approach make sense? Is there a simpler way? Are abstractions justified? |
| **Modularity** | Are responsibilities clearly separated? Does each function/class do one thing? |
| **Edge cases** | What happens with empty input, null values, concurrent access, large data? |
| **Error handling** | Are errors caught and handled meaningfully? Are error messages helpful? |
| **Tests** | Are there tests? Do they test the right things? Are edge cases covered? |
| **Documentation** | Are public APIs documented? Are non-obvious decisions explained? |
| **Security** | Any injection risks, auth gaps, data exposure, or OWASP concerns? |
| **Performance** | Any N+1 queries, unnecessary allocations, missing indexes, or O(n^2) where O(n) is possible? |
| **Compatibility** | Does this break existing callers, APIs, or contracts? |
