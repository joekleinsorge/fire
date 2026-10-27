// Loads the browser scripts into one isolated global scope with a permissive DOM stub, so
// their pure logic can be tested with node:test and no dependencies.
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const WEB = new URL('../../web/', import.meta.url);

function element() {
  const target = {
    classList: {add() {}, remove() {}, toggle() {}, contains: () => false},
    style: {}, dataset: {}, options: [], value: '',
    addEventListener() {}, removeEventListener() {}, append() {}, setAttribute() {},
    querySelector: () => element(), querySelectorAll: () => [], showModal() {}, close() {},
    getBoundingClientRect: () => ({width: 0, height: 0, left: 0, top: 0}),
  };
  target.elements = new Proxy({}, {get: () => element()});
  return target;
}

export function load(...files) {
  const storage = new Map();
  const context = vm.createContext({
    console, crypto, setTimeout, clearTimeout, structuredClone,
    document: {getElementById: element, querySelector: element, querySelectorAll: () => [], addEventListener() {},
               createElement: element, documentElement: element()},
    window: {addEventListener() {}},
    location: {hash: ''},
    localStorage: {getItem: k => storage.get(k) ?? null, setItem: (k, v) => storage.set(k, String(v)), removeItem: k => storage.delete(k)},
    confirm: () => true,
    fetch: () => Promise.reject(new Error('network disabled in tests')),
  });
  for (const file of files) vm.runInContext(readFileSync(new URL(file, WEB), 'utf8'), context, {filename: file});
  // Top-level const/let live in the context's lexical scope, so read them by evaluation.
  return source => vm.runInContext(source, context);
}
