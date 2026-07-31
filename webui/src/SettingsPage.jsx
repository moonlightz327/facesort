import React, { useState } from "react";
import { api } from "./api.js";
import { Button, Card, Icon, Badge } from "./ui.jsx";
import ModelSetup from "./ModelSetup.jsx";

/**
 * Always-reachable settings, separate from the 4-step wizard.
 *
 * Exists mainly so the recognition model can be installed *before* the first
 * sort instead of being discovered mid-run, and so preferences persist across
 * restarts instead of resetting every launch.
 */
export default function SettingsPage({ boot, model, setModel, settings, setSettings }) {
  const [saved, setSaved] = useState(false);

  const update = async (patch) => {
    const next = { ...settings, ...patch };
    setSettings(next);
    const r = await api.saveSettings(patch);
    if (r.ok) {
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    }
  };

  const reset = async () => {
    if (!confirm("恢复所有设置为默认值？（不会删除已安装的模型和人物库）")) return;
    const r = await api.resetSettings();
    if (r.ok) setSettings(r.settings);
  };

  return (
    <div className="animate-fade">
      <div className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold">设置</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            这里的改动会自动保存，下次打开仍然生效。
          </p>
        </div>
        {saved && (
          <span className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400">
            <Icon name="check" className="w-4 h-4" /> 已保存
          </span>
        )}
      </div>

      <div className="mb-6">
        <ModelSetup model={model} onReady={setModel} manage />
      </div>

      {boot?.accel?.available && (
        <Card className="mb-6 p-5">
          <div className="mb-3 flex items-center gap-2">
            <h2 className="text-sm font-semibold">硬件加速</h2>
            <Badge tone="green">Apple 芯片</Badge>
          </div>
          <Row
            label="用神经网络引擎 / GPU 识别"
            hint="识别速度约提升 8 倍，结果与 CPU 一致。首次启用需要一次约 10 秒的模型编译，之后启动照常"
          >
            <input
              type="checkbox"
              checked={settings.useGpu !== false}
              onChange={(e) => update({ useGpu: e.target.checked })}
              className="h-4 w-4 shrink-0 rounded accent-indigo-600"
            />
          </Row>
          <p className="mt-3 text-xs text-slate-400">
            {boot.accel.active
              ? `当前运行在 ${boot.accel.active}。`
              : "首次识别时生效。"}
            如果遇到异常，关掉这项会回到 CPU 模式（较慢但最稳妥）。
          </p>
        </Card>
      )}

      <Card className="mb-6 p-5">
        <h2 className="mb-4 text-sm font-semibold">整理默认值</h2>
        <div className="space-y-4">
          <Row
            label="并行处理数"
            hint="同时分析几张照片。自动即可；调太高反而会变慢"
          >
            <select
              value={settings.workers ?? 0}
              onChange={(e) => update({ workers: parseInt(e.target.value, 10) })}
              className={SELECT}
            >
              <option value={0}>自动{boot?.autoWorkers ? `（${boot.autoWorkers}）` : ""}</option>
              <option value={1}>1（最省资源）</option>
              <option value={2}>2</option>
              <option value={4}>4</option>
              <option value={6}>6</option>
            </select>
          </Row>

          <Row
            label="按原始分辨率解码"
            hint="默认解码到约一半尺寸，大图快约 1.6 倍且识别结果几乎无差别；勾选后更慢"
          >
            <input
              type="checkbox"
              checked={(settings.decodeMaxSide ?? 1400) === 0}
              onChange={(e) => update({ decodeMaxSide: e.target.checked ? 0 : 1400 })}
              className="h-4 w-4 shrink-0 rounded accent-indigo-600"
            />
          </Row>

          <Row label="最小人脸尺寸" hint="小于此像素的背景小脸会被忽略">
            <div className="flex items-center gap-2">
              <input
                type="number"
                min="0"
                value={settings.minFace ?? 40}
                onChange={(e) => update({ minFace: parseInt(e.target.value || "0", 10) })}
                className="w-20 rounded-lg border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-800"
              />
              <span className="text-xs text-slate-400">px</span>
            </div>
          </Row>

          <Row label="移动文件（而非复制）" hint="默认复制，原照片保留不动，更安全">
            <input
              type="checkbox"
              checked={!!settings.move}
              onChange={(e) => update({ move: e.target.checked })}
              className="h-4 w-4 shrink-0 rounded accent-indigo-600"
            />
          </Row>
        </div>
      </Card>

      <Card className="p-5">
        <h2 className="mb-3 text-sm font-semibold">存储位置</h2>
        <div className="space-y-2 text-xs text-slate-500 dark:text-slate-400">
          <PathRow label="人物样本库" value={boot?.libraryPath} />
          <PathRow label="识别模型" value={model?.modelDir} />
        </div>
        <div className="mt-4 flex gap-2">
          <Button variant="outline" onClick={() => api.openPath(boot?.libraryPath)}>
            <Icon name="finder" className="w-4 h-4" /> 打开人物库
          </Button>
          <Button variant="danger" onClick={reset}>
            恢复默认设置
          </Button>
        </div>
      </Card>
    </div>
  );
}

const SELECT =
  "rounded-lg border border-slate-300 bg-white px-2 py-1 text-sm dark:border-slate-700 dark:bg-slate-800";

function Row({ label, hint, children }) {
  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <span className="min-w-0">
        <span className="font-medium">{label}</span>
        <span className="ml-2 text-xs text-slate-400">{hint}</span>
      </span>
      {children}
    </div>
  );
}

function PathRow({ label, value }) {
  return (
    <div className="flex flex-wrap items-baseline gap-2">
      <span className="shrink-0">{label}：</span>
      <span className="break-all font-mono text-[11px] text-slate-600 dark:text-slate-300">
        {value || "—"}
      </span>
    </div>
  );
}
