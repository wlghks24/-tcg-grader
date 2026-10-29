#!/usr/bin/env node
"use strict";
// Exercise the real sw.js install/activate listeners with atomic Cache.addAll.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ORIGIN = "https://cards.example";
const CACHE = "tcg-v276-network-first-runtime";
const OLD = "tcg-v275-network-first-runtime";
const THIRD_PARTY = "unrelated-app-cache";
const url = value => new URL(typeof value === "string" ? value : value.url, ORIGIN + "/").href;

async function scenario({fail = [], quota = false, existingCurrent = false} = {}) {
  const blocked = new Set(fail.map(url));
  const stores = new Map();
  const old = new Map([[url("./index.html"), new Response("last-good-v275")]]);
  stores.set(OLD, old);
  stores.set(THIRD_PARTY, new Map([["keep", new Response("keep")]]));
  if (existingCurrent)
    stores.set(CACHE, new Map([[url("./index.html"), new Response("last-good-v276")]]));
  const events = new Map();
  let skipped = 0, claimed = 0, requests = 0, addAllCount = 0;
  async function network(input) {
    requests++;
    const key = url(input);
    if (blocked.has(key)) throw new Error("network unavailable: " + key);
    return new Response(key.endsWith(".html") ? "<html>current</html>" : "asset", {
      status: 200, headers: {"Content-Type": key.endsWith(".html") ? "text/html" : "text/plain"},
    });
  }
  const caches = {
    async open(name) {
      if (!stores.has(name)) stores.set(name, new Map());
      const rows = stores.get(name);
      return {
        async addAll(requests) {
          addAllCount++;
          const staged = [];
          for (const req of requests) {
            const response = await network(req);
            if (!response.ok || response.type === "opaque")
              throw new Error("critical asset rejected");
            staged.push([url(req), response.clone()]);
          }
          if (quota) throw new Error("quota exceeded");
          // Cache.addAll is atomic: nothing is committed until every fetch succeeds.
          for (const [key, response] of staged) rows.set(key, response);
        },
        async put(input, response) {
          if (quota) throw new Error("quota exceeded");
          rows.set(url(input), response.clone());
        },
        async match(input) {
          const response = rows.get(url(input));
          return response && response.clone();
        },
      };
    },
    async keys() { return [...stores.keys()]; },
    async delete(name) { return stores.delete(name); },
    async match(input) {
      for (const rows of stores.values()) {
        const response = rows.get(url(input));
        if (response) return response.clone();
      }
      return undefined;
    },
  };
  class ScopedRequest {
    constructor(input, options = {}) {
      this.url = url(input);
      this.cache = options.cache;
    }
  }
  const self = {
    location: {origin: ORIGIN, href: ORIGIN + "/sw.js"},
    clients: {claim: async () => { claimed++; }},
    skipWaiting: async () => { skipped++; },
    addEventListener(type, callback) { events.set(type, callback); },
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "sw.js"), "utf8"), {
    self, caches, fetch: network, Request: ScopedRequest,
    URL, Response, Headers, JSON, console,
  }, {filename: "sw.js"});
  async function dispatch(type) {
    let task;
    events.get(type)({waitUntil(promise) { task = promise; }});
    return await task;
  }
  return {dispatch, stores, get skipped() {return skipped;},
    get claimed() {return claimed;}, get requests() {return requests;},
    get addAllCount() {return addAllCount;}};
}

async function run() {
  for (const asset of ["./", "./index.html", "./manifest.webmanifest",
                        "./feature_category_nav.js", "./ui_app_shell_v272.css"]) {
    const state = await scenario({fail: [asset], existingCurrent: true});
    await assert.rejects(state.dispatch("install"), /network unavailable/);
    assert.equal(state.skipped, 0, "failed critical shell must not skipWaiting");
    assert.equal(state.addAllCount, 1);
    assert.equal(await state.stores.get(CACHE).get(url("./index.html")).text(),
      "last-good-v276", "failed install must not corrupt same-name old cache");
    assert.equal(await state.stores.get(OLD).get(url("./index.html")).text(),
      "last-good-v275", "failed install must retain previous generation");
  }
  const quota = await scenario({quota: true, existingCurrent: true});
  await assert.rejects(quota.dispatch("install"), /quota exceeded/);
  assert.equal(quota.skipped, 0);
  assert.equal(await quota.stores.get(CACHE).get(url("./index.html")).text(), "last-good-v276");

  const optional = await scenario({fail: ["./releases.json"]});
  await optional.dispatch("install");
  assert.equal(optional.skipped, 1, "optional live data may be unavailable");
  assert.ok(optional.stores.get(CACHE).has(url("./index.html")));
  assert.equal(optional.stores.get(CACHE).has(url("./releases.json")), false);
  await optional.dispatch("activate");
  assert.equal(optional.claimed, 1);
  assert.equal(optional.stores.has(OLD), false, "obsolete TCG cache removed only after complete shell");
  assert.equal(optional.stores.has(THIRD_PARTY), true, "unrelated caches must not be deleted");

  const all = await scenario();
  await all.dispatch("install");
  await all.dispatch("activate");
  assert.equal(all.skipped, 1);
  assert.equal(all.claimed, 1);
  assert.ok(all.stores.get(CACHE).has(url("./manifest.webmanifest")));

  const corrupt = await scenario({existingCurrent: true});
  await assert.rejects(corrupt.dispatch("activate"), /critical app shell unavailable/);
  assert.equal(corrupt.claimed, 0);
  assert.equal(corrupt.stores.has(OLD), true);
  assert.equal(corrupt.stores.has(THIRD_PARTY), true);
  console.log("PWA critical-shell install/activate: 5 failed-critical + quota + optional + complete + corrupt PASS");
}
run().catch(error => { console.error(error); process.exitCode = 1; });
