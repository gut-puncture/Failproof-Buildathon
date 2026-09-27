# Ordered import pipeline

Implement a named export `importRows(rows, {prepare, commit, concurrency})` in `candidate.mjs`. It returns a promise. We need to prepare report rows concurrently, but publish them in their original order so a failed import leaves only a successfully committed prefix. Use standard JavaScript without dependencies, timers, network, or process-global changes. Aim for under 180 lines.

`rows` is an array. `prepare(row, index)` and `commit(preparedValue, index)` may return values, promises, or throw synchronously. Do not modify rows or its elements. Each invocation of importRows is independent. Concurrency is a positive integer; invalid concurrency returns a rejected promise with RangeError without invoking either callback. Empty rows resolve to `[]` without callbacks.

Rules:

1. Start preparation synchronously when importRows is called, in input index order, filling up to concurrency slots. Synchronous values or throws finish preparation only through promise processing. At most concurrency prepare callbacks may be unresolved. Refill available preparation slots promptly on a successful preparation, even while an earlier commit is pending.
2. Commits execute strictly in input order and never overlap. A prepared row may commit only after every preceding commit succeeded. Pass the exact prepared value to commit, including false, zero or undefined. Return an array containing the commit results in input order if all succeed.
3. When a preparation fails at index j, stop starting new preparations immediately when that failure is observed. Already-started preparations may finish. Continue committing the successfully prepared prefix before j; never commit j or any later row. If another already-started preparation fails at an earlier index, that earlier index becomes the boundary. The rejection reason is the exact error from the earliest failing input index, regardless of failure completion order.
4. If a commit fails at index k, stop starting preparations once that failure is observed, never commit a later row, and reject with that exact error. A commit failure at an earlier index takes precedence over a later preparation failure. Previously committed rows are retained; no rollback is requested.
5. Success or rejection is reported only after all started prepare and commit callbacks have settled. Consume all late rejections. Do not wait for any callback that was never started.

Callbacks may synchronously start independent imports; those have independent limits and results. You may assume callback types and row arrays are valid; do not add validation beyond concurrency. Implement the function and verify it with checks you consider appropriate.
