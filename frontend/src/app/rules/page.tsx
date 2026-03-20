"use client";

import { useEffect, useState, useCallback } from "react";
import { getLeagueSettings } from "@/lib/api";
import LoadingSpinner from "@/components/LoadingSpinner";
import type { LeagueSettings } from "@/types";

const TABS = [
  { id: "overview", label: "聯盟總覽" },
  { id: "contract", label: "薪資與合約" },
  { id: "transaction", label: "球員異動" },
  { id: "keeper", label: "留用與買斷" },
  { id: "other", label: "其他規則" },
  { id: "diy", label: "自建系統" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function RulesPage() {
  const [settings, setSettings] = useState<LeagueSettings | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>("overview");

  useEffect(() => {
    getLeagueSettings().then(setSettings).catch(() => {});
  }, []);

  if (!settings) {
    return <LoadingSpinner />;
  }

  const currentYear = new Date().getFullYear();
  const currentCap =
    settings.salary_base +
    (currentYear - 2024 + 1) * settings.salary_increment;

  return (
    <div className="mx-auto max-w-3xl pb-10">
      <h1 className="mb-2 text-xl font-bold sm:text-2xl">League Rules</h1>
      <p className="mb-4 text-sm text-gray-500">
        Fantasy Baseball 5-Man Keepers 聯盟規則總覽（2025.02.26 版）
      </p>

      {/* Tab Navigation */}
      <div className="mb-6 flex gap-1 border-b border-gray-200 overflow-x-auto">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={`relative whitespace-nowrap px-3 py-2 text-xs font-medium transition-colors sm:px-4 sm:text-sm ${
              activeTab === tab.id
                ? "text-indigo-600"
                : "text-gray-500 hover:text-gray-700"
            }`}
          >
            {tab.label}
            {activeTab === tab.id && (
              <span className="absolute inset-x-0 bottom-0 h-0.5 bg-indigo-600" />
            )}
          </button>
        ))}
      </div>

      {/* ==================== Tab 1: 聯盟總覽 ==================== */}
      {activeTab === "overview" && (
        <div className="space-y-6">
          {/* ===== 1. Basic Info ===== */}
          <section className="rounded-lg border bg-white p-5">
            <h2 className="mb-1 text-lg font-semibold">基本資訊</h2>
            <p className="mb-3 text-xs text-gray-400">League Overview</p>
            <dl className="grid grid-cols-2 gap-y-2 text-sm">
              <dt className="text-gray-500">聯盟名稱</dt>
              <dd className="font-medium">{settings.league_name}</dd>
              <dt className="text-gray-500">隊伍數</dt>
              <dd>{settings.total_teams} 隊（最大限制 16 隊）</dd>
              <dt className="text-gray-500">球員來源</dt>
              <dd>AL + NL 混合聯盟（以 Yahoo! FB 為準）</dd>
              <dt className="text-gray-500">選秀方式</dt>
              <dd>喊價選秀 (Auction Draft)</dd>
              <dt className="text-gray-500">調度方式</dt>
              <dd>Daily Transaction</dd>
            </dl>
          </section>

          {/* ===== 2. Roster Positions ===== */}
          <section className="rounded-lg border bg-white p-5">
            <h2 className="mb-1 text-lg font-semibold">球員位置</h2>
            <p className="mb-3 text-xs text-gray-400">Roster Positions</p>
            <div className="space-y-2 text-sm">
              <div className="flex items-start gap-2">
                <span className="w-16 shrink-0 font-medium text-gray-700">打者</span>
                <div className="flex flex-wrap gap-1">
                  {(settings.roster_positions?.active || ["C","1B","2B","3B","SS","IF","LF","CF","RF","OF","UT","UT"]).map((pos, i) => (
                    <span key={`a-${i}`} className="rounded bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
                      {pos}
                    </span>
                  ))}
                </div>
              </div>
              <div className="flex items-start gap-2">
                <span className="w-16 shrink-0 font-medium text-gray-700">投手</span>
                <div className="flex flex-wrap gap-1">
                  {(settings.roster_positions?.pitchers || ["SP","SP","SP","SP","RP","RP","RP","P","P","P"]).map((pos, i) => (
                    <span key={`p-${i}`} className="rounded bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
                      {pos}
                    </span>
                  ))}
                </div>
              </div>
              <div className="flex items-start gap-2">
                <span className="w-16 shrink-0 font-medium text-gray-700">其他</span>
                <div className="flex flex-wrap gap-1">
                  <span className="rounded bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">BN x5</span>
                  <span className="rounded bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">NA x2</span>
                  <span className="rounded bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600">DL x4</span>
                </div>
              </div>
            </div>
          </section>

          {/* ===== 3. Team Setup ===== */}
          <section className="rounded-lg border bg-white p-5">
            <h2 className="mb-1 text-lg font-semibold">球隊設定</h2>
            <p className="mb-3 text-xs text-gray-400">Team Setup</p>
            <ul className="list-inside list-disc space-y-1.5 text-sm text-gray-600">
              <li>球隊數目可依擴編或裁減而變化，原則上每年擴編 0-2 隊。</li>
              <li>隊名需取完整的大聯盟名稱（如 New York Mets），球季中可更改但不得重複。</li>
              <li>
                球季中你的 Roster 必須隨時都有該隊{" "}
                <span className="font-semibold">5 名以上</span>球員。
                <span className="text-xs text-amber-600">（R 約球員不算入 5 名球員內）</span>
              </li>
              <li>開季隊名將以選秀結果為準，若兩隊同時擁有同隊五名球員，以先組成且先通知的隊伍優先。</li>
            </ul>
          </section>

          {/* ===== 4. Scoring ===== */}
          <section className="rounded-lg border bg-white p-5">
            <h2 className="mb-1 text-lg font-semibold">計分方式</h2>
            <p className="mb-3 text-xs text-gray-400">Scoring</p>
            <dl className="grid grid-cols-2 gap-y-2 text-sm">
              <dt className="text-gray-500">計分制度</dt>
              <dd>{settings.scoring_format}</dd>
              <dt className="text-gray-500">打擊類別</dt>
              <dd>{settings.hitting_cats.join(", ")}</dd>
              <dt className="text-gray-500">投球類別</dt>
              <dd>{settings.pitching_cats.join(", ")}</dd>
              <dt className="text-gray-500">最低投球局數</dt>
              <dd>30 IP</dd>
              <dt className="text-gray-500">季後賽</dt>
              <dd>Week 23, 24, 25（前 8 隊晉級）</dd>
              <dt className="text-gray-500">Tiebreak</dt>
              <dd>依 Yahoo 系統的 Tiebreak 規則決定排名</dd>
            </dl>
          </section>
        </div>
      )}

      {/* ==================== Tab 2: 薪資與合約 ==================== */}
      {activeTab === "contract" && (
        <div className="space-y-6">
          {/* ===== 5. Salary Cap ===== */}
          <section className="rounded-lg border bg-white p-5">
            <h2 className="mb-1 text-lg font-semibold">薪資設定</h2>
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

            <div className="mt-4 border-t pt-3">
              <p className="mb-2 text-sm font-medium text-gray-700">薪資交易規則</p>
              <ul className="list-inside list-disc space-y-1 text-xs text-gray-500">
                <li>起始薪資與 FAAB 可搭配球員交易以補貼薪資的方式交易。</li>
                <li>
                  <span className="font-medium text-gray-700">FAAB</span>：只能以當年度的額度進行交易，沒用完也無法留到下一年。
                </li>
                <li>
                  <span className="font-medium text-gray-700">起始薪資</span>：支付模式（時間、額度）以雙方 GM 約定同意即可，分期付款交易金最多不可超過{" "}
                  <span className="font-semibold">5 年</span>。
                </li>
              </ul>
            </div>
          </section>

          {/* ===== 6. Contract System ===== */}
          <section className="rounded-lg border bg-white p-5">
            <h2 className="mb-1 text-lg font-semibold">球員合約</h2>
            <p className="mb-3 text-xs text-gray-400">Contract System (1+1+X)</p>

            <div className="mb-4 rounded bg-slate-50 p-3 text-xs text-gray-600">
              <p className="font-medium">基本概念</p>
              <p className="mt-1">
                採用 1+1+X 設定，即為 A-B-O 或 A-B 或 A。如簽長約則為 A-B-N-O。
                交易不影響合約狀態。球員一旦釋出即回歸無合約狀態。
                球員簽入之後至多可以用此簽約價碼續約 3 年，可以在任何一年終止合約，
                在第二年時可以不轉 O 約。若選擇簽長約，薪資為原合約薪資 + N*$5。
              </p>
            </div>

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
                    R 約球員在球季開始至球季結束前被啟用 (active)，也為 A 約。
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
                  <p className="font-medium">第 2 年 &rarr; 選擇權年 (Option Year)</p>
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
                    B 約時可選擇延長 1~3 年。薪資增加 N x $
                    {settings.extension_cost_per_year}。
                    <br />
                    例: $10/B 延長 3 年 &rarr; $10 + 3x$5 = $25/N3，之後
                    N3&rarr;N2&rarr;N1&rarr;O&rarr;FA。
                    <br />
                    N 約期間薪資固定不變，合約總長度為 N+1 年（含 O 年）。
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
                  <span className="inline-block rounded bg-blue-100 px-1.5 py-1 text-center font-bold text-blue-800">
                    A
                  </span>
                  <span className="text-gray-400">/</span>
                  <span className="inline-block w-8 rounded bg-gray-200 px-1.5 py-1 text-center font-bold text-gray-700">
                    R
                  </span>
                </div>
                <div>
                  <p className="font-medium">新秀 Rookie</p>
                  <p className="text-xs text-gray-500">
                    R 約球員放在 Keep 名單，不計入 Keepers 人數上限，每隊最多 {settings.keeper_bench_max} 人。
                    新秀資格：MLB 打數少於 130 個、投球局數少於 50 局。
                  </p>
                  <ul className="mt-1.5 list-inside list-disc space-y-0.5 text-xs text-gray-500">
                    <li>
                      <span className="font-medium text-gray-700">仍符合新秀資格</span>
                      {" "}&rarr; 可繼續維持 R 約 Keep
                    </li>
                    <li>
                      <span className="font-medium text-gray-700">已超過新秀門檻（畢業）或啟用</span>
                      {" "}&rarr; 必須轉為 A 約進入正規合約流程
                    </li>
                  </ul>
                </div>
              </div>
            </div>

            {/* Contract transition rules */}
            <div className="mt-4 border-t pt-3">
              <p className="mb-2 text-sm font-medium text-gray-700">合約轉換時機</p>
              <p className="text-xs text-gray-500">合約轉換僅在三種情況下發生：</p>
              <ol className="mt-1 list-inside list-decimal space-y-1 text-xs text-gray-500">
                <li><span className="font-medium text-gray-700">R 約球員 active</span>：立即轉為 A 約，合約價值不變。</li>
                <li><span className="font-medium text-gray-700">球員死亡</span>：合約自動作廢。</li>
                <li><span className="font-medium text-gray-700">年底 Keeper 續約</span>：請參見「留用與買斷」分頁。</li>
              </ol>
            </div>

            {/* Visual flow chart */}
            <div className="mt-4 rounded bg-slate-50 p-3 text-center text-xs text-gray-600">
              <p className="font-medium">完整合約路徑 Contract Flow</p>
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
              <p className="mt-0.5">
                <span className="font-bold text-gray-600">R</span>
                {" "}&rarr;{" "}
                <span className="font-bold text-gray-600">R</span>
                {" "}(仍符合新秀) 或{" "}
                <span className="font-bold text-gray-600">R</span>
                {" "}&rarr;{" "}
                <span className="font-bold text-blue-700">A</span>
                {" "}(畢業/啟用)
              </p>
            </div>
          </section>
        </div>
      )}

      {/* ==================== Tab 3: 球員異動 ==================== */}
      {activeTab === "transaction" && (
        <div className="space-y-6">
          {/* ===== 7. Free Agent Acquisition ===== */}
          <section className="rounded-lg border bg-white p-5">
            <h2 className="mb-1 text-lg font-semibold">自由球員獲得</h2>
            <p className="mb-3 text-xs text-gray-400">Free Agent Acquisition (FAAB)</p>
            <ul className="list-inside list-disc space-y-1.5 text-sm text-gray-600">
              <li>球季中採用 FAAB 方式，以競價方式進行自由球員獲得。</li>
              <li>
                最低 FAAB 標金為{" "}
                <span className="font-semibold">${settings.min_bid}</span>，若填 $0 得標者作廢，由聯盟長手動遞補下一順位，無下一順位則球員重新回到 waiver。
              </li>
              <li>
                同一球隊發生{" "}
                <span className="font-semibold text-amber-700">第 4 次</span>{" "}
                開始扣 FAAB $5，第 5 次扣 $10，以此類推。
              </li>
              <li>如果遇到相同價格競標 waiver 球員，以 Yahoo 系統內 waiver 優先順序決定（第一年順序為隨機，第二年開季上季最後一名排第一位）。</li>
            </ul>
            <div className="mt-3 rounded bg-red-50 p-3 text-xs text-red-800">
              <span className="font-semibold">強制 Keeper</span>：標金超過{" "}
              <span className="font-bold">$10（含）</span>者，於該年底時必須強制 Keeper。釋出的話必須支付買斷金。
            </div>
          </section>

          {/* ===== 8. Re-acquisition Rules ===== */}
          <section className="rounded-lg border bg-white p-5">
            <h2 className="mb-1 text-lg font-semibold">合約重複入團規則</h2>
            <p className="mb-3 text-xs text-gray-400">Re-acquisition Rules</p>
            <p className="mb-2 text-sm text-gray-600">
              合約因 FAAB 或釋出離隊後，球員以不同合約狀況重複入團，合約與薪資依下列規則計算：
            </p>
            <ol className="list-inside list-decimal space-y-2 text-sm text-gray-600">
              <li>
                <span className="font-medium text-gray-700">薪資</span>：以（球員現有薪資 / 該隊當季擁有該球員的原薪資）中{" "}
                <span className="font-semibold text-red-600">較高</span>的薪資計算。
              </li>
              <li>
                <span className="font-medium text-gray-700">合約</span>：以（球員現有合約 / 該隊當季擁有該球員的原合約）中{" "}
                <span className="font-semibold text-red-600">較差</span>的合約計算。
                <p className="mt-1 text-xs text-gray-400">
                  優先順序：N/O 約最差 &gt; B 約其次 &gt; A 約再次 &gt; R 約最佳
                </p>
              </li>
            </ol>
            <div className="mt-3 rounded bg-gray-50 p-3 text-xs text-gray-500">
              <p className="font-medium text-gray-700">範例</p>
              <p className="mt-1">X 隊將 $10/B 的球員 P 釋出，隨後在 FAAB 中花費 $6 標回 P，球員 P 在 X 隊的合約仍需以 $10/B 約計算。</p>
              <p className="mt-1">X 隊將 $20/N2 的球員 Q 釋出，Y 隊花 $6 FAAB 標到 Q（此時 Q 在 Y 隊為 $6/A 約），Y 隊再將 Q 交易回 X 隊，此時 Q 在 X 隊以 $20/N2 約計算。</p>
            </div>
          </section>

          {/* ===== 14. Trade Contract Rules ===== */}
          <section className="rounded-lg border bg-white p-5">
            <h2 className="mb-1 text-lg font-semibold">交易合約規則</h2>
            <p className="mb-3 text-xs text-gray-400">Trade Contract Resolution</p>
            <p className="mb-2 text-sm text-gray-600">
              交易不影響合約狀態。被交易的球員完整繼承來源隊伍的合約。
            </p>
            <p className="text-xs text-gray-500">
              注意：若球隊交易得到一名長約球員後決定不保留，仍需支付買斷合約的金額。
            </p>
          </section>
        </div>
      )}

      {/* ==================== Tab 4: 留用與買斷 ==================== */}
      {activeTab === "keeper" && (
        <div className="space-y-6">
          {/* ===== 9. Keeper Rules ===== */}
          <section className="rounded-lg border bg-white p-5">
            <h2 className="mb-1 text-lg font-semibold">留用規則</h2>
            <p className="mb-3 text-xs text-gray-400">Keeper Rules</p>
            <dl className="grid grid-cols-2 gap-y-2 text-sm">
              <dt className="text-gray-500">留用人數 (Active)</dt>
              <dd>
                {settings.keeper_active_min} ~ {settings.keeper_active_max} 人
                (A/B/N/O)
              </dd>
              <dt className="text-gray-500">農場新秀 (Farm Rookie)</dt>
              <dd>最多 {settings.keeper_bench_max} 人 (R 約)</dd>
              <dt className="text-gray-500">延長合約成本</dt>
              <dd>每延長 1 年 +${settings.extension_cost_per_year}</dd>
            </dl>

            <div className="mt-3 border-t pt-3">
              <p className="mb-2 text-sm font-medium text-gray-700">留用名單續約</p>
              <ol className="list-inside list-decimal space-y-1 text-xs text-gray-500">
                <li>A 約球員年底 Keeper 續約：次年轉為 B 約，合約價值不變。</li>
                <li>B 約球員年底 Keeper 續 O 約：次年轉為 O 約，合約價值不變。</li>
                <li>B 約球員年底 Keeper 續長約：次年轉為 N+O 約，合約價值增加 $N*5。</li>
                <li>長約 (N 約) 球員年底 Keeper：次年自動轉為 N(Y-1) 約，合約價值不變。</li>
              </ol>
            </div>

            <div className="mt-3 border-t pt-3">
              <p className="mb-2 text-sm font-medium text-gray-700">留用名單限制</p>
              <ol className="list-inside list-decimal space-y-1 text-xs text-gray-500">
                <li>O 約球員不可續約，年底自動成為 FA 球員。</li>
                <li>長約（非 O 約）若被買斷，也成為 FA 球員。</li>
                <li>
                  若可保留人數少於（低於 {settings.keeper_active_min} 人）或多於（長約超過 {settings.keeper_active_max} 人）keeper 限制，
                  球隊需自行進行交易或買斷合約以符合限制。
                  <span className="font-semibold text-red-600">
                    （於 Keeper 名單繳交前兩日未完成之球隊將會被強制撤換 GM）
                  </span>
                </li>
              </ol>
            </div>

            <div className="mt-3 rounded bg-amber-50 p-3 text-xs text-amber-800">
              R 約球員超過 {settings.keeper_bench_max} 名時，可以 active 中以 active keeper 保留
              （合約一旦 Active 即變成 A 約）。
            </div>
          </section>

          {/* ===== 10. Buyout Rules ===== */}
          <section className="rounded-lg border bg-white p-5">
            <h2 className="mb-1 text-lg font-semibold">合約買斷</h2>
            <p className="mb-3 text-xs text-gray-400">Buyout Rules</p>
            <div className="space-y-3 text-sm">
              <div>
                <p className="font-medium">一般買斷</p>
                <p className="text-xs text-gray-500">
                  強制 Keeper / 長約 / 季後交易球員若不保留，需買斷合約。
                  買斷金額 = 球員當年薪資，並在之後的每年支付其合約之金額。
                </p>
              </div>
              <div>
                <p className="font-medium">FAAB 買斷</p>
                <p className="text-xs text-gray-500">
                  可選擇用 FAAB 執行一次買斷動作。如果如此，每年需用該年 FAAB 支付其剩餘薪資的 1/2，
                  之後每年僅需從薪資扣除 1/2 的薪資。（所有小數點後數字將自動進位）
                  <br />
                  例: $11/O 球員 &rarr; 每年 FAAB $6 + 薪資 $5。
                </p>
              </div>
              <div>
                <p className="font-medium">N 約多年買斷</p>
                <p className="text-xs text-gray-500">
                  例: $18/N3 球員不保留，需執行 3 年買斷：$18/N2、$18/N1、$18/O 共三年合約之買斷動作。
                  多年度買斷可選擇全部以起始薪資（Salary Cap）支付，或分成起始薪資 + FAAB 各半支付。
                </p>
              </div>
            </div>

            <div className="mt-4 border-t pt-3">
              <p className="mb-2 text-sm font-medium text-gray-700">買斷限制</p>
              <ul className="list-inside list-disc space-y-1 text-xs text-gray-500">
                <li>該季季末交易之球員，不得於 Keeper 名單繳交前進行買斷。</li>
                <li>球員於季末交易後至 Keeper 名單決定前，發生受傷之狀況者可例外買斷。</li>
                <li>球員買斷於季中也可執行。</li>
              </ul>
            </div>
          </section>
        </div>
      )}

      {/* ==================== Tab 5: 其他規則 ==================== */}
      {activeTab === "other" && (
        <div className="space-y-6">
          {/* ===== 11. Injured List ===== */}
          <section className="rounded-lg border bg-white p-5">
            <h2 className="mb-1 text-lg font-semibold">傷兵制度</h2>
            <p className="mb-3 text-xs text-gray-400">Injured List Rules</p>
            <p className="text-sm text-gray-600">
              同球隊的五名球員，若有{" "}
              <span className="font-semibold">兩位以上</span>被放入 DL 格子，計算上只算一位。
              不足五名同隊球員，需從 waiver 或是交易補足五名同隊球員。
            </p>
          </section>

          {/* ===== 12. Ranking Bonus ===== */}
          <section className="rounded-lg border bg-white p-5">
            <h2 className="mb-1 text-lg font-semibold">排名獎勵金</h2>
            <p className="mb-3 text-xs text-gray-400">Ranking Bonus</p>
            <p className="mb-3 text-xs text-gray-500">
              球季結束後，季後賽前 6 名都有獎勵（類似票房收入增加的概念），獎勵為下季的額外 FAAB 競標金額。
            </p>
            <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
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

          {/* ===== 13. Rewards & Penalties ===== */}
          <section className="rounded-lg border bg-white p-5">
            <h2 className="mb-1 text-lg font-semibold">獎懲制度</h2>
            <p className="mb-3 text-xs text-gray-400">Rewards & Penalties</p>
            <div className="space-y-3 text-sm text-gray-600">
              <div>
                <p className="font-medium">5 名同隊球員規則</p>
                <p className="text-xs text-gray-500">
                  球季中 Roster 必須隨時都有該隊 5 名以上球員。
                  違反此規則第 1 次警告，後續則罰{" "}
                  <span className="font-semibold text-red-600">FAAB $5/天</span>，再不遵守則撤換球隊 GM。
                  若遇球員交易、退休或死亡，給予一個禮拜緩衝期。
                </p>
              </div>
              <div>
                <p className="font-medium">完封獎勵 (Shutout Bonus)</p>
                <p className="text-xs text-gray-500">
                  若出現完封 (14:0)，勝隊可向敗隊討取{" "}
                  <span className="font-bold text-green-600">FAAB $10</span>。
                </p>
              </div>
              <div>
                <p className="font-medium">選秀提名權</p>
                <p className="text-xs text-gray-500">
                  上賽季第一名擁有選秀第一順位提名權，選秀順位依上賽季排名依序提名。
                </p>
              </div>
            </div>
          </section>

          {/* ===== 15. Inactivity Clause ===== */}
          <section className="rounded-lg border bg-white p-5">
            <h2 className="mb-1 text-lg font-semibold">死魚條款</h2>
            <p className="mb-3 text-xs text-gray-400">Inactivity Clause</p>
            <p className="text-sm text-gray-600">
              若連續三週沒有上線，請事先請假。若無請假，三週後將直接{" "}
              <span className="font-semibold text-red-600">撤換球隊 GM</span>。
            </p>
          </section>

          {/* ===== 16. Special Clause (Legal Issue) ===== */}
          <section className="rounded-lg border bg-white p-5">
            <h2 className="mb-1 text-lg font-semibold">特別條款</h2>
            <p className="mb-3 text-xs text-gray-400">Special Clause (Legal Issue)</p>
            <p className="mb-2 text-sm text-gray-600">
              若球員在當打之年決定退休、或因為家暴案、負面新聞無法出賽或終生禁賽等狀況，依特殊案例處理：
            </p>
            <ul className="list-inside list-disc space-y-1.5 text-sm text-gray-600">
              <li>
                可以完全{" "}
                <span className="font-semibold text-green-600">不用付薪水</span>，也不用在隔年 Keeper 名單內 keep。
              </li>
              <li>需在球隊下方另外註記有這名球員。</li>
              <li>
                如果判決結果是可以回到現實球隊繼續比賽，則須將該球員放入該年度 Keep 名單，
                並以{" "}
                <span className="font-semibold">原本剩餘合約</span>{" "}
                繼續出賽，或是選擇買斷合約釋出。
              </li>
            </ul>
            <div className="mt-3 rounded bg-gray-50 p-3 text-xs text-gray-500">
              <p className="font-medium text-gray-700">範例</p>
              <p className="mt-1">
                A 隊 GM 於 2022 年因 B 球員合約到期決定續約 5 年（$26/N5）。
                B 球員於 2023 年季末因重大傷勢退休/醜聞/負面事件影響，確定 2024 年球季幾乎無法出賽。
                下一球季 A 隊 GM 可使用特別條款不支付原本 $26 的費用，直到合約結束。
              </p>
              <p className="mt-1">
                若 B 球員於 2025 賽季宣布復出，則 A 隊 GM 須將該球員放入該年度 Keep 名單並以 $26/N2 合約繼續進行，或是選擇買斷。
              </p>
            </div>
          </section>
        </div>
      )}

      {/* ==================== Tab 6: 自建系統 ==================== */}
      {activeTab === "diy" && <DIYSection />}
    </div>
  );
}

