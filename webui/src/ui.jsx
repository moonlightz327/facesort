// Small shared UI primitives. Slate + indigo, light/dark aware.
import React from "react";

export function cx(...parts) {
  return parts.filter(Boolean).join(" ");
}

export function Button({ variant = "primary", className, children, ...props }) {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium transition select-none disabled:opacity-40 disabled:cursor-not-allowed";
  const variants = {
    primary:
      "bg-indigo-600 text-white hover:bg-indigo-500 active:bg-indigo-700 shadow-sm shadow-indigo-600/20",
    ghost:
      "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
    outline:
      "border border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-800",
    danger:
      "text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950/40",
    subtle:
      "bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700",
  };
  return (
    <button className={cx(base, variants[variant], className)} {...props}>
      {children}
    </button>
  );
}

export function Card({ className, children }) {
  return (
    <div
      className={cx(
        "rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900",
        className
      )}
    >
      {children}
    </div>
  );
}

export function Spinner({ className }) {
  return (
    <svg
      className={cx("animate-spin", className)}
      viewBox="0 0 24 24"
      fill="none"
      width="18"
      height="18"
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function ProgressBar({ value = 0, className }) {
  return (
    <div className={cx("h-2 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800", className)}>
      <div
        className="h-full rounded-full bg-indigo-600 transition-all duration-300"
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}

export function Badge({ children, tone = "slate" }) {
  const tones = {
    slate: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
    indigo: "bg-indigo-100 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300",
    amber: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
    green: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  };
  return (
    <span className={cx("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium", tones[tone])}>
      {children}
    </span>
  );
}

// Minimal inline icon set.
export function Icon({ name, className = "w-5 h-5", ...props }) {
  const paths = {
    users: "M17 20h5v-1a4 4 0 0 0-3-3.87M9 20H4v-1a4 4 0 0 1 3-3.87m6-1.13a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z",
    sliders: "M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6",
    eye: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z|M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z",
    check: "M20 6 9 17l-5-5",
    plus: "M12 5v14M5 12h14",
    folder: "M3 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z",
    x: "M18 6 6 18M6 6l12 12",
    trash: "M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m2 0v14a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V6",
    arrowRight: "M5 12h14M13 6l6 6-6 6",
    arrowLeft: "M19 12H5M11 18l-6-6 6-6",
    warning: "M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z",
    image: "M3 5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5Z|M8.5 11a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3ZM21 15l-5-5L5 21",
    finder: "M4 4h16v16H4zM4 10h16M10 4v16",
  };
  const d = paths[name] || "";
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} {...props}>
      {d.split("|").map((seg, i) => (
        <path key={i} d={seg} stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      ))}
    </svg>
  );
}

export function Thumb({ src, alt, className, onClick }) {
  return (
    <div
      onClick={onClick}
      className={cx(
        "relative overflow-hidden rounded-lg bg-slate-100 dark:bg-slate-800",
        onClick && "cursor-pointer",
        className
      )}
    >
      {src ? (
        <img src={src} alt={alt} className="h-full w-full object-cover" loading="lazy" />
      ) : (
        <div className="flex h-full w-full items-center justify-center text-slate-400">
          <Icon name="image" />
        </div>
      )}
    </div>
  );
}
