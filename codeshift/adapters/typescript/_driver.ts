// Subprocess driver: import a translated module and exercise one callable over
// many inputs. Run via `tsx` so TypeScript is executed directly (no build step).
//   npx tsx _driver.ts <root> <module> <target>   (payload as JSON on stdin)
//
// `<target>` is an exported function (`slugify`), a qualified method
// (`Cart.addItem`), or `Cart.__init__`, which means "construct only".
//
// Payload: {"inputs": [[...]], "ctor": [[...]] | null} — one constructor
// arg-list per input, so each call runs against a freshly built receiver, the
// same way the Python side does it. A bare list means inputs with no ctor.
//
// Method names are looked up across the spellings a translation may pick
// (`add_item` / `addItem`). Only the class name is mapped ahead of time, from
// the module's exports; a method's name never appears there to be mapped.
//
// Wrapped in an async IIFE (no top-level await) so it works whether tsx emits
// CommonJS or ESM.
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const CONSTRUCT = "__init__";

function variants(name: string): string[] {
  const camel = name.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
  const snake = name.replace(/([a-z0-9])([A-Z])/g, "$1_$2").toLowerCase();
  return [...new Set([name, camel, snake])];
}

// The *key* under which `name` is reachable on `container`, or undefined.
function pick(container: any, name: string): string | undefined {
  for (const candidate of variants(name)) {
    if (container?.[candidate] !== undefined) return candidate;
  }
  return undefined;
}

function resolveExport(mod: any, name: string): any {
  const key = pick(mod, name);
  if (key !== undefined) return mod[key];

  const fallback = mod.default;
  if (fallback === undefined || fallback === null) return undefined;
  const nested = pick(fallback, name);
  if (nested !== undefined) return fallback[nested];
  // `export default class Cart` puts the class itself under `default`.
  if (typeof fallback === "function" && variants(name).includes(fallback.name)) return fallback;
  return undefined;
}

// A total order for values that are not mutually comparable. Must agree with
// the Python driver's `_canon`, which uses sorted keys and no spaces.
function canon(value: any): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
  if (Array.isArray(value)) return "[" + value.map(canon).join(",") + "]";
  const keys = Object.keys(value).sort();
  return "{" + keys.map((k) => JSON.stringify(k) + ":" + canon(value[k])).join(",") + "}";
}

// Put a value into a form the other language can produce exactly.
//
// `JSON.stringify` renders a Set or a Map as `{}` — the contents vanish, so a
// wrong one compares equal to a right one. Python's `json` has no encoding for
// a set either and falls back to a repr string. Both sides therefore emit a
// tagged, sorted array for sets, a plain object for Maps (matching a Python
// dict), and epoch milliseconds for dates. See `_driver.py:_normalize` — these
// two functions have to stay in step.
function normalize(value: any): any {
  if (value instanceof Set) {
    return { __set__: [...value].map(normalize).sort((a, b) => (canon(a) < canon(b) ? -1 : canon(a) > canon(b) ? 1 : 0)) };
  }
  if (value instanceof Map) {
    const out: Record<string, any> = {};
    for (const [key, v] of value) out[String(key)] = normalize(v);
    return out;
  }
  if (value instanceof Date) return { __datetime__: value.getTime() };
  if (Array.isArray(value)) return value.map(normalize);
  if (value !== null && typeof value === "object") {
    const out: Record<string, any> = {};
    for (const [key, v] of Object.entries(value)) out[key] = normalize(v);
    return out;
  }
  return value;
}

// The receiver's own fields after a call. Methods are dropped whether they live
// on the instance or the prototype, matching what the Python side compares.
function state(obj: any): Record<string, any> {
  const out: Record<string, any> = {};
  for (const [key, value] of Object.entries(obj ?? {})) {
    if (typeof value !== "function") out[key] = normalize(value);
  }
  return out;
}

type Call = (args: any[], ctorArgs: any[] | null) => Promise<[any, Record<string, any> | null]>;

function resolve(mod: any, target: string): Call {
  const dot = target.lastIndexOf(".");
  const ownerName = dot === -1 ? "" : target.slice(0, dot);
  const memberName = dot === -1 ? target : target.slice(dot + 1);

  if (!ownerName) {
    const fn = resolveExport(mod, memberName);
    if (typeof fn !== "function") throw new Error(`no exported function ${memberName}`);
    return async (args) => [await fn(...args), null];
  }

  // Resolved once, before the loop: a class the translation never emitted
  // should fail the run as a single honest error, not as one identical error
  // per input, which the harness would read as behavioral drift.
  const cls = resolveExport(mod, ownerName);
  if (typeof cls !== "function") throw new Error(`no exported class ${ownerName}`);

  if (memberName === CONSTRUCT) {
    return async (args) => [null, state(new cls(...args))];
  }

  const onClass = pick(cls, memberName);
  const onProto = pick(cls.prototype, memberName);
  return async (args, ctorArgs) => {
    if (ctorArgs === null) {
      const key = onClass ?? memberName;
      if (typeof cls[key] !== "function") {
        throw new Error(`${ownerName} has no static method ${memberName}`);
      }
      return [await cls[key](...args), null];
    }
    const obj = new cls(...ctorArgs);
    // Prototype first, then the instance: some translations assign methods in
    // the constructor, where only the built object can see them.
    const key = onProto ?? pick(obj, memberName) ?? memberName;
    if (typeof obj[key] !== "function") {
      throw new Error(`${ownerName} has no method ${memberName}`);
    }
    return [await obj[key](...args), state(obj)];
  };
}

(async () => {
  const [root, moduleName, target] = process.argv.slice(2);
  const rel = moduleName.replace(/\./g, "/");
  const url = pathToFileURL(`${root}/${rel}.ts`).href;

  const mod: any = await import(url);
  const call = resolve(mod, target);

  const raw = JSON.parse(readFileSync(0, "utf8"));
  const payload = Array.isArray(raw) ? { inputs: raw, ctor: null } : raw;
  const inputs: any[][] = payload.inputs ?? [];
  const ctor: any[][] | null = payload.ctor ?? null;

  const results: any[] = [];
  for (let i = 0; i < inputs.length; i++) {
    const ctorArgs = ctor !== null && i < ctor.length ? ctor[i] : null;
    try {
      const [raw, after] = await call(inputs[i], ctorArgs);
      // Return values need the same treatment as state: a function that
      // returns a Set hits the identical encoding gap.
      const value = normalize(raw);
      results.push(after === null ? { ok: true, value } : { ok: true, value, state: after });
    } catch (e: any) {
      results.push({ ok: false, error: e?.constructor?.name ?? "Error" });
    }
  }
  process.stdout.write(JSON.stringify(results));
})();
