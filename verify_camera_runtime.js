#!/usr/bin/env node
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const html = fs.readFileSync(path.join(__dirname, "index.html"), "utf8");
const match = /<script id="simple-grade-v32-script">([\s\S]*?)<\/script>/.exec(html);
assert.ok(match, "automatic-camera script is missing");

class TestClassList {
  constructor(initial = []) { this.values = new Set(initial); }
  add(...names) { names.forEach((name) => this.values.add(name)); }
  remove(...names) { names.forEach((name) => this.values.delete(name)); }
  contains(name) { return this.values.has(name); }
  toggle(name, force) {
    const enabled = force === undefined ? !this.contains(name) : Boolean(force);
    enabled ? this.add(name) : this.remove(name);
    return enabled;
  }
}

class TestElement {
  constructor(id) {
    this.id = id;
    this.dataset = {};
    this.style = { display: "" };
    this.textContent = "";
    this.innerHTML = "";
    this.src = "";
    this.srcObject = null;
    this.files = [];
    this._value = "";
    this.clickCount = 0;
    this.listeners = new Map();
    this.classList = new TestClassList(id === "out" ? ["hidden"] : []);
    this.videoWidth = id === "gradeCamera" ? 1280 : 0;
    this.videoHeight = id === "gradeCamera" ? 720 : 0;
  }
  set value(next) { this._value = String(next); if (next === "") this.files = []; }
  get value() { return this._value; }
  async play() { if (this.playError) throw this.playError; this.played = true; }
  pause() { this.paused = true; }
  click() { this.clickCount += 1; return typeof this.onclick === "function" ? this.onclick({ type: "click" }) : undefined; }
  dispatchEvent(event) {
    if (event.type === "change" && typeof this.onchange === "function") this.onchange(event);
    for (const callback of this.listeners.get(event.type) || []) callback(event);
    return true;
  }
  addEventListener(type, callback) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(callback);
  }
  removeAttribute(name) { if (name === "src") this.src = ""; }
  scrollIntoView() { this.scrolled = true; }
}

let scene = 0;
let shakeOffset = 0;
let encodeFails = false;
let objectUrlSequence = 0;
const createdObjectUrls = [];
const revokedObjectUrls = [];
const intervalCallbacks = new Map();
let intervalSequence = 0;

class TestCanvas {
  constructor() { this.width = 0; this.height = 0; }
  getContext() {
    const canvas = this;
    return {
      drawImage() {},
      getImageData() {
        const data = new Uint8ClampedArray(canvas.width * canvas.height * 4);
        for (let y = 0; y < canvas.height; y += 1) {
          for (let x = 0; x < canvas.width; x += 1) {
            const index = (y * canvas.width + x) * 4;
            const sx = x + shakeOffset;
            const checker = (Math.floor(sx / 6) + Math.floor(y / 12)) % 2;
            const front = checker ? 205 : 55;
            const value = scene === 0 ? front : 255 - front;
            data[index] = value;
            data[index + 1] = value;
            data[index + 2] = value;
            data[index + 3] = 255;
          }
        }
        return { data };
      },
    };
  }
  toBlob(callback, type) { callback(encodeFails ? null : new Blob([`scene:${scene}`], { type })); }
  toDataURL() { return "data:image/jpeg;base64,Y2FtZXJh"; }
}

class TestFile extends Blob {
  constructor(parts, name, options = {}) { super(parts, options); this.name = name; }
}

class TestDataTransfer {
  constructor() {
    this.files = [];
    this.items = { add: (file) => { this.files.push(file); } };
  }
}

class TestEvent {
  constructor(type, options = {}) { this.type = type; this.bubbles = Boolean(options.bubbles); }
}

function createStream(label) {
  const listeners = new Map();
  const track = {
    label,
    stopped: false,
    constraints: [],
    stop() { this.stopped = true; },
    addEventListener(type, callback) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(callback);
    },
    emit(type) { for (const callback of listeners.get(type) || []) callback(); },
    getCapabilities() { return { focusMode: ["continuous"], exposureMode: ["continuous"], whiteBalanceMode: ["continuous"] }; },
    async applyConstraints(value) { this.constraints.push(value); },
  };
  return {
    label,
    track,
    getTracks() { return [track]; },
    getVideoTracks() { return [track]; },
  };
}

const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, new TestElement(id));
  return elements.get(id);
}

const gameButtons = ["pokemon", "onepiece", "naruto"].map((game) => {
  const button = element(`simple-${game}`);
  button.dataset.simpleGame = game;
  return button;
});

const documentListeners = new Map();
const document = {
  hidden: false,
  getElementById: element,
  querySelectorAll(selector) { return selector === "[data-simple-game]" ? gameButtons : []; },
  createElement(tag) { return tag === "canvas" ? new TestCanvas() : new TestElement(tag); },
  addEventListener(type, callback) {
    if (!documentListeners.has(type)) documentListeners.set(type, []);
    documentListeners.get(type).push(callback);
  },
};

