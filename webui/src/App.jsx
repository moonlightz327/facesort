import React, { useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import { Icon, Spinner, cx } from "./ui.jsx";
import SamplesStep from "./steps/SamplesStep.jsx";
import ConfigStep from "./steps/ConfigStep.jsx";
import PreviewStep from "./steps/PreviewStep.jsx";
import RunStep from "./steps/RunStep.jsx";
import SettingsPage from "./SettingsPage.jsx";
import {
  SETTINGS,
  blockedReason as navBlockedReason,
  runningStepOf,
  shouldResetPlan,
} from "./navigation.js";

const STEPS = [
  { id: "samples", label: "人物样本", hint: "登记要识别的人", icon: "users" },
  { id: "config", label: "整理设置", hint: "选择照片与规则", icon: "sliders" },
  { id: "preview", label: "预览确认", hint: "先看分好的样子", icon: "eye" },
  { id: "run", label: "开始整理", hint: "执行并复核", icon: "check" },
];

export default function App() {
  const [dark, setDark] = useState(
    () => window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
  );
  const [boot, setBoot] = useState(null);
  const [step, setStep] = useState(0);
  const [people, setPeople] = useState([]);
  const [settings, setSettings] = useState({});
  const [config, setConfig] = useState({
    mode: "sample", // "sample" (用样本) | "cluster" (无样本自动分组)
    inputDir: "",
    outputDir: "",
    threshold: 0.4,
    multiPerson: "primary",
    folderTemplate: "{person}",
    fileTemplate: "{orig_name}{ext}",
    minFace: 40,
    move: false,
    groupSubfolders: false,
    workers: 0, // 0 = auto-size the analyze thread pool
    decodeMaxSide: 1400, // 0 = decode at full resolution (slower)
    clusterNames: {}, // 人物N -> 用户自定义名字（聚类模式）
  });
  const [preview, setPreview] = useState(null); // dry-run result
  const [runResult, setRunResult] = useState(null); // completed organize result
  const [task, setTask] = useState(null); // "preview" | "organize" while running
  const [model, setModel] = useState(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  useEffect(() => {
    api.bootstrap().then((b) => {
      setBoot(b);
      setPeople(b.people || []);
      setModel(b.model || null);
      setSettings(b.defaults || {});
      setConfig((c) => ({ ...c, ...(b.defaults || {}) }));
    });
  }, []);

  const readySamples = useMemo(
    () => people.filter((p) => p.samples && p.samples.length > 0).length,
    [people]
  );

  // The step that owns the in-flight task, so it always stays reachable.
  const runningStep = runningStepOf(task);

  // Rules live in navigation.js so they stay testable; the rail surfaces the
  // reason as a tooltip instead of just looking broken.
  const navState = {
    task,
    mode: config.mode,
    readySamples,
    inputDir: config.inputDir,
    preview,
    runResult,
  };
  const blockedReason = (target) => navBlockedReason(navState, target);

  const canGo = (target) => blockedReason(target) === null;

  const goto = (target) => {
    if (!canGo(target)) return;
    // Coming back to a step whose task is still running must not reset it.
    if (target === runningStep) {
      setStep(target);
      return;
    }
    if (shouldResetPlan(step, target)) {
      setPreview(null);
      setRunResult(null);
      setConfig((c) => ({ ...c, clusterNames: {} }));
    }
    setStep(target);
  };

  /** Start a fresh batch after a finished run. */
  const startOver = () => {
    setPreview(null);
    setRunResult(null);
    setConfig((c) => ({ ...c, clusterNames: {} }));
    setStep(0);
  };

  if (!boot) {
    return (
      <div className="flex h-full items-center justify-center bg-slate-50 text-slate-500 dark:bg-slate-950 dark:text-slate-400">
        <Spinner className="w-6 h-6 mr-3" /> 正在启动…
      </div>
    );
  }

  const stepProps = {
    boot, people, setPeople, config, setConfig, preview, setPreview,
    runResult, setRunResult, goto, task, setTask, model, setModel, startOver,
  };

  return (
    <div className="flex h-full bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      {/* Left rail */}
      <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white/70 px-4 py-6 backdrop-blur dark:border-slate-800 dark:bg-slate-900/60">
        <div className="mb-8 flex items-center gap-2.5 px-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-sm shadow-indigo-600/30">
            <Icon name="users" className="w-5 h-5" />
          </div>
          <div>
            <div className="text-[15px] font-semibold leading-tight">FaceSort</div>
            <div className="text-xs text-slate-400">分图 · 按人归类</div>
          </div>
        </div>

        <nav className="flex-1 space-y-1">
          {STEPS.map((s, i) => {
            const active = i === step;
            const done = step !== SETTINGS && i < step;
            const reason = blockedReason(i);
            const running = i === runningStep;
            return (
              <button
                key={s.id}
                onClick={() => goto(i)}
                disabled={!!reason}
                title={reason || ""}
                className={cx(
                  "group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition",
                  active
                    ? "bg-indigo-50 dark:bg-indigo-950/50"
                    : !reason
                    ? "hover:bg-slate-100 dark:hover:bg-slate-800"
                    : "opacity-40 cursor-not-allowed"
                )}
              >
                <span
                  className={cx(
                    "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-xs font-semibold",
                    active
                      ? "bg-indigo-600 text-white"
                      : done
                      ? "bg-emerald-500 text-white"
                      : "bg-slate-200 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
                  )}
                >
                  {running ? (
                    <Spinner className="w-4 h-4" />
                  ) : done ? (
                    <Icon name="check" className="w-4 h-4" />
                  ) : (
                    i + 1
                  )}
                </span>
                <span className="min-w-0">
                  <span
                    className={cx(
                      "block text-sm font-medium leading-tight",
                      active ? "text-indigo-700 dark:text-indigo-300" : ""
                    )}
                  >
                    {s.label}
                  </span>
                  <span className="block truncate text-xs text-slate-400">
                    {running ? "进行中…" : s.hint}
                  </span>
                </span>
              </button>
            );
          })}
        </nav>

        {task && (
          <div className="mb-2 rounded-lg bg-amber-50 px-3 py-2 text-[11px] leading-relaxed text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
            任务进行中，其他步骤暂时锁定。
            {step !== runningStep && (
              <button
                onClick={() => goto(runningStep)}
                className="mt-1 block font-medium underline hover:no-underline"
              >
                返回「{STEPS[runningStep]?.label}」
              </button>
            )}
          </div>
        )}

        <button
          onClick={() => setStep(SETTINGS)}
          className={cx(
            "flex items-center gap-3 rounded-xl px-3 py-2.5 text-left transition",
            step === SETTINGS
              ? "bg-indigo-50 dark:bg-indigo-950/50"
              : "hover:bg-slate-100 dark:hover:bg-slate-800"
          )}
        >
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-slate-200 text-slate-500 dark:bg-slate-800 dark:text-slate-400">
            <Icon name="sliders" className="w-4 h-4" />
          </span>
          <span className="min-w-0 flex-1">
            <span
              className={cx(
                "block text-sm font-medium leading-tight",
                step === SETTINGS ? "text-indigo-700 dark:text-indigo-300" : ""
              )}
            >
              设置
            </span>
            <span className="block truncate text-xs text-slate-400">
              {model && !model.installed ? "模型未安装" : "模型与默认值"}
            </span>
          </span>
          {model && !model.installed && (
            <span className="h-2 w-2 shrink-0 rounded-full bg-amber-500" />
          )}
        </button>

        <button
          onClick={() => setDark((d) => !d)}
          className="mt-2 flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
        >
          {dark ? "☀️ 浅色" : "🌙 深色"}
        </button>
      </aside>

      {/* Main */}
      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-8 py-8">
          {/* Nudge the model install before it blocks a sort mid-flow. */}
          {model && !model.installed && step !== SETTINGS && !task && (
            <button
              onClick={() => setStep(SETTINGS)}
              className="mb-6 flex w-full items-center gap-2 rounded-xl bg-amber-50 px-4 py-3 text-left text-sm text-amber-700 hover:bg-amber-100 dark:bg-amber-950/40 dark:text-amber-300 dark:hover:bg-amber-950/60"
            >
              <Icon name="warning" className="w-4 h-4 shrink-0" />
              <span className="flex-1">
                人脸识别模型还没安装（约 {model.sizeMB || 289}MB）。建议先到「设置」装好，避免整理时才开始等下载。
              </span>
              <Icon name="arrowRight" className="w-4 h-4 shrink-0" />
            </button>
          )}

          {step === SETTINGS && task && (
            <button
              onClick={() => goto(runningStep)}
              className="mb-6 flex w-full items-center gap-2 rounded-xl bg-indigo-50 px-4 py-3 text-left text-sm text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-950/40 dark:text-indigo-300 dark:hover:bg-indigo-950/60"
            >
              <Spinner className="w-4 h-4 shrink-0" />
              <span className="flex-1">
                「{STEPS[runningStep]?.label}」正在进行中，点这里返回查看进度。
              </span>
              <Icon name="arrowRight" className="w-4 h-4 shrink-0" />
            </button>
          )}

          {step === SETTINGS ? (
            <SettingsPage
              boot={boot}
              model={model}
              setModel={setModel}
              settings={settings}
              setSettings={(s) => {
                setSettings(s);
                setConfig((c) => ({ ...c, ...s }));
              }}
            />
          ) : (
            <>
              {step === 0 && <SamplesStep key="s" {...stepProps} />}
              {step === 1 && <ConfigStep key="c" {...stepProps} />}
              {step === 2 && <PreviewStep key="p" {...stepProps} />}
              {step === 3 && <RunStep key="r" {...stepProps} />}
            </>
          )}
        </div>
      </main>
    </div>
  );
}
