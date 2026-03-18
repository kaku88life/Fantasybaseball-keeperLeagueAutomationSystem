"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth";
import { getYears } from "@/lib/api";
import LoadingSpinner from "@/components/LoadingSpinner";
import SeasonCountdown from "@/components/SeasonCountdown";

export default function HomePage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [years, setYears] = useState<number[]>([]);

  useEffect(() => {
    getYears().then(setYears).catch(() => {});
  }, []);

  if (loading) {
    return <LoadingSpinner />;
  }

  // --- Authenticated: redirect to league year page ---
  if (user) {
    const currentYear = new Date().getFullYear();
    const targetYear = years.includes(currentYear)
      ? currentYear
      : years.length > 0
        ? years[years.length - 1]
        : null;

    if (targetYear) {
      router.push(`/${targetYear}`);
      return null;
    }

    return (
      <div className="py-10 text-center">
        <h1 className="mb-4 text-2xl font-bold">Welcome{user.yahoo_nickname ? `, ${user.yahoo_nickname}` : ""}!</h1>
        {user.manager_name && (
          <p className="text-gray-600">
            Team: {user.manager_name}
            {user.team_name && ` (${user.team_name})`}
          </p>
        )}
        <p className="mt-6 text-gray-500">
          No league data imported yet.
          {user.is_commissioner && " Go to Commissioner panel to import Excel data."}
        </p>
      </div>
    );
  }

  // --- Unauthenticated: Promotional landing page ---
  const apiBase = process.env.NEXT_PUBLIC_API_URL || "https://localhost:8002";

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:py-12">
      {/* Hero Section */}
      <section className="mb-12 text-center sm:mb-16">
        <div className="mb-2 inline-block rounded-full bg-indigo-100 px-4 py-1 text-xs font-semibold tracking-wide text-indigo-700 uppercase">
          Fantasy Baseball
        </div>
        <h1 className="mb-3 text-3xl font-extrabold tracking-tight text-gray-900 sm:text-5xl">
          5-Man <span className="text-indigo-600">Keepers</span>
        </h1>
        <p className="mx-auto mb-6 max-w-xl text-base text-gray-500 sm:text-lg">
          16 支隊伍的 Keepers 合約制 Fantasy Baseball 聯盟<br />
          結合薪資帽、競標選秀、FAAB 與獨特的合約系統<br />
          打造最接近真實 GM 體驗的 Fantasy Baseball 聯盟。
        </p>
        <a
          href={`${apiBase}/api/auth/yahoo/login`}
          className="inline-block rounded-lg bg-indigo-600 px-8 py-3 text-sm font-semibold text-white shadow-md transition-all hover:bg-indigo-500 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
        >
          Login with Yahoo
        </a>

        {/* Season Countdown */}
        <SeasonCountdown />
      </section>

      {/* League Highlights - 3 column grid */}
      <section className="mb-12 sm:mb-16">
        <div className="grid gap-4 sm:grid-cols-3">
          {/* Card 1 */}
          <div className="rounded-xl border border-gray-200 bg-white p-6 text-center shadow-sm">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50">
              <svg className="h-6 w-6 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M18 18.72a9.094 9.094 0 003.741-.479 3 3 0 00-4.682-2.72m.94 3.198l.001.031c0 .225-.012.447-.037.666A11.944 11.944 0 0112 21c-2.17 0-4.207-.576-5.963-1.584A6.062 6.062 0 016 18.719m12 0a5.971 5.971 0 00-.941-3.197m0 0A5.995 5.995 0 0012 12.75a5.995 5.995 0 00-5.058 2.772m0 0a3 3 0 00-4.681 2.72 8.986 8.986 0 003.74.477m.94-3.197a5.971 5.971 0 00-.94 3.197M15 6.75a3 3 0 11-6 0 3 3 0 016 0zm6 3a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0zm-13.5 0a2.25 2.25 0 11-4.5 0 2.25 2.25 0 014.5 0z" />
              </svg>
            </div>
            <p className="text-3xl font-bold text-gray-900">16</p>
            <p className="text-sm font-medium text-gray-500">支隊伍</p>
          </div>

          {/* Card 2 */}
          <div className="rounded-xl border border-gray-200 bg-white p-6 text-center shadow-sm">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50">
              <svg className="h-6 w-6 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
              </svg>
            </div>
            <p className="text-3xl font-bold text-gray-900">H2H 7x7</p>
            <p className="text-sm font-medium text-gray-500">對戰賽制</p>
          </div>

          {/* Card 3 */}
          <div className="rounded-xl border border-gray-200 bg-white p-6 text-center shadow-sm">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50">
              <svg className="h-6 w-6 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
              </svg>
            </div>
            <p className="text-3xl font-bold text-gray-900">Keepers</p>
            <p className="text-sm font-medium text-gray-500">合約制</p>
          </div>
        </div>
      </section>

      {/* Contract System Overview */}
      <section className="mb-12 sm:mb-16">
        <h2 className="mb-6 text-center text-xl font-bold text-gray-900 sm:text-2xl">
          合約系統 Contract System
        </h2>
        <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm sm:p-8">
          {/* Contract Flow */}
          <div className="mb-6 flex flex-wrap items-center justify-center gap-2 sm:gap-3">
            {[
              { code: "A", label: "第一年約", color: "bg-green-100 text-green-800 border-green-200" },
              { code: "B", label: "第二年約", color: "bg-blue-100 text-blue-800 border-blue-200" },
              { code: "N(x)", label: "延長約", color: "bg-purple-100 text-purple-800 border-purple-200" },
              { code: "O", label: "到期約", color: "bg-gray-100 text-gray-800 border-gray-200" },
            ].map((item, i) => (
              <div key={item.code} className="flex items-center gap-2 sm:gap-3">
                <div className={`flex flex-col items-center rounded-lg border px-3 py-2 sm:px-4 sm:py-3 ${item.color}`}>
                  <span className="text-lg font-bold sm:text-xl">{item.code}</span>
                  <span className="text-[10px] sm:text-xs">{item.label}</span>
                </div>
                {i < 3 && (
                  <svg className="h-4 w-4 flex-shrink-0 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                )}
              </div>
            ))}
          </div>

          {/* Explanation items */}
          <div className="grid gap-4 text-sm text-gray-600 sm:grid-cols-2">
            <div className="flex gap-3">
              <span className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-600">1</span>
              <p>透過<strong>選秀</strong>或 <strong>FAAB</strong> 取得球員後進入 A 約</p>
            </div>
            <div className="flex gap-3">
              <span className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-600">2</span>
              <p>每年可選擇<strong>留用 (Keep)</strong> 進入下一階段合約</p>
            </div>
            <div className="flex gap-3">
              <span className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-600">3</span>
              <p>B 約結束時可選擇<strong>延長 N 年</strong>，薪資每年 +$5</p>
            </div>
            <div className="flex gap-3">
              <span className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-600">4</span>
              <p>O 約到期後成為<strong>自由球員 (FA)</strong>，重新進入選秀池</p>
            </div>
          </div>

          {/* Special contracts */}
          <div className="mt-6 rounded-lg bg-gray-50 p-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">特殊合約</p>
            <div className="flex flex-wrap gap-4 text-sm text-gray-600">
              <div className="flex items-center gap-2">
                <span className="rounded border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-bold text-amber-700">R</span>
                <span>農場新秀約 (不佔正規名額，每隊最多 2 名)</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Stats & Format */}
      <section className="mb-12 sm:mb-16">
        <h2 className="mb-6 text-center text-xl font-bold text-gray-900 sm:text-2xl">
          聯盟規格 League Format
        </h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {/* Hitting */}
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <h3 className="mb-3 text-sm font-semibold text-gray-700">打擊數據 (7 項)</h3>
            <div className="flex flex-wrap gap-2">
              {["R", "H", "HR", "RBI", "SB", "AVG", "OPS"].map((cat) => (
                <span key={cat} className="rounded-md bg-blue-50 px-2.5 py-1 text-xs font-medium text-blue-700">
                  {cat}
                </span>
              ))}
            </div>
          </div>
          {/* Pitching */}
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <h3 className="mb-3 text-sm font-semibold text-gray-700">投球數據 (7 項)</h3>
            <div className="flex flex-wrap gap-2">
              {["W", "SV", "HLD", "K", "ERA", "WHIP", "QS"].map((cat) => (
                <span key={cat} className="rounded-md bg-green-50 px-2.5 py-1 text-xs font-medium text-green-700">
                  {cat}
                </span>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Rules Preview + CTA */}
      <section className="mb-12 sm:mb-16">
        <div className="rounded-xl border border-gray-200 bg-gradient-to-br from-indigo-50 to-white p-6 text-center shadow-sm sm:p-8">
          <h2 className="mb-3 text-xl font-bold text-gray-900 sm:text-2xl">
            完整規則
          </h2>
          <p className="mx-auto mb-5 max-w-md text-sm text-gray-500">
            薪資帽管理、FAAB 競標、買斷條款、交易規則...
            完整的聯盟規則說明都在這裡。
          </p>
          <Link
            href="/rules"
            className="inline-block rounded-lg border border-indigo-200 bg-white px-6 py-2.5 text-sm font-medium text-indigo-600 shadow-sm transition-colors hover:bg-indigo-50"
          >
            查看規則 View Rules
          </Link>
        </div>
      </section>

      {/* Bottom CTA */}
      <section className="text-center">
        <div className="rounded-xl border border-gray-200 bg-gray-900 p-8 shadow-sm sm:p-10">
          <h2 className="mb-3 text-xl font-bold text-white sm:text-2xl">
            聯盟成員？
          </h2>
          <p className="mx-auto mb-6 max-w-md text-sm text-gray-400">
            登入 Yahoo 帳號即可查看完整聯盟資訊，包含球員合約、薪資、留用選擇等內部資料。
          </p>
          <a
            href={`${apiBase}/api/auth/yahoo/login`}
            className="inline-block rounded-lg bg-indigo-600 px-8 py-3 text-sm font-semibold text-white shadow-md transition-all hover:bg-indigo-500 hover:shadow-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-gray-900"
          >
            Login with Yahoo
          </a>
        </div>
      </section>
    </div>
  );
}
