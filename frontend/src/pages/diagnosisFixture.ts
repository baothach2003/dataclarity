// diagnosis.json as the diagnose answer carries it, for the Insights tests: only the fields CONTRACTS 11
// lists for FE that the page reads (hypotheses' family and lens, the lever tree, the gross sales of the
// returns lens, the calendar), matching insightsFixture.json - FIGMA_DESIGN_NOTES section 6's sample:
// orders per customer 2.10 -> 2.14 (+1,792), AOV 40.00 -> 40.40 (+952). Stage 3's customers are BUYERS
// (lever.period_totals: a sale row), so 1,225 -> 1,101 here while the KPI's active customers, returns-only
// customers included, read 1,240 -> 1,112 (the 6E2 review #1).

export function makeDiagnosis(): Record<string, unknown> {
  return {
    hypotheses: [
      { id: 'C2', family: 'customers', lens: 'customers' },
      { id: 'B1', family: 'lever', lens: 'lever' },
      { id: 'P2', family: 'product_returns', lens: 'product' },
      { id: 'T2', family: 'time', lens: 'time' },
      { id: 'P1', family: 'product_returns', lens: 'product' },
      { id: 'R1', family: 'localization_lifecycle', lens: 'localization' },
      { id: 'D1', family: 'data_quality', lens: 'data' },
      { id: 'T3', family: 'time', lens: 'time' },
      { id: 'P5', family: 'product_returns', lens: 'returns' },
    ],
    tree: {
      method: 'shapley',
      lever: {
        level1: {
          formula: 'customers*frequency*aov',
          factors: [
            { name: 'customers', value_prev: 1225, value_cur: 1101, contribution: -10752 },
            { name: 'frequency', value_prev: 2.1, value_cur: 2.14, contribution: 1792 },
            { name: 'aov', value_prev: 40, value_cur: 40.4, contribution: 952 },
          ],
        },
        level2: null,
        gross_to_net: null,
        masked_shift_alert: false,
        masked_shift_pair: null,
      },
      customers: null,
      returns: {
        gross_prev: 106000,
        gross_cur: 98000,
        returns_prev: 1840,
        returns_cur: 1848,
        deductions_prev: 0,
        deductions_cur: 0,
        charges_prev: 0,
        charges_cur: 0,
      },
      products: { volume: -7000, mix: -300, price: 0, new_products: 0, discontinued_products: -700, unidentified: 0 },
    },
    calendar: { method: 'weekday_weights', expected_cur: 95000, expected_prev: 96300, calendar_effect: -1300, calendar_adjusted_change: -6708 },
  }
}
