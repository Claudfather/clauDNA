# Scan Categories — Frontend Performance Audit

Reference material for Phase 3 scan. Each category is investigated by an Explore subagent focused on the component tree identified in Phase 2.

---

## A. Render Cascades

The most common source of "flickering" and "multiple reloads." Trace the re-render chain from trigger to effect.

**Look for:**
- **Unstable object/array references** in useEffect dependencies — objects or arrays created inline that trigger re-runs on every render despite identical values
- **useEffect with object dependencies** — `[someObject]` instead of `[someObject.id, someObject.name]`
- **Props that create new references** — inline objects `prop={{ key: value }}`, inline arrays, inline callbacks without `useCallback`
- **URL sync loops** — `useSearchParams()` or `useRouter()` changes causing parent re-renders that recreate child props, which trigger effects, which update the URL again

**Trace methodology:**
1. Start at the route entry point
2. For each component: list its state, effects, and their dependency arrays
3. For each dependency: is the reference stable across renders?
4. For each effect: what does it trigger? (fetch, state update, URL change, scroll)
5. Does the trigger cascade back to step 2? If yes, you found a loop.

**Output:** Draw the cascade chain showing each step and what triggers it.

## B. Fetch Patterns

**Look for:**
- **Redundant fetches** — same endpoint called multiple times due to effect re-runs
- **Fetch waterfalls** — sequential fetches where parallel would work (fetch A → wait → fetch B → wait)
- **No client-side caching** — every navigation re-fetches (no SWR, React Query, or memo)
- **`cache: "no-store"`** on every request — prevents browser-level and Next.js caching
- **Missing abort controllers** — stale requests completing after navigation
- **Non-blocking fetches that block** — secondary fetches that prevent rendering

## C. Observer & Listener Overhead

**Look for:**
- **IntersectionObserver** with excessive thresholds (more than 5 values)
- **Scroll event listeners** without debounce or throttle
- **ResizeObserver** triggering state updates on every pixel change
- **MutationObserver** on large subtrees
- **Missing cleanup** — listeners added in useEffect without return cleanup
- **Observer callbacks that call setState** — every observation triggers a re-render

## D. State Management

**Look for:**
- **State thrashing** — multiple `setState` calls in sequence that each trigger a render (React 18+ batches these in event handlers, but NOT in async callbacks, timeouts, or promises)
- **Derived state stored in useState** — values computable from props/other state stored separately, creating sync issues
- **Context at too high a level** — Context providers wrapping large subtrees where changes re-render everything below
- **State lifted too high** — parent holds state that only one child needs, causing sibling re-renders

## E. Memoization Gaps

**Look for:**
- **Components missing `React.memo()`** — especially list items, nav elements, and components receiving stable data but re-rendering due to parent
- **Expensive computations without `useMemo`** — filtering, sorting, or transforming large arrays on every render
- **Callbacks without `useCallback`** — especially when passed as props to memoized children (defeats the memo)
- **`useMemo` with unstable dependencies** — memo that recalculates every render because a dependency is recreated

## F. Layout Stability

**Look for:**
- **Suspense boundaries** causing content flash — skeleton shown, then content, then skeleton again if data refetches
- **Conditional rendering** without size reservation — elements appearing/disappearing cause layout shifts
- **Images and embeds without dimensions** — cause CLS (Cumulative Layout Shift)
- **Font loading** causing text reflow (FOUT/FOIT)
- **Dynamic imports** without loading fallbacks

## G. Framework-Specific Issues

**Next.js App Router:**
- `useSearchParams()` inside a component that also has effects — URL changes re-render the component, potentially triggering effects
- Middleware redirects causing double page loads
- Server/client component boundary mismatches — client component inside server component re-mounting
- `generateMetadata` making slow async calls that delay page render
- Missing `loading.tsx` causing full-page skeleton on navigation

**React 19 specific:**
- `use()` hook suspending unexpectedly
- Transitions not wrapping slow state updates

## H. Bundle & Loading

**Look for:**
- **Large component files** (>500 lines) — may benefit from code splitting
- **Heavy library imports** — importing full libraries when tree-shakeable imports exist (e.g., `import _ from 'lodash'` vs `import debounce from 'lodash/debounce'`)
- **Missing dynamic imports** — large components loaded eagerly when they're below the fold
- **Unoptimized images** — no `next/image`, large uncompressed assets
