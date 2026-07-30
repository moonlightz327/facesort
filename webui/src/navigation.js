// Wizard navigation rules, kept pure so they can be reasoned about and tested
// without React. See scripts/test_navigation.mjs.

export const SETTINGS = 99; // not a wizard step; reachable at any time

export const STEP_LABELS = ["人物样本", "整理设置", "预览确认", "开始整理"];

/** Which wizard step owns the in-flight task, if any. */
export function runningStepOf(task) {
  if (task === "preview") return 2;
  if (task === "organize") return 3;
  return null;
}

/**
 * Why `target` cannot be entered, or null if it can.
 *
 * state: { task, mode, readySamples, inputDir, preview, runResult }
 */
export function blockedReason(state, target) {
  const running = runningStepOf(state.task);
  // Returning to the running step is never blocked. 设置 is reachable at any
  // time, so blocking every step during a task turned it into a one-way door.
  if (target === running) return null;
  if (state.task) return "任务进行中，请先完成或取消";
  if (target >= 1 && state.mode !== "cluster" && (state.readySamples || 0) < 1)
    return "至少需要一个人有样本照片";
  if (target >= 2 && !state.inputDir) return "请先选择照片目录";
  if (target === 3 && !state.preview && !state.runResult) return "请先预览分图结果";
  return null;
}

export function canGo(state, target) {
  return blockedReason(state, target) === null;
}

/**
 * Should entering `target` from `from` discard the cached plan?
 *
 * Only steps that edit inputs invalidate it. Coming back from 设置 or from the
 * results page is not an input change — otherwise a detour to 设置 would throw
 * away a preview that had just finished computing.
 */
export function shouldResetPlan(from, target) {
  return target === 2 && from < 2;
}
