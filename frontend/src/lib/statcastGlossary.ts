/**
 * Single source of truth for how each Statcast metric is explained.
 *
 * Used by both the radar page and the player modal so a metric never gets two
 * different explanations. `tooltip` is the hover text; `how` is the "so what"
 * line shown in the expandable guide.
 */

export interface MetricGlossary {
  /** Short label shown in the UI. */
  label: string;
  /** Full name, English, for the hover title. */
  full: string;
  /** What the number is. */
  meaning: string;
  /** How to read it — the actionable part. */
  how: string;
  /** Rough reference points for this league's context. */
  benchmark?: string;
}

export const STATCAST_GLOSSARY = {
  xwoba: {
    label: "xwOBA",
    full: "Expected Weighted On-Base Average",
    meaning: "依每次擊球的初速與角度推算「應該」有的產能，排除守備與運氣。",
    how: "高於實際 wOBA 代表成績被低估，是買點；低於則代表運氣好、可能回落。",
    benchmark: ".320 聯盟平均 · .370 以上優異 · .400 以上頂級",
  },
  woba: {
    label: "wOBA",
    full: "Weighted On-Base Average",
    meaning: "實際的加權上壘率，把各種上壘方式依價值加權。",
    how: "和 xwOBA 一起看：兩者差距就是運氣成分。",
    benchmark: ".320 聯盟平均 · .370 以上優異",
  },
  xwoba_against: {
    label: "被打 xwOBA",
    full: "Expected wOBA Against",
    meaning: "打者面對這名投手時的預期產能，越低代表壓制力越強。",
    how: "低於 .280 是宰制級；高於 .350 代表被打得很扎實，成績遲早反映。",
    benchmark: ".280 以下宰制 · .320 平均 · .350 以上危險",
  },
  barrel_rate: {
    label: "Barrel%",
    full: "Barrel Rate",
    meaning: "同時具備理想初速與仰角的擊球比例（Savant 定義的 barrel）。",
    how: "最能預測長打與全壘打的單一指標，上升通常領先成績反映。",
    benchmark: "6% 聯盟平均 · 10% 以上偏高 · 15% 以上優異",
  },
  barrel_rate_against: {
    label: "被 Barrel%",
    full: "Barrel Rate Against",
    meaning: "被打出理想擊球的比例，越低越好。",
    how: "上升代表球被打得越來越扎實，是失分增加的前兆。",
    benchmark: "6% 聯盟平均 · 4% 以下優秀 · 10% 以上危險",
  },
  hard_hit_rate: {
    label: "強擊率",
    full: "Hard-Hit Rate",
    meaning: "初速達 95 mph 以上的擊球比例。",
    how: "比 Barrel% 樣本更穩定，適合在小樣本時判斷擊球品質。",
    benchmark: "38% 聯盟平均 · 45% 以上優異",
  },
  hard_hit_rate_against: {
    label: "被強擊率",
    full: "Hard-Hit Rate Against",
    meaning: "被打出 95 mph 以上的比例，越低越好。",
    how: "配合被打 xwOBA 看：兩者同時上升代表狀況真的變差，不是運氣。",
    benchmark: "38% 聯盟平均 · 32% 以下優秀",
  },
  avg_ev: {
    label: "平均初速",
    full: "Average Exit Velocity",
    meaning: "所有擊球出去的平均速度（mph）。",
    how: "反映純粹的力量，短期波動比 Barrel% 小。",
    benchmark: "88.5 mph 聯盟平均 · 92 mph 以上優異",
  },
  whiff_rate: {
    label: "Whiff%",
    full: "Whiff Rate",
    meaning: "揮棒落空次數 ÷ 總揮棒次數，代表決勝球的宰制力。",
    how: "投手的三振能力先行指標，通常比 K/9 更早反映狀態變化。",
    benchmark: "25% 聯盟平均 · 30% 以上優異 · 35% 以上頂級",
  },
  velo: {
    label: "速球均速",
    full: "Average Fastball Velocity",
    meaning: "四縫線 / 伸卡 / 卡特的平均球速（mph）。",
    how: "雙向訊號：明顯掉速常是傷兵前兆；上升代表健康恢復或轉任後援。",
    benchmark: "掉 1.5 mph 以上值得警戒",
  },
  csw_rate: {
    label: "CSW%",
    full: "Called Strikes + Whiffs Rate",
    meaning: "（被抓看好球 + 揮空）÷ 總球數，衡量每一球的宰制力。",
    how: "分母是總球數而非揮棒數，比 Whiff% 穩定，通常比 K/9 更早反映狀態變化。",
    benchmark: "28% 聯盟平均 · 30% 以上優異 · 33% 以上頂級",
  },
  k_rate: {
    label: "K%",
    full: "Strikeout Rate",
    meaning: "三振數 ÷ 打席數。",
    how: "打者越低越好、投手越高越好。比 K/9 不受局數長短影響。",
    benchmark: "打者 22% 聯盟平均 · 投手 22% 平均、27% 以上優異",
  },
  bb_rate: {
    label: "BB%",
    full: "Walk Rate",
    meaning: "保送數 ÷ 打席數。",
    how: "打者越高代表選球好（OBP 底氣）；投手越低越好，配合 K% 看控球。",
    benchmark: "8.5% 聯盟平均",
  },
  swing_rate: {
    label: "Swing%",
    full: "Swing Rate",
    meaning: "揮棒次數 ÷ 總球數。",
    how: "單獨看意義不大，要配 Chase% 判斷「揮得多」是積極還是浮躁。",
    benchmark: "47% 聯盟平均",
  },
  chase_rate: {
    label: "Chase%",
    full: "Chase Rate (O-Swing%)",
    meaning: "對好球帶外的球揮棒的比例。",
    how: "打者越低代表選球紀律越好；投手越高代表誘騙能力強。",
    benchmark: "28% 聯盟平均 · 打者 24% 以下優異",
  },
  xba: {
    label: "xBA",
    full: "Expected Batting Average",
    meaning: "依擊球初速與角度推算的預期打擊率。",
    how: "與實際 AVG 的差距即運氣成分，比 AVG 更早反映真實水準。",
    benchmark: ".250 聯盟平均",
  },
  xslg: {
    label: "xSLG",
    full: "Expected Slugging",
    meaning: "依擊球品質推算的預期長打率。",
    how: "配合 Barrel% 看長打潛力，比 SLG 少了球場與守備的雜訊。",
    benchmark: ".410 聯盟平均",
  },
  fip: {
    label: "FIP",
    full: "Fielding Independent Pitching",
    meaning: "只用三振、保送、觸身、被全壘打計算的防禦率，排除守備影響。",
    how: "ERA 遠高於 FIP 代表運氣或守備拖累、後續可能好轉；反之則可能回落。",
    benchmark: "與 ERA 同尺度，聯盟平均約 4.00",
  },
  gb_rate: {
    label: "GB%",
    full: "Ground Ball Rate",
    meaning: "滾地球佔所有擊球的比例。",
    how: "投手高 GB% 抑制長打；打者過高則長打受限。",
    benchmark: "43% 聯盟平均",
  },
  pa: {
    label: "PA",
    full: "Plate Appearances",
    meaning: "此區間內的打席數，是判斷樣本是否足夠的依據。",
    how: "低於 20 打席的比率數據波動大，僅供參考。",
  },
  pitches: {
    label: "球數",
    full: "Pitches Thrown",
    meaning: "此區間內投出的總球數。",
    how: "低於 100 球的比率數據波動大，僅供參考。",
  },
} as const satisfies Record<string, MetricGlossary>;

export type MetricKey = keyof typeof STATCAST_GLOSSARY;

/** Build the hover text for a metric: what it is, then how to read it. */
export function metricTooltip(key: MetricKey): string {
  const g = STATCAST_GLOSSARY[key];
  const parts = [`${g.label}（${g.full}）`, g.meaning, `解讀：${g.how}`];
  if ("benchmark" in g && g.benchmark) parts.push(`參考值：${g.benchmark}`);
  return parts.join("\n");
}

/** Metrics shown for each role, in display order. */
export const BATTER_METRICS: MetricKey[] = [
  "xwoba",
  "woba",
  "barrel_rate",
  "hard_hit_rate",
  "avg_ev",
  "pa",
];

export const PITCHER_METRICS: MetricKey[] = [
  "xwoba_against",
  "csw_rate",
  "velo",
  "barrel_rate_against",
  "hard_hit_rate_against",
  "pitches",
];
