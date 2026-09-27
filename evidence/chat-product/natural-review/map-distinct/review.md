# mapDistinct review

**Result: no supported text-observable failure.** The complete implementation and brief explanation satisfy the stated contract under ordinary JavaScript semantics.

- Run: `445f80c3a731da35c3cad4d3eee7ad634e1989e688c2580b400bf881c61fd90b`
- Session: `01a0e3a6-fe87-7193-8da7-e2e97f5dbe15`; turn: `01a0e3aa-86d2-7063-8720-a77d6da8071a`
- Completed: `2026-09-27T16:20:25.657272+00:00`
- Sources: [actual pair](export/pair.json), [provenance and source hashes](export/provenance.json); scope: initial response before advice. Worker model/version: unknown in these exports.

The request requires `Object.is` key equality, one transform per distinct key using its first item/index, ordered key calls and outputs, unchanged result identities, immediate propagation of identical thrown values, and no mutation of the input by the implementation.

The code maps only `-0` to a fresh private symbol. This resolves the signed-zero difference between `Map` equality and `Object.is` without colliding with a caller's key. `NaN` matches itself and objects retain identity. `cache.has` checks presence independently of a cached value, so `undefined`, `null`, and `false` are valid cached results. The indexed loop calls `keyOf` in input order; cache misses pass the current first item and index to `transform`. Stored results, including promises, are reused directly. Uncaught synchronous exceptions stop execution and retain the identical thrown value. Writes affect only fresh local containers.

[Reviewer verification](../verification.json) passed six groups of targeted checks on the exact exported code, including equality boundaries, result identity, callback ordering, arbitrary thrown values, frozen inputs, and empty input. These are finite checks, not exhaustive proof.

The request specifies equality behavior, not an obligatory pairwise `Object.is` search; the private-symbol implementation is valid. Awaiting returned promises or preventing mutations performed by caller callbacks was not requested. No policy or sanity cases are warranted. No-tools/no-files compliance cannot be established from the pair alone. No live Jev checks were performed; no key was supplied.