const context = {
  Blob,
  File: TestFile,
  DataTransfer: TestDataTransfer,
  Event: TestEvent,
  Uint8Array,
  URL: {
    createObjectURL() {
      const url = `blob:camera-runtime/${objectUrlSequence++}`;
      createdObjectUrls.push(url);
      return url;
    },
    revokeObjectURL(url) { revokedObjectUrls.push(url); },
  },
  atob(value) { return Buffer.from(value, "base64").toString("binary"); },
  console,
  document,
  navigator: { mediaDevices: { async getUserMedia() { return createStream("default"); } } },
  fetch: async () => ({ json: async () => ({ entries: {} }) }),
  setInterval(callback) { const id = ++intervalSequence; intervalCallbacks.set(id, callback); return id; },
  clearInterval(id) { intervalCallbacks.delete(id); },
  setTimeout,
  clearTimeout,
  __TCG_CAMERA_REQUEST_TIMEOUT_MS__: 25,
  __TCG_CAMERA_FLIP_DELAY_MS__: 20,
  __TCG_CAMERA_CAPTURE_CONFIRM_MS__: 10,
  __TCG_CAMERA_MOTION_THRESHOLD__: 7.5,
  previewObjectUrls: new WeakMap(),
  addEventListener(type, callback) {
    if (!documentListeners.has(`window:${type}`)) documentListeners.set(`window:${type}`, []);
    documentListeners.get(`window:${type}`).push(callback);
  },
  setGame() {},
  escapeDisplayText(value) { return String(value); },
};
context.window = context;

element("simpleGradeResult").style.display = "none";
element("quickCardQuery").value = "";
element("analyze").onclick = async () => {
  assert.ok(element("front")._tcgCapturedFile, "front capture was not delivered to analysis");
  assert.ok(element("back")._tcgCapturedFile, "back capture was not delivered to analysis");
  for (const [id, value] of [["fw", "48%"], ["bw", "47%"], ["corner", "5/100"], ["edge", "6/100"], ["surface", "7/100"]]) element(id).textContent = value;
  element("confidence").textContent = "분석 신뢰도: 90/100";
  element("out").classList.remove("hidden");
};

vm.runInContext(match[1], vm.createContext(context), { filename: "index.html:simple-grade-v32-script" });

async function flush() { await new Promise((resolve) => setImmediate(resolve)); }
async function tick(count) {
  for (let index = 0; index < count; index += 1) {
    for (const callback of [...intervalCallbacks.values()]) callback();
    await flush();
  }
}