// ============================================================
// DIY Section - Build Your Own League System
// ============================================================

/** Prompt template for one-click copy */
function buildPrompt(config: {
  teams: number;
  hittingCats: string;
  pitchingCats: string;
  salaryCap: number;
  faabBudget: number;
  keeperMax: number;
  contractSystem: string;
  platform: string;
}) {
  return `Please help me build a Fantasy Baseball Keepers League Automation System with the following specifications:

## League Configuration
- Number of teams: ${config.teams}
- Scoring format: H2H (Head-to-Head) Categories
- Hitting categories: ${config.hittingCats}
- Pitching categories: ${config.pitchingCats}
- Platform: ${config.platform}

## Financial System
- Salary cap: $${config.salaryCap}
- FAAB (Free Agent Acquisition Budget): $${config.faabBudget}
- Auction draft

## Keeper / Contract System
${config.contractSystem}
- Maximum keepers per team: ${config.keeperMax}

## Technical Requirements
- Backend: FastAPI (Python) with PostgreSQL
- Frontend: Next.js + React + Tailwind CSS
- Authentication: ${config.platform} OAuth2 + JWT
- Deployment: Docker-ready

## Features Needed
1. Keeper selection interface with real-time validation and auto-save
2. Contract tracking and automatic progression (A->B->O or A->B->N(x)->O)
3. Salary cap management with buyout calculations (salary + FAAB split)
4. Player database with MLB/MiLB stats and Top 100 prospect rankings
5. Commissioner dashboard for data import, team management, and approval workflow
6. Season countdown (draft day, opening day, weekly schedule, playoffs)
7. Analytics dashboard: salary rankings, contract values, draft top 10, FAAB correlation, position preference, trade activity
8. LINE Bot integration for keeper submission reminders
9. Historical data tracking across multiple seasons (2014-2025)

Please provide the project structure, key files, and step-by-step implementation guide.
Reference project: https://github.com/kaku88life/Fantasybaseball-keeperLeagueAutomationSystem`;
}

