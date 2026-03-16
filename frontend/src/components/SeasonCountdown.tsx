"use client";

import { useEffect, useState } from "react";

// --- Key dates (local time) ---
// Draft Day: 2026/03/22 (Sun) 9:00 PM
const DRAFT_DAY = new Date(2026, 2, 22, 21, 0, 0);
// 2026 MLB Opening Day: 2026/03/26 (Thu)
const OPENING_DAY = new Date(2026, 2, 26);
// Fantasy H2H Week 1 starts the Monday of Opening Day week
const WEEK1_START = new Date(2026, 2, 23);
const TOTAL_WEEKS = 25;
// Playoffs start at Week 23 (22 weeks after Week 1)
const PLAYOFFS_START = new Date(
  WEEK1_START.getTime() + 22 * 7 * 24 * 60 * 60 * 1000,
);

/** Reusable countdown digit grid */
function CountdownDigits({ ms }: { ms: number }) {
  const days = Math.floor(ms / (1000 * 60 * 60 * 24));
  const hours = Math.floor((ms % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
  const minutes = Math.floor((ms % (1000 * 60 * 60)) / (1000 * 60));
  const seconds = Math.floor((ms % (1000 * 60)) / 1000);

  return (
    <div className="flex justify-center gap-3">
      {[
        { value: days, label: "Days" },
        { value: hours, label: "Hrs" },
        { value: minutes, label: "Min" },
        { value: seconds, label: "Sec" },
      ].map(({ value, label }) => (
        <div key={label} className="flex flex-col items-center">
          <span className="w-12 rounded-md bg-indigo-50 py-1.5 text-center text-2xl font-bold tabular-nums text-indigo-600">
            {String(value).padStart(2, "0")}
          </span>
          <span className="mt-1 text-[10px] text-gray-400">{label}</span>
        </div>
      ))}
    </div>
  );
}

/** Draft countdown / Season countdown / current-week indicator */
export default function SeasonCountdown() {
  const [now, setNow] = useState<Date | null>(null);

  useEffect(() => {
    setNow(new Date());
    const timer = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // SSR guard: render nothing on the server to avoid hydration mismatch
  if (!now) return null;

  const msToDraft = DRAFT_DAY.getTime() - now.getTime();
  const msToOpening = OPENING_DAY.getTime() - now.getTime();

  // --- Phase 1: Before Draft Day ---
  if (msToDraft > 0) {
    return (
      <div className="mt-8 space-y-4">
        {/* Draft countdown (primary) */}
        <div className="rounded-lg border border-indigo-200 bg-gradient-to-b from-indigo-50/50 to-white p-5">
          <p className="mb-3 text-xs font-medium tracking-wide text-indigo-400 uppercase">
            Draft Day
          </p>
          <CountdownDigits ms={msToDraft} />
          <p className="mt-3 text-xs text-gray-400">
            2026/03/22 (Sun) 9:00 PM
          </p>
        </div>
        {/* Opening Day (secondary, compact) */}
        <div className="rounded-lg border border-gray-200 bg-gray-50/50 px-4 py-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-400">Opening Day</span>
            <span className="text-xs tabular-nums text-gray-500">
              {Math.ceil(msToOpening / (1000 * 60 * 60 * 24))} days
            </span>
            <span className="text-xs text-gray-400">03/26 (Thu)</span>
          </div>
        </div>
      </div>
    );
  }

  // --- Phase 2: After Draft, before Opening Day ---
  if (msToOpening > 0) {
    return (
      <div className="mt-8 rounded-lg border border-gray-200 bg-gradient-to-b from-gray-50 to-white p-5">
        <p className="mb-3 text-xs font-medium tracking-wide text-gray-400 uppercase">
          2026 MLB Opening Day
        </p>
        <CountdownDigits ms={msToOpening} />
        <p className="mt-3 text-xs text-gray-400">
          2026/03/26 (Thu) - Play Ball!
        </p>
      </div>
    );
  }

  // --- Phase 3: During season ---
  const msFromWeek1 = now.getTime() - WEEK1_START.getTime();
  const currentWeek =
    Math.floor(msFromWeek1 / (1000 * 60 * 60 * 24 * 7)) + 1;

  // Season ended
  if (currentWeek > TOTAL_WEEKS) {
    return (
      <div className="mt-8 rounded-lg border border-gray-200 bg-gray-50 p-4 text-center">
        <p className="text-sm text-gray-500">2026 賽季已結束</p>
      </div>
    );
  }

  // Show current week + progress bar
  const isPlayoffs = currentWeek >= 23;
  const progress = Math.min((currentWeek / TOTAL_WEEKS) * 100, 100);
  const msToPlayoffs = PLAYOFFS_START.getTime() - now.getTime();
  const daysToPlayoffs = Math.ceil(msToPlayoffs / (1000 * 60 * 60 * 24));

  return (
    <div className="mt-8 space-y-4">
      {/* Current week (primary) */}
      <div
        className={`rounded-lg border bg-gradient-to-b p-5 ${
          isPlayoffs
            ? "border-orange-200 from-orange-50/50 to-white"
            : "border-gray-200 from-gray-50 to-white"
        }`}
      >
        <p className="mb-2 text-xs font-medium tracking-wide uppercase text-gray-400">
          {isPlayoffs ? "Playoffs" : "2026 Season"}
        </p>
        <div className="flex items-baseline justify-center gap-1.5">
          <span className="text-xs text-gray-400">Week</span>
          <span
            className={`text-3xl font-bold ${isPlayoffs ? "text-orange-600" : "text-indigo-600"}`}
          >
            {currentWeek}
          </span>
          <span className="text-sm text-gray-400">/ {TOTAL_WEEKS}</span>
        </div>
        {/* Progress bar */}
        <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-gray-200">
          <div
            className={`h-1.5 rounded-full transition-all duration-500 ${isPlayoffs ? "bg-orange-500" : "bg-indigo-500"}`}
            style={{ width: `${progress}%` }}
          />
        </div>
        {isPlayoffs && (
          <p className="mt-2 text-xs font-medium text-orange-600">
            季後賽進行中
          </p>
        )}
      </div>

      {/* Playoffs countdown (secondary, show only within 30 days before playoffs) */}
      {!isPlayoffs && daysToPlayoffs > 0 && daysToPlayoffs <= 30 && (
        <div className="rounded-lg border border-gray-200 bg-gray-50/50 px-4 py-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-400">Playoffs</span>
            <span className="text-xs tabular-nums text-gray-500">
              {daysToPlayoffs} days
            </span>
            <span className="text-xs text-gray-400">Week 23-25</span>
          </div>
        </div>
      )}
    </div>
  );
}
