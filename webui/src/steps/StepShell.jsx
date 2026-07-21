import React from "react";
import { Button, Icon } from "../ui.jsx";

export function StepHeader({ title, desc }) {
  return (
    <header className="mb-6 animate-fade">
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      {desc && <p className="mt-1.5 text-sm text-slate-500 dark:text-slate-400">{desc}</p>}
    </header>
  );
}

export function StepNav({ onBack, onNext, nextLabel = "下一步", nextDisabled, backLabel = "上一步", right }) {
  return (
    <div className="mt-8 flex items-center justify-between border-t border-slate-200 pt-5 dark:border-slate-800">
      <div>
        {onBack && (
          <Button variant="ghost" onClick={onBack}>
            <Icon name="arrowLeft" className="w-4 h-4" /> {backLabel}
          </Button>
        )}
      </div>
      <div className="flex items-center gap-3">
        {right}
        {onNext && (
          <Button onClick={onNext} disabled={nextDisabled}>
            {nextLabel} <Icon name="arrowRight" className="w-4 h-4" />
          </Button>
        )}
      </div>
    </div>
  );
}
