const inheritNull = new Set([
  ['delivery', 'enabled'], ['delivery', 'recipients'], ['display', 'columns'],
  ['limits', 'maxRows'], ['limits', 'timeoutMs'],
].map(path => JSON.stringify(path)));
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const clone = value => {
  if (Array.isArray(value)) return value.map(clone);
  if (record(value)) return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, clone(v)]));
  return value;
};

export function resolveReportSettings(defaults, workspace, request) {
  function merge(layers, path) {
    const keys = new Set(layers.filter(record).flatMap(layer => Object.keys(layer)));
    const entries = [];
    for (const key of keys) {
      const fieldPath = [...path, key];
      const values = layers.map(layer => record(layer) && Object.hasOwn(layer, key) ? layer[key] : undefined)
        .filter(value => value !== undefined && !(value === null && inheritNull.has(JSON.stringify(fieldPath))));
      if (!values.length) continue;
      const selected = values.at(-1);
      // An explicit null resets the lower object before subsequent object overrides.
      const lastNull = values.lastIndexOf(null);
      const value = record(selected) ? merge(values.slice(lastNull + 1), fieldPath) : clone(selected);
      entries.push([key, value]);
    }
    return Object.fromEntries(entries);
  }
  return merge([defaults, workspace, request], []);
}