async function main() {
  const firstStream = createStream("automatic");
  context.navigator.mediaDevices.getUserMedia = async () => firstStream;
  await element("startAutoCamera").click();
  assert.equal(context.window.tcgCameraRuntime.state().active, true);
  assert.equal(element("manualCapture").style.display, "block");
  assert.equal(element("stopAutoCamera").style.display, "block");
  assert.equal(firstStream.track.constraints.length, 1, "continuous camera modes were not requested");
  assert.equal(firstStream.track.constraints[0].advanced[0].focusMode, "continuous");
  assert.equal(firstStream.track.constraints[0].advanced[0].exposureMode, "continuous");
  assert.equal(firstStream.track.constraints[0].advanced[0].whiteBalanceMode, "continuous");
  assert.equal(context.window.tcgCameraRuntime.version, "v104-camera-shake-stability");

  scene = 0; shakeOffset = 0;
  await tick(7);
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(context.window.tcgCameraRuntime.state().frontReady, true, "front was not automatically captured");
  assert.equal(context.window.tcgCameraRuntime.state().backReady, false);
  assert.equal(element("front").files.length, 1, "DataTransfer capture was not assigned");

  await new Promise((resolve) => setTimeout(resolve, 30));
  await tick(10);
  assert.equal(context.window.tcgCameraRuntime.state().backReady, false, "same front image was incorrectly saved as back");
  assert.match(element("cameraStatus").textContent, /카드를 뒤집/);

  scene = 1;
  await tick(8);
  await new Promise((resolve) => setTimeout(resolve, 130));
  assert.equal(firstStream.track.stopped, true, "camera stream stayed active after both captures");
  assert.equal(element("simpleGradeResult").style.display, "block", "automatic analysis did not finish");
  assert.equal(element("cameraStatus").textContent, "분석 완료");

  const shakeStream = createStream("shake-withhold");
  context.navigator.mediaDevices.getUserMedia = async () => shakeStream;
  await element("startAutoCamera").click();
  scene = 0; shakeOffset = 0;
  for (let i = 0; i < 12; i += 1) { shakeOffset = i % 2 ? 9 : 0; await tick(1); }
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(context.window.tcgCameraRuntime.state().frontReady, false, "camera shake incorrectly triggered automatic capture");
  assert.match(element("cameraStatus").textContent, /흔들림|고정/);
  shakeOffset = 0;
  await tick(7);
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(context.window.tcgCameraRuntime.state().frontReady, true, "stable frame did not recover after shake");
  element("stopAutoCamera").click();

  const lastMomentStream = createStream("last-moment-shake");
  context.navigator.mediaDevices.getUserMedia = async () => lastMomentStream;
  await element("startAutoCamera").click();
  scene = 0; shakeOffset = 0;
  await tick(7);
  shakeOffset = 9;
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(context.window.tcgCameraRuntime.state().frontReady, false, "last-moment shake was captured instead of being withheld");
  assert.match(element("cameraStatus").textContent, /마지막 순간 흔들림|고정/);
  element("stopAutoCamera").click();
  shakeOffset = 0;

  context.DataTransfer = undefined;
  shakeOffset = 0;
  const fallbackStream = createStream("no-data-transfer");
  context.navigator.mediaDevices.getUserMedia = async () => fallbackStream;
  await element("startAutoCamera").click();
  scene = 0;
  await element("manualCapture").click();
  await new Promise((resolve) => setTimeout(resolve, 30));
  await element("manualCapture").click();
  assert.equal(context.window.tcgCameraRuntime.state().backReady, false, "manual capture stored the same front image as back");
  assert.match(element("cameraStatus").textContent, /앞면과 다른 화면/);
  scene = 1;
  await element("manualCapture").click();
  await new Promise((resolve) => setTimeout(resolve, 130));
  assert.equal(element("front").files.length, 0, "fallback unexpectedly depended on DataTransfer");
  assert.ok(element("front")._tcgCapturedFile && element("back")._tcgCapturedFile, "iOS-style capture fallback lost files");
  assert.equal(fallbackStream.track.stopped, true);

  context.DataTransfer = TestDataTransfer;
  const priorAnalyzer = element("analyze").onclick;
  const analysisFailureStream = createStream("analysis-failure");
  context.navigator.mediaDevices.getUserMedia = async () => analysisFailureStream;
  element("analyze").onclick = async () => { throw new Error("decode failed"); };
  await element("startAutoCamera").click();
  scene = 0;
  await element("manualCapture").click();
  await new Promise((resolve) => setTimeout(resolve, 30));
  scene = 1;
  await element("manualCapture").click();
  await new Promise((resolve) => setTimeout(resolve, 130));
  assert.match(element("cameraStatus").textContent, /분석 중 오류/);
  assert.equal(analysisFailureStream.track.stopped, true);
  element("analyze").onclick = priorAnalyzer;

  const encodingFailureStream = createStream("encoding-failure");
  context.navigator.mediaDevices.getUserMedia = async () => encodingFailureStream;
  encodeFails = true;
  await element("startAutoCamera").click();
  await element("manualCapture").click();
  assert.equal(context.window.tcgCameraRuntime.state().frontReady, false);
  assert.match(element("cameraStatus").textContent, /저장하지 못했습니다/);
  encodeFails = false;
  element("stopAutoCamera").click();

  const zeroFrameStream = createStream("zero-frame");
  context.navigator.mediaDevices.getUserMedia = async () => zeroFrameStream;
  await element("startAutoCamera").click();
  element("gradeCamera").videoWidth = 0;
  await element("manualCapture").click();
  assert.match(element("cameraStatus").textContent, /영상이 아직 준비되지/);
  element("gradeCamera").videoWidth = 1280;
  element("stopAutoCamera").click();

  const stoppable = createStream("stop-button");
  context.navigator.mediaDevices.getUserMedia = async () => stoppable;
  await element("startAutoCamera").click();
  element("stopAutoCamera").click();
  assert.equal(stoppable.track.stopped, true);
  assert.equal(context.window.tcgCameraRuntime.state().active, false);
  assert.match(element("cameraStatus").textContent, /중지했습니다/);

  const hiddenStream = createStream("hidden-page");
  context.navigator.mediaDevices.getUserMedia = async () => hiddenStream;
  await element("startAutoCamera").click();
  document.hidden = true;
  for (const callback of documentListeners.get("visibilitychange") || []) callback();
  document.hidden = false;
  assert.equal(hiddenStream.track.stopped, true, "hidden page kept the camera stream active");
  assert.match(element("cameraStatus").textContent, /백그라운드/);

  const pagehideStream = createStream("pagehide");
  context.navigator.mediaDevices.getUserMedia = async () => pagehideStream;
  await element("startAutoCamera").click();
  for (const callback of documentListeners.get("window:pagehide") || []) callback();
  assert.equal(pagehideStream.track.stopped, true, "pagehide kept the camera stream active");

  const constraintsFallbackStream = createStream("overconstrained-fallback");
  let constraintsCalls = 0;
  context.navigator.mediaDevices.getUserMedia = async () => {
    constraintsCalls += 1;
    if (constraintsCalls === 1) { const error = new Error("unsupported constraints"); error.name = "OverconstrainedError"; throw error; }
    return constraintsFallbackStream;
  };
  await element("startAutoCamera").click();
  assert.equal(constraintsCalls, 2, "overconstrained camera request did not use generic video fallback");
  context.window.tcgCameraRuntime.stop();
  assert.equal(constraintsFallbackStream.track.stopped, true);

  const playFailureStream = createStream("video-play-failure");
  const captureBeforePlayFailure = { name: "before-play-failure.jpg" };
  element("front")._tcgCapturedFile = captureBeforePlayFailure;
  element("gradeCamera").playError = new Error("video play failed");
  context.navigator.mediaDevices.getUserMedia = async () => playFailureStream;
  await element("startAutoCamera").click();
  element("gradeCamera").playError = null;
  assert.equal(playFailureStream.track.stopped, true, "stream survived video.play failure");
  assert.equal(element("front")._tcgCapturedFile, captureBeforePlayFailure, "video.play failure erased an existing capture");

  context.navigator.mediaDevices = undefined;
  const pickerCount = element("front").clickCount;
  await element("startAutoCamera").click();
  assert.equal(element("front").clickCount, pickerCount + 1, "insecure-context file camera fallback did not open");
  assert.match(element("cameraStatus").textContent, /실시간 자동촬영을 사용할 수 없습니다/);

  context.navigator.mediaDevices = { getUserMedia: async () => { const error = new Error("denied"); error.name = "NotAllowedError"; throw error; } };
  const preservedCapture = { name: "preserved-front.jpg" };
  element("front")._tcgCapturedFile = preservedCapture;
  await element("startAutoCamera").click();
  assert.match(element("cameraStatus").textContent, /권한이 거부/);
  assert.equal(element("manualCapture").style.display, "none");
  assert.equal(element("front")._tcgCapturedFile, preservedCapture, "permission denial erased an existing capture");

  let resolveTimedOut;
  const timedOutStream = createStream("permission-timeout-late-stream");
  context.navigator.mediaDevices = { getUserMedia: () => new Promise((resolve) => { resolveTimedOut = resolve; }) };
  await element("startAutoCamera").click();
  assert.match(element("cameraStatus").textContent, /권한 응답이 30초 동안 없어/);
  assert.equal(element("front")._tcgCapturedFile, preservedCapture, "permission timeout erased an existing capture");
  resolveTimedOut(timedOutStream);
  await flush();
  assert.equal(timedOutStream.track.stopped, true, "late stream after permission timeout was not stopped");

  const endedStream = createStream("unexpected-track-ending");
  context.navigator.mediaDevices = { getUserMedia: async () => endedStream };
  await element("startAutoCamera").click();
  endedStream.track.emit("ended");
  assert.equal(context.window.tcgCameraRuntime.state().active, false, "ended camera track stayed active");
  assert.match(element("cameraStatus").textContent, /카메라 연결이 종료/);

  let resolveSlow;
  const slow = createStream("slow-old-request");
  const current = createStream("current-request");
  let requestCount = 0;
  context.navigator.mediaDevices = { getUserMedia: () => {
    requestCount += 1;
    return requestCount === 1 ? new Promise((resolve) => { resolveSlow = resolve; }) : Promise.resolve(current);
  } };
  const oldRequest = element("startAutoCamera").click();
  const newRequest = element("startAutoCamera").click();
  await newRequest;
  resolveSlow(slow);
  await oldRequest;
  assert.equal(slow.track.stopped, true, "late camera permission result replaced the current stream");
  assert.equal(current.track.stopped, false);
  context.window.tcgCameraRuntime.stop();
  assert.equal(current.track.stopped, true);

  assert.ok(revokedObjectUrls.length >= 2, "camera preview object URLs were not released on retake");
  assert.ok(createdObjectUrls.length >= revokedObjectUrls.length);
  console.log("PASS: shake withholding/recovery, pre-capture shake confirmation, continuous focus/exposure/white-balance request, automatic front/back capture, duplicate-side prevention, manual duplicate-side prevention, iOS file fallback, encode/frame/analysis failures, stop/permission/insecure-context/background/pagehide handling, constraints fallback, video-play failure cleanup, permission timeout, unexpected track ending, previous captures preserved, late-request isolation and camera resource cleanup");
}

main().catch((error) => {
  try { context.window.tcgCameraRuntime?.stop(); } catch (_) {}
  console.error(error);
  process.exitCode = 1;
});
