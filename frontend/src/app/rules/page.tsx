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
        5-Man MLB Keeper League 聯盟規則總覽（2025.02.26 版）
      </p>

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
              <li><span className="font-medium text-gray-700">年底 Keeper 續約</span>：請參見「留用規則」區塊。</li>
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
            <span className="font-bold">$10（含）</span>者，於該年底時必須強制 Keeper，不可釋出。
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
            <dt className="text-gray-500">板凳留用 (Bench)</dt>
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

        {/* ===== 15. Inactivity Clause ===== */}
        <section className="rounded-lg border bg-white p-5">
          <h2 className="mb-1 text-lg font-semibold">死魚條款</h2>
          <p className="mb-3 text-xs text-gray-400">Inactivity Clause</p>
          <p className="text-sm text-gray-600">
            若連續三週沒有上線，請事先請假。若無請假，三週後將直接{" "}
            <span className="font-semibold text-red-600">撤換球隊 GM</span>。
          </p>
        </section>

        {/* ===== 16. Special Clause (League Issue) ===== */}
        <section className="rounded-lg border bg-white p-5">
          <h2 className="mb-1 text-lg font-semibold">特別條款</h2>
          <p className="mb-3 text-xs text-gray-400">Special Clause (League Issue)</p>
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
    </div>
  );
}
