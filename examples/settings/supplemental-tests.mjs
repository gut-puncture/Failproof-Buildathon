import assert from 'node:assert/strict';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const path = process.argv[2] ? pathToFileURL(resolve(process.argv[2])) : new URL('./reference.mjs', import.meta.url);
const { resolveReportSettings } = await import(path.href);
const tests = [];
const add = (name, run) => tests.push({ name, run });

add('literal dotted key delivery.enabled is an additional field whose null is explicit', () => {
  assert.deepEqual(resolveReportSettings({ 'delivery.enabled': true }, {}, { 'delivery.enabled': null }), { 'delivery.enabled': null });
});

for (const [key, fallback] of [
  ['delivery.recipients', ['ops@example.test']], ['display.columns', ['name']],
  ['limits.maxRows', 100], ['limits.timeoutMs', 5000],
]) {
  add(`literal dotted key ${key} does not inherit the nested field's null rule`, () => {
    assert.deepEqual(resolveReportSettings({ [key]: fallback }, {}, { [key]: null }), { [key]: null });
  });
}

add('ordinary nested null inheritance still applies at all five specified paths', () => {
  const defaults = { delivery: { enabled: true, recipients: ['ops@example.test'] }, display: { columns: ['name'] }, limits: { maxRows: 100, timeoutMs: 5000 } };
  const request = { delivery: { enabled: null, recipients: null }, display: { columns: null }, limits: { maxRows: null, timeoutMs: null } };
  assert.deepEqual(resolveReportSettings(defaults, {}, request), defaults);
});

add('literal and nested fields coexist with distinct null semantics', () => {
  assert.deepEqual(resolveReportSettings(
    { 'limits.maxRows': 17, limits: { maxRows: 100 } },
    {},
    { 'limits.maxRows': null, limits: { maxRows: null } },
  ), { 'limits.maxRows': null, limits: { maxRows: 100 } });
});

let failed = 0;
for (const { name, run } of tests) {
  try { run(); console.log(JSON.stringify({ name, passed: true })); }
  catch (error) { failed++; console.log(JSON.stringify({ name, passed: false, error: error.message })); }
}
console.log(JSON.stringify({ summary: { total: tests.length, passed: tests.length - failed, failed } }));
process.exitCode = failed ? 1 : 0;
