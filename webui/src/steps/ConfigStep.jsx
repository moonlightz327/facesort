import React, { useEffect, useState } from "react";
import { api } from "../api.js";
import { Button, Card, Icon, Badge, cx } from "../ui.jsx";
import { StepHeader, StepNav } from "./StepShell.jsx";

const STRATEGY_CARDS = [
  { id: "primary", title: "归入主要人物", desc: "合影只放到最像主体的那个人的文件夹（按大小、居中、相似度综合判断）", emoji: "🎯" },
  { id: "all", title: "每人都存一份", desc: "合影复制到每个认出的人的文件夹，谁的相册里都有", emoji: "👥" },
  { id: "group", title: "单独放进合影", desc: "把多人合影统一放到「_合影」文件夹里", emoji: "🖼️" },
];

const THRESH_STOPS = [
  { v: 0.3, label: "宽松" },
  { v: 0.4, label: "推荐" },
  { v: 0.5, label: "严格" },
];

export default function ConfigStep({ boot, config, setConfig, goto }) {
  const [example, setExample] = useState("");
  const [nameError, setNameError] = useState("");
  const [advanced, setAdvanced] = useState(false);
  const set = (patch) => setConfig((c) => ({ ...c, ...patch }));

  useEffect(() => {
    api.previewName(config.folderTemplate, config.fileTemplate).then((r) => {
      if (r.ok) {
        setExample(r.example);
        setNameError("");
      } else {
        setNameError(r.error);
      }
    });
  }, [config.folderTemplate, config.fileTemplate]);

  const pick = async (which) => {
    const path = await api.pickFolder(which === "input" ? "选择照片目录" : "选择输出目录");
    if (path) set(which === "input" ? { inputDir: path } : { outputDir: path });
  };

  const presets = boot.folderPresets || [];
  const activePreset = presets.find(
    (p) => p.folder === config.folderTemplate && p.file === config.fileTemplate
  );

  return (
    <div>
      <StepHeader title="整理设置" desc="选择要整理的照片，设定归类与命名规则。" />

      {/* Folders */}
      <Card className="mb-5 p-5">
        <FolderRow
          label="照片目录"
          hint="要整理的照片所在的文件夹（会递归扫描子文件夹）"
          value={config.inputDir}
          placeholder="尚未选择"
          onPick={() => pick("input")}
        />
        <div className="my-4 h-px bg-slate-100 dark:bg-slate-800" />
        <FolderRow
          label="输出目录"
          hint="整理结果存放位置，留空则默认放在照片目录下的 _sorted"
          value={config.outputDir}
          placeholder={config.inputDir ? `${config.inputDir}/_sorted（默认）` : "默认 照片目录/_sorted"}
          onPick={() => pick("output")}
          onClear={config.outputDir ? () => set({ outputDir: "" }) : null}
        />
      </Card>

      {/* Multi-person strategy */}
      <SectionTitle>合影里有多个人时…</SectionTitle>
      <div className="mb-5 grid grid-cols-3 gap-3">
        {STRATEGY_CARDS.map((s) => {
          const active = config.multiPerson === s.id;
          return (
            <button
              key={s.id}
              onClick={() => set({ multiPerson: s.id })}
              className={cx(
                "rounded-2xl border p-4 text-left transition",
                active
                  ? "border-indigo-500 bg-indigo-50 ring-2 ring-indigo-500/20 dark:bg-indigo-950/40"
                  : "border-slate-200 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-slate-700"
              )}
            >
              <div className="mb-1.5 text-2xl">{s.emoji}</div>
              <div className={cx("text-sm font-semibold", active && "text-indigo-700 dark:text-indigo-300")}>
                {s.title}
              </div>
              <div className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">{s.desc}</div>
            </button>
          );
        })}
      </div>
      {config.multiPerson === "group" && (
        <label className="mb-5 -mt-2 flex items-center gap-2 px-1 text-sm text-slate-600 dark:text-slate-300">
          <input
            type="checkbox"
            checked={config.groupSubfolders}
            onChange={(e) => set({ groupSubfolders: e.target.checked })}
            className="h-4 w-4 rounded accent-indigo-600"
          />
          合影内再按人名组合建子文件夹（如「张三+李四」）
        </label>
      )}

      {/* Threshold */}
      <SectionTitle>{config.mode === "cluster" ? "分组精细度" : "识别严格度"}</SectionTitle>
      <Card className="mb-5 p-5">
        <input
          type="range"
          min="0.3"
          max="0.55"
          step="0.01"
          value={config.threshold}
          onChange={(e) => set({ threshold: parseFloat(e.target.value) })}
          className="w-full accent-indigo-600"
        />
        <div className="mt-2 flex justify-between text-xs text-slate-400">
          <span>宽松（认得多，可能认错）</span>
          <span className="font-medium text-slate-600 dark:text-slate-300">当前 {config.threshold.toFixed(2)}</span>
          <span>严格（更准，可能漏认）</span>
        </div>
        <div className="mt-3 flex gap-2">
          {THRESH_STOPS.map((s) => (
            <button
              key={s.v}
              onClick={() => set({ threshold: s.v })}
              className={cx(
                "rounded-lg px-2.5 py-1 text-xs",
                Math.abs(config.threshold - s.v) < 0.005
                  ? "bg-indigo-600 text-white"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-300"
              )}
            >
              {s.label} {s.v.toFixed(2)}
            </button>
          ))}
        </div>
      </Card>

      {/* Naming */}
      <SectionTitle>文件夹与命名规则</SectionTitle>
      <Card className="mb-5 p-5">
        <div className="mb-3 flex flex-wrap gap-2">
          {presets.map((p) => (
            <button
              key={p.id}
              onClick={() => set({ folderTemplate: p.folder, fileTemplate: p.file })}
              className={cx(
                "rounded-lg border px-3 py-1.5 text-xs transition",
                activePreset?.id === p.id
                  ? "border-indigo-500 bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300"
                  : "border-slate-200 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <TemplateInput label="文件夹" value={config.folderTemplate} onChange={(v) => set({ folderTemplate: v })} />
          <TemplateInput label="文件名" value={config.fileTemplate} onChange={(v) => set({ fileTemplate: v })} />
        </div>
        <div className="mt-3 rounded-xl bg-slate-50 px-4 py-3 dark:bg-slate-800/50">
          <div className="text-xs text-slate-400">效果预览</div>
          {nameError ? (
            <div className="mt-1 text-sm text-red-500">{nameError}</div>
          ) : (
            <div className="mt-1 flex items-center gap-2 font-mono text-sm">
              <Icon name="folder" className="w-4 h-4 text-slate-400" />
              <span className="text-slate-700 dark:text-slate-200">{example}</span>
            </div>
          )}
          <div className="mt-2 text-[11px] leading-relaxed text-slate-400">
            可用变量：{"{person}"} 人名 · {"{date}"} 日期 · {"{index:03d}"} 序号 · {"{orig_name}"} 原名 · {"{ext}"} 扩展名
          </div>
        </div>
      </Card>

      {/* Advanced */}
      <button
        onClick={() => setAdvanced((a) => !a)}
        className="mb-3 flex items-center gap-1.5 text-sm text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
      >
        <Icon name={advanced ? "arrowLeft" : "arrowRight"} className="w-4 h-4" />
        高级选项
      </button>
      {advanced && (
        <Card className="mb-2 space-y-4 p-5 animate-fade">
          <label className="flex items-center justify-between text-sm">
            <span>
              <span className="font-medium">移动文件（而非复制）</span>
              <span className="ml-2 text-xs text-slate-400">默认复制，原照片保留不动，更安全</span>
            </span>
            <input
              type="checkbox"
              checked={config.move}
              onChange={(e) => set({ move: e.target.checked })}
              className="h-4 w-4 rounded accent-indigo-600"
            />
          </label>
          <div className="flex items-center justify-between text-sm">
            <span>
              <span className="font-medium">最小人脸尺寸</span>
              <span className="ml-2 text-xs text-slate-400">小于此像素的背景小脸会被忽略</span>
            </span>
            <div className="flex items-center gap-2">
              <input
                type="number"
                min="0"
                value={config.minFace}
                onChange={(e) => set({ minFace: parseInt(e.target.value || "0", 10) })}
                className="w-20 rounded-lg border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-800"
              />
              <span className="text-xs text-slate-400">px</span>
            </div>
          </div>
        </Card>
      )}

      <StepNav
        onBack={() => goto(0)}
        onNext={() => goto(2)}
        nextLabel="预览分图"
        nextDisabled={!config.inputDir || !!nameError}
        right={
          !config.inputDir ? (
            <span className="text-xs text-amber-600 dark:text-amber-400">请先选择照片目录</span>
          ) : null
        }
      />
    </div>
  );
}

function SectionTitle({ children }) {
  return <h2 className="mb-2.5 px-1 text-sm font-semibold text-slate-500 dark:text-slate-400">{children}</h2>;
}

function FolderRow({ label, hint, value, placeholder, onPick, onClear }) {
  return (
    <div className="flex items-center gap-4">
      <div className="w-24 shrink-0">
        <div className="text-sm font-medium">{label}</div>
      </div>
      <div className="min-w-0 flex-1">
        <div
          className={cx(
            "truncate rounded-lg bg-slate-50 px-3 py-2 font-mono text-xs dark:bg-slate-800/60",
            value ? "text-slate-700 dark:text-slate-200" : "text-slate-400"
          )}
          title={value || placeholder}
        >
          {value || placeholder}
        </div>
        <div className="mt-1 px-1 text-[11px] text-slate-400">{hint}</div>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {onClear && (
          <Button variant="ghost" onClick={onClear} className="px-2">
            <Icon name="x" className="w-4 h-4" />
          </Button>
        )}
        <Button variant="outline" onClick={onPick}>
          <Icon name="folder" className="w-4 h-4" /> 选择
        </Button>
      </div>
    </div>
  );
}

function TemplateInput({ label, value, onChange }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs text-slate-400">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 dark:border-slate-700 dark:bg-slate-800"
      />
    </label>
  );
}
