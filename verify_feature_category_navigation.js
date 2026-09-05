#!/usr/bin/env node
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "feature_category_nav.js"), "utf8");

class FakeElement {
  constructor(id, { href = "", panel = "" } = {}) {
    this.id = id;
    this.dataset = panel ? { featureOpenPanel: panel } : {};
    this.hrefValue = href;
    this.listeners = new Map();
    this.clickCount = 0;
    this.scrollCount = 0;
  }
  addEventListener(type, callback) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(callback);
  }
  emit(type) {
    const event = { type, prevented: false, preventDefault() { this.prevented = true; } };
    for (const callback of this.listeners.get(type) || []) callback(event);
    return event;
  }
  getAttribute(name) { return name === "href" ? this.hrefValue : null; }
  click() {
    this.clickCount += 1;
    for (const callback of this.listeners.get("click") || []) callback({ type: "click", preventDefault() {} });
  }
  scrollIntoView() { this.scrollCount += 1; }
}

const releaseBoard = new FakeElement("releaseBoard");
const grade = new FakeElement("simpleGradeV32");
const promoTab = new FakeElement("promoTab");
promoTab.dataset = { topPanel: "promoPanel" };
const releaseTab = new FakeElement("releaseTab");
releaseTab.dataset = { topPanel: "releasePanel" };
const purchaseTab = new FakeElement("purchaseTab");
purchaseTab.dataset = { topPanel: "purchasePanel" };

const promoShortcut = new FakeElement("promoShortcut", { href: "#releaseBoard", panel: "promoPanel" });
const gradeShortcut = new FakeElement("gradeShortcut", { href: "#simpleGradeV32" });
const badShortcut = new FakeElement("badShortcut", { href: "#missingTarget" });

const byId = new Map([
  ["releaseBoard", releaseBoard],
  ["simpleGradeV32", grade],
]);
const shortcuts = [promoShortcut, gradeShortcut, badShortcut];
const tabs = [releaseTab, promoTab, purchaseTab];

const document = {
  getElementById(id) { return byId.get(id) || null; },
  querySelectorAll(selector) {
    if (selector === ".feature-shortcut") return shortcuts;
    if (selector === ".top-info-tab") return tabs;
    return [];
  },
};

const context = vm.createContext({
  document,
  window: {},
  console,
  Set,
  Object,
  String,
  Boolean,
  setTimeout(callback) { callback(); return 1; },
});

vm.runInContext(source, context, { filename: "feature_category_nav.js" });

assert.ok(context.window.TCGFeatureCategoryNav, "navigation API was not exposed");
assert.equal(context.window.TCGFeatureCategoryNav.version, "v26-category-nav");
assert.equal(context.window.TCGFeatureCategoryNav.targetExists("simpleGradeV32"), true);
assert.equal(context.window.TCGFeatureCategoryNav.targetExists("missingTarget"), false);
assert.equal(context.window.TCGFeatureCategoryNav.targetExists("../unsafe"), false);

const promoEvent = promoShortcut.emit("click");
assert.equal(promoEvent.prevented, true);
assert.equal(promoTab.clickCount, 1, "promo category did not activate the promo top panel");
assert.equal(releaseBoard.scrollCount, 1, "promo category did not scroll to the top information board");

const gradeEvent = gradeShortcut.emit("click");
assert.equal(gradeEvent.prevented, true);
assert.equal(grade.scrollCount, 1, "grade shortcut did not scroll to grading");

const badEvent = badShortcut.emit("click");
assert.equal(badEvent.prevented, true);
assert.equal(context.window.TCGFeatureCategoryNav.navigateShortcut(badShortcut), false);

assert.equal(context.window.TCGFeatureCategoryNav.activateTopPanel("purchasePanel"), true);
assert.equal(purchaseTab.clickCount, 1);
assert.equal(context.window.TCGFeatureCategoryNav.activateTopPanel("notAllowed"), false);

console.log("PASS: category shortcuts, top-panel activation, target validation and safe navigation");
