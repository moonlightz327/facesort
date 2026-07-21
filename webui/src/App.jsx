import React, { useEffect, useMemo, useState } from "react";
import { api } from "./api.js";
import { Icon, Spinner, cx } from "./ui.jsx";
import SamplesStep from "./steps/SamplesStep.jsx";
import ConfigStep from "./steps/ConfigStep.jsx";
import PreviewStep from "./steps/PreviewStep.jsx";
import RunStep from "./steps/RunStep.jsx";

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
  });
  const [preview, setPreview] = useState(null); // dry-run result

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  useEffect(() => {
    api.bootstrap().then((b) => {
      setBoot(b);
      setPeople(b.people || []);
      setConfig((c) => ({ ...c, ...camel(b.defaults) }));
    });
  }, []);

  const readySamples = useMemo(
    () => people.filter((p) => p.samples && p.samples.length > 0).length,
    [people]
  );

  const canGo = (target) => {
    if (target <= step) return true;
    if (target >= 1 && config.mode !== "cluster" && readySamples < 1) return false;
    if (target >= 2 && !config.inputDir) return false;
    return true;
  };

  const goto = (target) => {
    if (canGo(target)) {
      // Leaving config invalidates a stale preview.
      if (target === 2 && step !== 2) setPreview(null);
      setStep(target);
    }
  };

  if (!boot) {
    return (
      <div className="flex h-full items-center justify-center bg-slate-50 text-slate-500 dark:bg-slate-950 dark:text-slate-400">
        <Spinner className="w-6 h-6 mr-3" /> 正在启动…
      </div>
    );
  }

  const stepProps = { boot, people, setPeople, config, setConfig, preview, setPreview, goto };

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
            const done = i < step;
            const enabled = canGo(i);
            return (
              <button
                key={s.id}
                onClick={() => goto(i)}
                disabled={!enabled}
                className={cx(
                  "group flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition",
                  active
                    ? "bg-indigo-50 dark:bg-indigo-950/50"
                    : enabled
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
                  {done ? <Icon name="check" className="w-4 h-4" /> : i + 1}
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
                  <span className="block truncate text-xs text-slate-400">{s.hint}</span>
                </span>
              </button>
            );
          })}
        </nav>

        <button
          onClick={() => setDark((d) => !d)}
          className="mt-4 flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
        >
          {dark ? "☀️ 浅色" : "🌙 深色"}
        </button>
      </aside>

      {/* Main */}
      <main className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-8 py-8">
          {step === 0 && <SamplesStep key="s" {...stepProps} />}
          {step === 1 && <ConfigStep key="c" {...stepProps} />}
          {step === 2 && <PreviewStep key="p" {...stepProps} />}
          {step === 3 && <RunStep key="r" {...stepProps} />}
        </div>
      </main>
    </div>
  );
}

function camel(defaults = {}) {
  return {
    threshold: defaults.threshold,
    multiPerson: defaults.multiPerson,
    folderTemplate: defaults.folderTemplate,
    fileTemplate: defaults.fileTemplate,
    minFace: defaults.minFace,
    move: defaults.move,
  };
}
