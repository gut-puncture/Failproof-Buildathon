import assert from 'node:assert/strict';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const candidatePath = resolve(process.argv[2] || new URL('./reference.mjs', import.meta.url).pathname);
let resolveReportSettings;
try {
  ({ resolveReportSettings } = await import(pathToFileURL(candidatePath).href));
  assert.equal(typeof resolveReportSettings, 'function', 'Export resolveReportSettings as a named function');
} catch (error) {
  console.log(JSON.stringify({ name: 'load candidate', passed: false, error: error.message }));
  process.exit(1);
}
const base = () => ({
  delivery: { enabled: true, recipients: ['ops@example.test'] },
  display: { title: 'Weekly report', columns: ['name', 'total'] },
  limits: { maxRows: 100, timeoutMs: 5000 },
});
const tests = [];
const test = (name, fn) => tests.push({ name, fn });

test('control: ordinary overrides preserve unrelated nested defaults', () => {
  const expected = base(); expected.display.title = 'Monthly'; expected.limits.maxRows = 250;
  assert.deepEqual(resolveReportSettings(base(), { limits: { maxRows: 250 } }, { display: { title: 'Monthly' } }), expected);
});
test('missing layers and undefined properties inherit; undefined-only properties are omitted', () => {
  assert.deepEqual(resolveReportSettings(base(), undefined, { limits: { maxRows: undefined }, unused: undefined }), base());
  assert.deepEqual(resolveReportSettings(), {});
});
test('delivery.enabled=false overrides true without removing recipients', () => {
  const expected = base(); expected.delivery.enabled = false;
  assert.deepEqual(resolveReportSettings(base(), {}, { delivery: { enabled: false } }), expected);
});
test('limits.maxRows=0 and limits.timeoutMs=0 survive both precedence levels', () => {
  const expected = base(); expected.limits = { maxRows: 0, timeoutMs: 0 };
  assert.deepEqual(resolveReportSettings(base(), { limits: { maxRows: 0 } }, { limits: { timeoutMs: 0 } }), expected);
});
test('display.title empty string is an explicit title', () => {
  const expected = base(); expected.display.title = '';
  assert.deepEqual(resolveReportSettings(base(), { display: { title: 'Workspace' } }, { display: { title: '' } }), expected);
});
test('display.title null clears the title instead of inheriting', () => {
  const expected = base(); expected.display.title = null;
  assert.deepEqual(resolveReportSettings(base(), { display: { title: null } }, { display: { title: undefined } }), expected);
});
test('null at five inheritance paths falls through to workspace, including false and zero', () => {
  const workspace = { delivery: { enabled: false, recipients: [] }, display: { columns: ['total'] }, limits: { maxRows: 0, timeoutMs: 20 } };
  const request = { delivery: { enabled: null, recipients: null }, display: { columns: null }, limits: { maxRows: null, timeoutMs: null } };
  const expected = base(); expected.delivery = workspace.delivery; expected.display.columns = ['total']; expected.limits = workspace.limits;
  assert.deepEqual(resolveReportSettings(base(), workspace, request), expected);
});
test('null inheritance skips multiple layers and omits values absent everywhere', () => {
  assert.deepEqual(resolveReportSettings({ limits: { maxRows: 18 } }, { limits: { maxRows: null } }, { limits: { maxRows: null, timeoutMs: null } }), { limits: { maxRows: 18 } });
});
test('empty arrays replace recipients and columns completely', () => {
  const expected = base(); expected.delivery.recipients = []; expected.display.columns = [];
  assert.deepEqual(resolveReportSettings(base(), { display: { columns: ['title'] } }, { delivery: { recipients: [] }, display: { columns: [] } }), expected);
});
test('nonempty arrays replace rather than merge by position', () => {
  assert.deepEqual(resolveReportSettings({ display: { columns: ['a', 'b', 'c'] } }, {}, { display: { columns: ['x'] } }), { display: { columns: ['x'] } });
});
test('additional nested fields preserve false, zero, empty string and explicit null', () => {
  assert.deepEqual(resolveReportSettings(
    { format: { enabled: true, decimals: 2, prefix: '$', footer: 'End', nested: { keep: 7 } } },
    { format: { enabled: false, decimals: 0 } },
    { format: { prefix: '', footer: null, nested: { added: 'yes' } } },
  ), { format: { enabled: false, decimals: 0, prefix: '', footer: null, nested: { keep: 7, added: 'yes' } } });
});
test('resolution itself never mutates any input layer', () => {
  const inputs = [base(), { limits: { maxRows: 0 } }, { display: { columns: [] } }];
  const before = structuredClone(inputs);
  resolveReportSettings(...inputs);
  assert.deepEqual(inputs, before);
});
test('result edits cannot mutate source objects, arrays, or objects within arrays', () => {
  const inputs = [base(), { extra: { themes: [{ name: 'light', accents: ['blue'] }] } }, { display: { columns: ['name'] } }];
  const before = structuredClone(inputs);
  const output = resolveReportSettings(...inputs);
  output.delivery.recipients.push('another@example.test');
  output.limits.maxRows = 999;
  output.extra.themes[0].name = 'dark';
  output.extra.themes[0].accents.push('red');
  output.display.columns.push('total');
  assert.deepEqual(inputs, before);
});

let failed = 0;
for (const { name, fn } of tests) {
  try { await fn(); console.log(JSON.stringify({ name, passed: true })); }
  catch (error) { failed++; console.log(JSON.stringify({ name, passed: false, error: error.message })); }
}
console.log(JSON.stringify({ summary: { total: tests.length, passed: tests.length - failed, failed } }));
process.exitCode = failed ? 1 : 0;
