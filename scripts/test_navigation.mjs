// Wizard navigation rules. Run: node scripts/test_navigation.mjs
//
// Regression cover for the "clicking 设置 mid-run traps you" bug: 设置 is
// reachable at any time, but every wizard step was blocked while a task ran, so
// there was no way back to the running step.

import assert from "node:assert/strict";
import {
  blockedReason,
  canGo,
  runningStepOf,
  shouldResetPlan,
} from "../webui/src/navigation.js";

let passed = 0;
function test(name, fn) {
  try {
    fn();
    passed++;
  } catch (e) {
    console.error(`FAIL: ${name}\n  ${e.message}`);
    process.exitCode = 1;
  }
}

const ready = {
  task: null,
  mode: "sample",
  readySamples: 1,
  inputDir: "/photos",
  preview: null,
  runResult: null,
};

test("runningStepOf maps tasks to their step", () => {
  assert.equal(runningStepOf(null), null);
  assert.equal(runningStepOf("preview"), 2);
  assert.equal(runningStepOf("organize"), 3);
});

test("a running preview can always be returned to", () => {
  const s = { ...ready, task: "preview" };
  assert.equal(blockedReason(s, 2), null, "must be able to go back to preview");
  assert.ok(canGo(s, 2));
});

test("a running organize can always be returned to", () => {
  const s = { ...ready, task: "organize" };
  assert.equal(blockedReason(s, 3), null, "must be able to go back to run");
  assert.ok(canGo(s, 3));
});

test("other steps stay locked while a task runs", () => {
  const s = { ...ready, task: "preview" };
  for (const target of [0, 1, 3]) {
    assert.equal(blockedReason(s, target), "任务进行中，请先完成或取消");
  }
});

test("the trap is gone: from 设置 there is always a reachable step", () => {
  for (const task of ["preview", "organize"]) {
    const s = { ...ready, task };
    const reachable = [0, 1, 2, 3].filter((t) => canGo(s, t));
    assert.deepEqual(reachable, [runningStepOf(task)],
      `task=${task} should leave exactly its own step reachable`);
  }
});

test("samples are required before leaving step 0 in sample mode", () => {
  const s = { ...ready, readySamples: 0 };
  assert.equal(blockedReason(s, 1), "至少需要一个人有样本照片");
  assert.equal(blockedReason(s, 0), null);
});

test("cluster mode needs no samples", () => {
  const s = { ...ready, mode: "cluster", readySamples: 0 };
  assert.equal(blockedReason(s, 1), null);
});

test("an input directory is required before preview", () => {
  const s = { ...ready, inputDir: "" };
  assert.equal(blockedReason(s, 2), "请先选择照片目录");
});

test("the run step requires a preview or a finished run", () => {
  assert.equal(blockedReason(ready, 3), "请先预览分图结果");
  assert.equal(blockedReason({ ...ready, preview: {} }, 3), null);
  assert.equal(blockedReason({ ...ready, runResult: {} }, 3), null);
});

test("editing inputs invalidates the plan", () => {
  assert.equal(shouldResetPlan(0, 2), true);
  assert.equal(shouldResetPlan(1, 2), true);
});

test("a detour to 设置 or back from results keeps the plan", () => {
  assert.equal(shouldResetPlan(99, 2), false, "returning from 设置 must keep it");
  assert.equal(shouldResetPlan(3, 2), false, "returning from results must keep it");
  assert.equal(shouldResetPlan(2, 2), false);
});

test("non-preview targets never reset the plan", () => {
  for (const target of [0, 1, 3, 99]) {
    assert.equal(shouldResetPlan(0, target), false);
  }
});

if (!process.exitCode) console.log(`navigation: ${passed} passed`);
