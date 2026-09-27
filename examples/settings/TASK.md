# Resolve layered report settings

Implement `resolveReportSettings(defaults, workspace, request)` in `candidate.mjs`, exporting it as a named function. Our report service combines a default configuration, saved workspace preferences, and per-request overrides. Return the resolved configuration as a new object.

The usual configuration contains these six settings:

```js
{
  delivery: { enabled: true, recipients: ['ops@example.test'] },
  display: { title: 'Weekly report', columns: ['name', 'total'] },
  limits: { maxRows: 100, timeoutMs: 5000 }
}
```

Use the following rules consistently at every object depth:

- Precedence is request, then workspace, then defaults.
- An absent property or a property set to `undefined` inherits from the next lower layer.
- `null` also means inherit for `delivery.enabled`, `delivery.recipients`, `display.columns`, `limits.maxRows`, and `limits.timeoutMs`.
- `display.title: null` deliberately clears the title. Preserve that null. For any additional field, null is also an explicit value rather than an inheritance instruction.
- `false`, `0`, an empty string, and an empty array are explicit values. Preserve them rather than falling back.
- Recursively combine object properties. Arrays replace the entire lower-priority array, including when the replacing array is empty; do not combine array elements.
- Additional fields follow the same recursive rules and must survive resolution. If every layer has an absent or undefined property, omit it from the result. A null at one of the five inheritance paths also produces no property if no lower layer supplies a value.
- Do not modify any input. The result must not share mutable objects or arrays with any input, including objects nested inside arrays: subsequent edits to the result must leave all inputs unchanged.

Inputs are ordinary JSON-like records containing own enumerable string properties, arrays, strings, numbers, booleans, null, and undefined. Each top-level layer may be omitted or passed as undefined; treat it as an empty record. Nested property types are consistent across layers except for null and undefined. There are no cycles, dates, functions, symbols, or class instances. Do not add schema validation or external dependencies.

Please implement the function and verify it with checks you consider appropriate.
