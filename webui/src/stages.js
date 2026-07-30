// Mapping from pipeline progress events to what the user sees.
//
// Kept pure and exhaustive on purpose. The previous inline version only handled
// samples/scan/analyze and let everything else fall through to a default that
// said "首次需加载识别模型" at 5% — so the moment analysis finished and the
// backend emitted stage="plan", the UI appeared to jump backwards to a
// model-loading screen. See scripts/test_navigation.mjs.

/** Stages the core pipeline emits, in the order they occur. */
export const STAGES = ["prepare", "samples", "scan", "analyze", "cluster", "plan", "execute"];

const LABELS = {
  prepare: "正在准备…",
  samples: "读取人物样本…",
  scan: "扫描照片…",
  cluster: "正在归并相同人物…",
  plan: "正在生成分图方案…",
};

/**
 * Human label for a progress event. Never mentions the recognition model:
 * genuine model work has its own panel (ModelProgress) driven by "model"
 * events, so claiming it here was both wrong and alarming.
 */
export function stageLabel(progress, { executing = false } = {}) {
  const p = progress || {};
  if (p.stage === "analyze") {
    return p.total ? `识别照片 ${p.done}/${p.total}` : "识别照片…";
  }
  if (p.stage === "execute") {
    return p.total ? `整理中 ${p.done}/${p.total}` : "整理中…";
  }
  return LABELS[p.stage] || (executing ? "准备整理…" : "正在准备…");
}

// Analysis dominates the wall clock, so it owns the bulk of the bar and the
// bookend stages get small fixed slices.
const ANALYZE_START = 8;
const ANALYZE_END = 92;

const FIXED = {
  prepare: 0,
  samples: 3,
  scan: 6,
  cluster: 94,
  plan: 97,
};

/**
 * Bar position for a progress event, 0-100.
 *
 * Monotonic across the pipeline: the value never decreases as stages advance,
 * which is what made the old mapping look like it had restarted.
 */
export function stagePercent(progress) {
  const p = progress || {};
  if (p.stage === "analyze") {
    const frac = p.total ? Math.min(Math.max(p.done / p.total, 0), 1) : 0;
    return ANALYZE_START + frac * (ANALYZE_END - ANALYZE_START);
  }
  if (p.stage === "execute") {
    const frac = p.total ? Math.min(Math.max(p.done / p.total, 0), 1) : 0;
    return frac * 100;
  }
  return FIXED[p.stage] ?? 0;
}
