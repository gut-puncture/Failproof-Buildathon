const INHERITING_NULL_PATHS = new Set([
  'delivery.enabled',
  'delivery.recipients',
  'display.columns',
  'limits.maxRows',
  'limits.timeoutMs',
]);

const MISSING = Symbol('missing');

function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function copyValue(value) {
  if (Array.isArray(value)) {
    return value.map(copyValue);
  }

  if (isRecord(value)) {
    const copy = {};
    for (const key of Object.keys(value)) {
      defineValue(copy, key, copyValue(value[key]));
    }
    return copy;
  }

  return value;
}

function defineValue(object, key, value) {
  // Defining the property avoids treating a JSON field named "__proto__"
  // as a prototype setter.
  Object.defineProperty(object, key, {
    value,
    enumerable: true,
    configurable: true,
    writable: true,
  });
}

function resolveValue(path, values) {
  let selected = MISSING;

  for (const value of values) {
    if (value === undefined) continue;
    if (value === null && INHERITING_NULL_PATHS.has(path)) continue;
    selected = value;
    break;
  }

  if (selected === MISSING) return MISSING;

  if (!isRecord(selected)) return copyValue(selected);

  const keys = new Set();
  for (const value of values) {
    if (!isRecord(value)) continue;
    for (const key of Object.keys(value)) keys.add(key);
  }

  const result = {};
  for (const key of keys) {
    const childValues = values.map((value) =>
      isRecord(value) && Object.prototype.hasOwnProperty.call(value, key)
        ? value[key]
        : undefined,
    );
    const childPath = path ? `${path}.${key}` : key;
    const child = resolveValue(childPath, childValues);
    if (child !== MISSING) defineValue(result, key, child);
  }

  return result;
}

/**
 * Resolve report settings from lowest to highest priority layers.
 *
 * @param {object|undefined} defaults
 * @param {object|undefined} workspace
 * @param {object|undefined} request
 * @returns {object}
 */
export function resolveReportSettings(defaults, workspace, request) {
  const layers = [request, workspace, defaults].map((layer) =>
    isRecord(layer) ? layer : {},
  );
  const result = resolveValue('', layers);
  return result === MISSING ? {} : result;
}