function DIYSection() {
  // Form state for prompt generator
  const [teams, setTeams] = useState(16);
  const [hittingCats, setHittingCats] = useState("R, H, HR, RBI, SB, AVG, OPS");
  const [pitchingCats, setPitchingCats] = useState("W, SV, HLD, K, ERA, WHIP, QS");
  const [salaryCap, setSalaryCap] = useState(300);
  const [faabBudget, setFaabBudget] = useState(100);
  const [keeperMax, setKeeperMax] = useState(15);
  const [contractSystem, setContractSystem] = useState(
    "- Contract types: A (year 1) -> B (year 2) -> O (option/final year) -> FA\n- Extension: B can extend N years at +$5/year\n- Rookie contracts (R) for farm system, max 2 per team"
  );
  const [platform, setPlatform] = useState("Yahoo Fantasy");
  const [copied, setCopied] = useState(false);

  const prompt = buildPrompt({
    teams, hittingCats, pitchingCats, salaryCap, faabBudget,
    keeperMax, contractSystem, platform,
  });

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const textarea = document.createElement("textarea");
      textarea.value = prompt;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [prompt]);

  return (
    <div className="space-y-6">
      {/* Intro */}
      <section className="rounded-lg border bg-gradient-to-br from-indigo-50 to-white p-5">
        <h2 className="mb-2 text-lg font-semibold">
          打造你自己的 Keepers League 系統
        </h2>
        <p className="text-sm text-gray-600">
          本系統完全開源，歡迎其他想要經營 Keepers League 的球迷參考、Fork 或直接使用。
          以下提供完整的建置引導，讓你可以快速建立屬於自己的聯盟管理系統。
        </p>
      </section>

      {/* GitHub Link */}
      <section className="rounded-lg border bg-white p-5">
        <h2 className="mb-1 text-lg font-semibold">原始碼 Source Code</h2>
        <p className="mb-4 text-xs text-gray-400">GitHub Repository</p>
        <a
          href="https://github.com/kaku88life/Fantasybaseball-keeperLeagueAutomationSystem"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-900 px-5 py-3 text-sm font-medium text-white transition-colors hover:bg-gray-800"
        >
          <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
            <path fillRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" clipRule="evenodd" />
          </svg>
          kaku88life/Fantasybaseball-keeperLeagueAutomationSystem
        </a>
        <div className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <div className="rounded bg-gray-50 p-3">
            <p className="font-medium text-gray-700">Backend</p>
            <p className="text-xs text-gray-500">FastAPI (Python) + PostgreSQL</p>
          </div>
          <div className="rounded bg-gray-50 p-3">
            <p className="font-medium text-gray-700">Frontend</p>
            <p className="text-xs text-gray-500">Next.js 15 + React 19 + Tailwind CSS v4</p>
          </div>
          <div className="rounded bg-gray-50 p-3">
            <p className="font-medium text-gray-700">Authentication</p>
            <p className="text-xs text-gray-500">Yahoo OAuth2 + JWT</p>
          </div>
          <div className="rounded bg-gray-50 p-3">
            <p className="font-medium text-gray-700">Deployment</p>
            <p className="text-xs text-gray-500">Docker + Zeabur / Vercel / Railway</p>
          </div>
        </div>
      </section>

      {/* Setup Guide */}
      <section className="rounded-lg border bg-white p-5">
        <h2 className="mb-1 text-lg font-semibold">建置指南 Setup Guide</h2>
        <p className="mb-4 text-xs text-gray-400">Step-by-step guide</p>
        <ol className="space-y-4 text-sm">
          <li className="flex gap-3">
            <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-600">1</span>
            <div>
              <p className="font-medium text-gray-800">Fork & Clone</p>
              <p className="text-xs text-gray-500">
                從 GitHub 上 Fork 專案到你的帳號，然後 clone 到本地開發環境。
              </p>
              <code className="mt-1 block overflow-x-auto whitespace-nowrap rounded bg-gray-100 px-3 py-1.5 text-xs text-gray-700">
                git clone https://github.com/YOUR_USERNAME/Fantasybaseball-keeperLeagueAutomationSystem.git
              </code>
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-600">2</span>
            <div>
              <p className="font-medium text-gray-800">設定環境變數</p>
              <p className="text-xs text-gray-500">
                複製 <code className="rounded bg-gray-100 px-1">.env.example</code> 為 <code className="rounded bg-gray-100 px-1">.env</code>，
                填入你的 Yahoo API 憑證和資料庫連線資訊。
              </p>
              <code className="mt-1 block overflow-x-auto whitespace-nowrap rounded bg-gray-100 px-3 py-1.5 text-xs text-gray-700">
                cp .env.example .env
              </code>
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-600">3</span>
            <div>
              <p className="font-medium text-gray-800">取得 Yahoo API 憑證</p>
              <p className="text-xs text-gray-500">
                前往{" "}
                <a href="https://developer.yahoo.com/apps/" target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline">
                  Yahoo Developer Portal
                </a>
                {" "}建立應用程式，取得 Client ID 和 Client Secret。
              </p>
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-600">4</span>
            <div>
              <p className="font-medium text-gray-800">安裝依賴 & 啟動</p>
              <div className="mt-1 space-y-1">
                <code className="block overflow-x-auto whitespace-nowrap rounded bg-gray-100 px-3 py-1.5 text-xs text-gray-700">
                  pip install -r requirements.txt
                </code>
                <code className="block overflow-x-auto whitespace-nowrap rounded bg-gray-100 px-3 py-1.5 text-xs text-gray-700">
                  cd frontend && npm install && npm run dev
                </code>
                <code className="block overflow-x-auto whitespace-nowrap rounded bg-gray-100 px-3 py-1.5 text-xs text-gray-700">
                  python -m uvicorn api.main:app --port 8002
                </code>
              </div>
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-600">5</span>
            <div>
              <p className="font-medium text-gray-800">載入歷史資料</p>
              <p className="text-xs text-gray-500">
                使用腳本從 Yahoo API 抓取歷史名冊和交易資料，然後透過合約追溯引擎建立合約清單。
              </p>
              <div className="mt-1 space-y-1">
                <code className="block overflow-x-auto whitespace-nowrap rounded bg-gray-100 px-3 py-1.5 text-xs text-gray-700">
                  python scripts/fetch_historical_yahoo.py
                </code>
                <code className="block overflow-x-auto whitespace-nowrap rounded bg-gray-100 px-3 py-1.5 text-xs text-gray-700">
                  python scripts/rebuild_with_correct_mapping.py
                </code>
              </div>
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-600">6</span>
            <div>
              <p className="font-medium text-gray-800">修改聯盟規則</p>
              <p className="text-xs text-gray-500">
                根據你的聯盟規則修改 <code className="rounded bg-gray-100 px-1">config/settings.py</code>（隊伍數、薪資帽、合約類型等）。
                前端驗證常數在 <code className="rounded bg-gray-100 px-1">frontend/src/lib/validation.ts</code>。
              </p>
            </div>
          </li>
          <li className="flex gap-3">
            <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full bg-indigo-100 text-xs font-bold text-indigo-600">7</span>
            <div>
              <p className="font-medium text-gray-800">部署</p>
              <p className="text-xs text-gray-500">
                專案內含 Dockerfile（python:3.11-slim），可部署至 Zeabur、Railway、Render 等平台。
                前端可獨立部署至 Vercel。推送 master 分支即可自動重新部署。
              </p>
            </div>
          </li>
        </ol>
      </section>

      {/* Important Notes */}
      <section className="rounded-lg border border-red-200 bg-red-50 p-5">
        <h2 className="mb-1 text-lg font-semibold text-red-800">注意事項 Important</h2>
        <p className="mb-3 text-xs text-red-400">Security & Configuration Notes</p>
        <ul className="space-y-2 text-sm text-red-700">
          <li className="flex gap-2">
            <svg className="mt-0.5 h-4 w-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span>
              <strong>.env 檔案必須加入 .gitignore</strong> — 包含 Yahoo API 金鑰、JWT 密鑰、資料庫密碼等敏感資訊，絕對不要提交到 Git。
            </span>
          </li>
          <li className="flex gap-2">
            <svg className="mt-0.5 h-4 w-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span>
              <strong>oauth2.json 也需要 .gitignore</strong> — Yahoo OAuth token 快取檔案，包含 access token 和 refresh token。
            </span>
          </li>
          <li className="flex gap-2">
            <svg className="mt-0.5 h-4 w-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span>
              <strong>JWT_SECRET_KEY 務必自行產生</strong>
              <code className="mt-1 block overflow-x-auto whitespace-nowrap rounded bg-red-100 px-2 py-1 text-xs">python -c &quot;import secrets; print(secrets.token_hex(32))&quot;</code>
            </span>
          </li>
          <li className="flex gap-2">
            <svg className="mt-0.5 h-4 w-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <span>
              <strong>資料庫檔案 (.db) 不要提交</strong> — SQLite 資料庫為本地開發用，生產環境使用 PostgreSQL 雲端服務。
            </span>
          </li>
        </ul>
        <div className="mt-4 rounded bg-white p-3">
          <p className="mb-1 text-xs font-medium text-gray-700">.gitignore 建議新增項目：</p>
          <pre className="rounded bg-gray-900 p-3 text-xs text-green-400 overflow-x-auto">{`.env
.env.local
oauth2.json
*.db
certs/
__pycache__/
node_modules/
.next/`}</pre>
        </div>
      </section>

      {/* One-click Prompt Generator */}
      <section className="rounded-lg border bg-white p-5">
        <h2 className="mb-1 text-lg font-semibold">AI 提示詞產生器</h2>
        <p className="mb-4 text-xs text-gray-400">
          One-click Prompt Generator — 根據你的聯盟設定，產生可直接貼給 AI 的建置提示詞
        </p>

        {/* Config form */}
        <div className="mb-6 grid gap-4 sm:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">隊伍數量</label>
            <input
              type="number"
              min={4}
              max={30}
              value={teams}
              onChange={(e) => setTeams(Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">平台</label>
            <select
              value={platform}
              onChange={(e) => setPlatform(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            >
              <option>Yahoo Fantasy</option>
              <option>ESPN Fantasy</option>
              <option>CBS Sports</option>
              <option>Fantrax</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">薪資帽 ($)</label>
            <input
              type="number"
              min={100}
              max={1000}
              value={salaryCap}
              onChange={(e) => setSalaryCap(Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">FAAB 預算 ($)</label>
            <input
              type="number"
              min={50}
              max={500}
              value={faabBudget}
              onChange={(e) => setFaabBudget(Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">最大留用人數</label>
            <input
              type="number"
              min={5}
              max={25}
              value={keeperMax}
              onChange={(e) => setKeeperMax(Number(e.target.value))}
              className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600">打擊數據類別</label>
            <input
              type="text"
              value={hittingCats}
              onChange={(e) => setHittingCats(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            />
          </div>
          <div className="sm:col-span-2">
            <label className="mb-1 block text-xs font-medium text-gray-600">投球數據類別</label>
            <input
              type="text"
              value={pitchingCats}
              onChange={(e) => setPitchingCats(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            />
          </div>
          <div className="sm:col-span-2">
            <label className="mb-1 block text-xs font-medium text-gray-600">合約系統描述</label>
            <textarea
              rows={3}
              value={contractSystem}
              onChange={(e) => setContractSystem(e.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:ring-indigo-500"
            />
          </div>
        </div>

        {/* Generated prompt preview */}
        <div className="relative">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-xs font-medium text-gray-600">產生的提示詞 Generated Prompt</p>
            <button
              onClick={handleCopy}
              className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
                copied
                  ? "bg-green-100 text-green-700"
                  : "bg-indigo-600 text-white hover:bg-indigo-500"
              }`}
            >
              {copied ? (
                <>
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  已複製
                </>
              ) : (
                <>
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                  複製提示詞
                </>
              )}
            </button>
          </div>
          <pre className="max-h-80 overflow-auto rounded-lg bg-gray-900 p-4 text-xs leading-relaxed text-gray-300">
            {prompt}
          </pre>
        </div>

        <p className="mt-4 text-xs text-gray-400">
          將上方提示詞貼到 Claude、ChatGPT 或其他 AI 工具，即可獲得客製化的建置指引。
          搭配本專案原始碼作為參考，可以大幅加速開發流程。
        </p>
      </section>
    </div>
  );
}
