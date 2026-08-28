#!/usr/bin/env node
"use strict";

// Exercise the real service worker with browser-compatible Request/Response objects.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const origin = "https://cards.example";
const listeners = new Map();
const saved = new Map();
let network = async () => new Response("unconfigured", { status: 500 });
let cacheUnavailable = false;

function cacheKey(request) {
  return new URL(typeof request === "string" ? request : request.url, `${origin}/`).href;
}

const cache = {
  async addAll() {},
  async put(request, response) {
    if (cacheUnavailable) throw new Error("storage quota exceeded");
    saved.set(cacheKey(request), response.clone());
  },
};

const caches = {
  async open() { return cache; },
  async keys() { return []; },
  async delete() { return true; },
  async match(request) {
    const response = saved.get(cacheKey(request));
    return response ? response.clone() : undefined;
  },
};

const worker = {
  location: { origin },
  clients: { claim: async () => {} },
  skipWaiting: async () => {},
  addEventListener(name, callback) { listeners.set(name, callback); },
};

const context = vm.createContext({
  URL,
  Response,
  JSON,
  caches,
  self: worker,
  fetch: (...args) => network(...args),
});
vm.runInContext(fs.readFileSync(path.join(__dirname, "sw.js"), "utf8"), context, { filename: "sw.js" });

async function request(url, mode = "cors", method = "GET") {
  let response;
  listeners.get("fetch")({
    request: { url: new URL(url, `${origin}/`).href, method, mode },
    respondWith(promise) { response = promise; },
  });
  return response ? await response : undefined;
}

async function main() {
  assert.equal(typeof listeners.get("fetch"), "function");

  network = async () => new Response(JSON.stringify({ generation: 1 }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
  let response = await request("/releases.json");
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { generation: 1 });

  saved.set(`${origin}/supplementary_candidates.json`, new Response(JSON.stringify({ generation: 1 }), {
    headers: { "Content-Type": "application/json" },
  }));
  network = async () => new Response(JSON.stringify({ generation: 2 }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
  response = await request("/supplementary_candidates.json");
  assert.deepEqual(await response.json(), { generation: 2 }, "supplementary event data remained stuck in an old cache");
  assert.deepEqual(await saved.get(`${origin}/supplementary_candidates.json`).clone().json(), { generation: 2 });

  saved.set(`${origin}/social_event_candidates.json`, new Response(JSON.stringify({ generation: 3 }), {
    headers: { "Content-Type": "application/json" },
  }));
  network = async () => new Response(JSON.stringify({ generation: 4 }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
  response = await request("/social_event_candidates.json");
  assert.deepEqual(await response.json(), { generation: 4 }, "social/Google event data remained stuck in an old cache");
  assert.deepEqual(await saved.get(`${origin}/social_event_candidates.json`).clone().json(), { generation: 4 });

  network = async () => new Response("temporary failure", { status: 500 });
  response = await request("/releases.json");
  assert.equal(response.status, 500);
  assert.deepEqual(await saved.get(`${origin}/releases.json`).clone().json(), { generation: 1 });

  network = async () => { throw new Error("offline"); };
  response = await request("/releases.json");
  assert.deepEqual(await response.json(), { generation: 1 });

  saved.set(`${origin}/index.html`, new Response("<html>verified offline page</html>", {
    headers: { "Content-Type": "text/html" },
  }));
  response = await request("/market_prices.json");
  assert.equal(response.status, 503);
  assert.match(response.headers.get("Content-Type"), /application\/json/);
  assert.equal((await response.json()).ok, false);

  response = await request("/unknown-page", "navigate");
  assert.equal(await response.text(), "<html>verified offline page</html>");
  response = await request("/missing-icon.svg");
  assert.equal(response.status, 503);
  assert.ok(!response.headers.get("Content-Type").includes("html"));

  assert.equal(await request("https://outside.example/track.json"), undefined);
  assert.equal(await request("/api/health"), undefined);
  assert.equal(await request("/index.html", "cors", "POST"), undefined);

  cacheUnavailable = true;
  network = async () => new Response("fresh success", { status: 200 });
  response = await request("/exchange_rates.json");
  assert.equal(response.status, 200);
  assert.equal(await response.text(), "fresh success");

  console.log("PASS: service-worker error cache isolation, supplementary + social/Google event freshness, JSON offline responses, same-origin policy and quota fallback");
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exitCode = 1;
});
