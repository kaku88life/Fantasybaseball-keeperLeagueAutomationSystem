"use client";

import { useEffect, useState } from "react";
import { getLeagueSettings } from "@/lib/api";
import type { LeagueSettings } from "@/types";

export default function RulesPage() {
  const [settings, setSettings] = useState<LeagueSettings | null>(null);

  useEffect(() => {
    getLeagueSettings().then(setSettings).catch(() => {});
  }, []);

  if (!settings) {
    return <div className="py-10 text-center text-gray-500">Loading...</div>;
  }

  const currentYear = new Date().getFullYear();
  const currentCap =
    settings.salary_base +
    (currentYear - 2024 + 1) * settings.salary_increment;

  return (
    <div className="mx-auto max-w-3xl pb-10">
      <h1 className="mb-2 text-2xl font-bold">League Rules</h1>
      <p className="mb-6 text-sm text-gray-500">
        5-Man MLB Keeper League 聯盟規則總覽
      </p>

      <div className="space-y-6">
        {/* Basic Info */}
        <section className="rounded-lg border bg-white p-5">
          <h2 className="mb-1 text-lg font-semibold">基本資訊</h2>
          <p className="mb-3 text-xs text-gray-400">League Overview</p>
          <dl className="grid grid-cols-2 gap-y-2 text-sm">
            <dt className="text-gray-500">聯盟名稱</dt>
            <dd className="font-medium">{settings.league_name}</dd>
            <dt className="text-gray-500">隊伍數</dt>
            <dd>{settings.total_teams} 隊</dd>
            <dt className="text-gray-500">計分方式</dt>
            <dd>{settings.scoring_format}</dd>
            <dt className="text-gray-500">打擊類別</dt>
            <dd>{settings.hitting_cats.join(", ")}</dd>
            <dt className="text-gray-500">投球類別</dt>
            <dd>{settings.pitching_cats.join(", ")}</dd>
          </dl>
        </section>

        {/* Salary Cap */}
        <section className="rounded-lg border bg-white p-5">
          <h2 className="mb-1 text-lg font-semibold">薪資上限</h2>
          <p className="mb-3 text-xs text-gray-400">Salary Cap</p>
          <dl className="grid grid-cols-2 gap-y-2 text-sm">
            <dt className="text-gray-500">基礎薪資</dt>
            <dd>${settings.salary_base}</dd>
            <dt className="text-gray-500">每年遞增</dt>
            <dd>+${settings.salary_increment} / 年 (自 2024 年起)</dd>
            <dt className="text-gray-500">{currentYear} 年薪資上限</dt>
            <dd className="font-semibold text-blue-600">${currentCap}</dd>
            <dt className="text-gray-500">FAAB 年度預算</dt>
            <dd>${settings.faab_base}</dd>
            <dt className="text-gray-500">FAAB 最低出價</dt>
            <dd>${settings.min_bid}</dd>
          </dl>
          <p className="mt-3 text-xs text-gray-400">
            計算公式: ${settings.salary_base} + (年份 - 2024 + 1) x $
            {settings.salary_increment}
          </p>
        </section>

        {/* Keeper Rules */}
        <section className="rounded-lg border bg-white p-5">
          <h2 className="mb-1 text-lg font-semibold">留用規則</h2>
          <p className="mb-3 text-xs text-gray-400">Keeper Rules</p>
          <dl className="grid grid-cols-2 gap-y-2 text-sm">
            <dt className="text-gray-500">活躍留用人數</dt>
            <dd>
              {settings.keeper_active_min} ~ {settings.keeper_active_max} 人
              (A/B/N/O)
            </dd>
            <dt className="text-gray-500">板凳留用人數</dt>
            <dd>最多 {settings.keeper_bench_max} 人 (R)</dd>
            <dt className="text-gray-500">延長合約成本</dt>
            <dd>每延長 1 年 +${settings.extension_cost_per_year}</dd>
          </dl>
          <div className="mt-3 rounded bg-amber-50 p-3 text-xs text-amber-800">
            留用者 = 你要帶到下一季的球員。每隊最少留{" "}
            {settings.keeper_active_min} 位活躍球員，最多{" "}
            {settings.keeper_active_max} 位，外加最多{" "}
            {settings.keeper_bench_max} 位板凳新秀 (R)。
          </div>
        </section>

        {/* Contract Flow */}
        <section className="rounded-lg border bg-white p-5">
          <h2 className="mb-1 text-lg font-semibold">合約流轉</h2>
          <p className="mb-3 text-xs text-gray-400">Contract System (1+1+X)</p>
          <div className="space-y-4 text-sm">
            {/* A -> B */}
            <div className="flex items-start gap-3">
              <div className="flex shrink-0 items-center gap-1.5">
                <span className="inline-block w-8 rounded bg-blue-100 px-1.5 py-1 text-center font-bold text-blue-800">
                  A
                </span>
                <span className="text-gray-400">&rarr;</span>
                <span className="inline-block w-8 rounded bg-green-100 px-1.5 py-1 text-center font-bold text-green-800">
                  B
                </span>
              </div>
              <div>
                <p className="font-medium">第 1 年 &rarr; 第 2 年</p>
                <p className="text-xs text-gray-500">
                  選秀或 FAAB 取得的球員為 A 約，留用後自動升為 B 約，薪資不變。
                </p>
              </div>
            </div>

            {/* B -> O */}
            <div className="flex items-start gap-3">
              <div className="flex shrink-0 items-center gap-1.5">
                <span className="inline-block w-8 rounded bg-green-100 px-1.5 py-1 text-center font-bold text-green-800">
                  B
                </span>
                <span className="text-gray-400">&rarr;</span>
                <span className="inline-block w-8 rounded bg-red-100 px-1.5 py-1 text-center font-bold text-red-800">
                  O
                </span>
              </div>
              <div>
                <p className="font-medium">第 2 年 &rarr; 選擇權年</p>
                <p className="text-xs text-gray-500">
                  不延長的話，B 約留用後變 O 約（最後一年），O 約結束後成為自由球員 (FA)。
                </p>
              </div>
            </div>

            {/* B -> N(x)+O */}
            <div className="flex items-start gap-3">
              <div className="flex shrink-0 items-center gap-1.5">
                <span className="inline-block w-8 rounded bg-green-100 px-1.5 py-1 text-center font-bold text-green-800">
                  B
                </span>
                <span className="text-gray-400">&rarr;</span>
                <span className="inline-block rounded bg-orange-100 px-1.5 py-1 text-center font-bold text-orange-800">
                  N+O
                </span>
              </div>
              <div>
                <p className="font-medium">延長合約</p>
                <p className="text-xs text-gray-500">
                  B 約時可選擇延長 1~3 年。延長 x 年薪資增加 x x $
                  {settings.extension_cost_per_year}。
                  <br />
                  例: $10/B 延長 3 年 &rarr; $10 + 3x$5 = $25/N3，之後
                  N3&rarr;N2&rarr;N1&rarr;O&rarr;FA。
                </p>
              </div>
            </div>

            {/* R */}
            <div className="flex items-start gap-3">
              <div className="flex shrink-0 items-center gap-1.5">
                <span className="inline-block w-8 rounded bg-gray-200 px-1.5 py-1 text-center font-bold text-gray-700">
                  R
                </span>
                <span className="text-gray-400">&rarr;</span>
                <span className="inline-block w-8 rounded bg-blue-100 px-1.5 py-1 text-center font-bold text-blue-800">
                  A
                </span>
              </div>
              <div>
                <p className="font-medium">新秀 (板凳)</p>
                <p className="text-xs text-gray-500">
                  R 約球員放在板凳名單，不計入薪資上限。啟用後轉為 A
                  約進入正規合約流程。
                </p>
              </div>
            </div>
          </div>

          {/* Visual flow chart */}
          <div className="mt-4 rounded bg-slate-50 p-3 text-center text-xs text-gray-600">
            <p className="font-medium">完整合約路徑</p>
            <p className="mt-1">
              <span className="font-bold text-blue-700">A</span>
              {" "}&rarr;{" "}
              <span className="font-bold text-green-700">B</span>
              {" "}&rarr;{" "}
              <span className="font-bold text-red-700">O</span>
              {" "}&rarr;{" "}
              <span className="text-gray-500">FA (自由球員)</span>
            </p>
            <p className="mt-0.5">
              <span className="font-bold text-blue-700">A</span>
              {" "}&rarr;{" "}
              <span className="font-bold text-green-700">B</span>
              {" "}&rarr;{" "}
              <span className="font-bold text-orange-600">N(x)</span>
              {" "}&rarr; ... &rarr;{" "}
              <span className="font-bold text-orange-600">N(1)</span>
              {" "}&rarr;{" "}
              <span className="font-bold text-red-700">O</span>
              {" "}&rarr;{" "}
              <span className="text-gray-500">FA</span>
            </p>
          </div>
        </section>

        {/* Buyout */}
        <section className="rounded-lg border bg-white p-5">
          <h2 className="mb-1 text-lg font-semibold">買斷規則</h2>
          <p className="mb-3 text-xs text-gray-400">Buyout Rules</p>
          <div className="space-y-2 text-sm">
            <div>
              <p className="font-medium">一般買斷</p>
              <p className="text-xs text-gray-500">
                買斷金 = 薪資 x 剩餘合約年數。例: $20/N1 (剩 2 年) &rarr; 買斷金 $40。
              </p>
            </div>
            <div>
              <p className="font-medium">FAAB 買斷</p>
              <p className="text-xs text-gray-500">
                可選擇用 FAAB 分攤。每年 FAAB 分攤 = ceil(薪資/2)，薪資分攤 = floor(薪資/2)。
                <br />
                例: $11 球員 &rarr; 每年 FAAB $6 + 薪資 $5。
              </p>
            </div>
          </div>
        </section>

        {/* Ranking Bonus */}
        <section className="rounded-lg border bg-white p-5">
          <h2 className="mb-1 text-lg font-semibold">排名獎勵金</h2>
          <p className="mb-3 text-xs text-gray-400">Ranking Bonus</p>
          <div className="grid grid-cols-3 gap-2 text-sm">
            {Object.entries(settings.ranking_bonus)
              .sort(([a], [b]) => Number(a) - Number(b))
              .map(([rank, bonus]) => (
                <div
                  key={rank}
                  className="rounded bg-gray-50 px-3 py-2 text-center"
                >
                  <span className="text-gray-500">第 {rank} 名</span>
                  <br />
                  <span className="text-lg font-bold text-green-600">
                    +${bonus}
                  </span>
                </div>
              ))}
          </div>
          <p className="mt-3 text-xs text-gray-400">
            獎勵金將加到下一季的薪資上限中，增加你的可用薪資空間。
          </p>
        </section>

        {/* Trade Rules */}
        <section className="rounded-lg border bg-white p-5">
          <h2 className="mb-1 text-lg font-semibold">交易合約規則</h2>
          <p className="mb-3 text-xs text-gray-400">Trade Contract Resolution</p>
          <div className="text-sm text-gray-600">
            <p>
              被交易的球員，合約以「較長者」為準：
            </p>
            <ul className="mt-2 list-inside list-disc space-y-1 text-xs text-gray-500">
              <li>薪資: 取 max(原薪資, 交易價)</li>
              <li>合約年限: 取較長者</li>
              <li>優先順序: N(最長) &gt; O &gt; B &gt; A &gt; R(最短)</li>
            </ul>
          </div>
        </section>
      </div>
    </div>
  );
}
