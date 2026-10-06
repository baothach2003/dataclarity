// The words the front section never uses (contracts/report_front.py FRONT_BANNED; design section 3 and
// Q3): the analyst's vocabulary and every adjective verdict on a month or a change. A copy the page's tests
// read the Insights page with outside "Technical details", as report.html is read outside its appendix;
// tests/contracts/test_frontend_fixtures.py pins it to the contract's, word for word.

export const FRONT_BANNED = ['hypothesis', 'hypotheses', 'verdict', 'supported', 'ruled out', 'lens', 'lever', 'share',
  'contribution', 'aov', 'yoy', 'year-over-year', 'limits', 'inconclusive', 'revenue', 'caused',
  'because of', 'explains', 'launched', 'discontinued', 'usual', 'unusual', 'normal', 'abnormal',
  'ordinary', 'bigger than usual', 'median']

function escaped(word: string): string {
  return word.replace(/[.*+?^${}()|[\]\\-]/g, '\\$&')
}

/** The banned words `text` uses, in the list's order - as contracts/forecast_actions.py front_word_problems
 * reads a sentence: whole words, a plural "s" or "es" included. */
export function bannedIn(text: string): string[] {
  const lowered = ` ${text.toLowerCase()} `
  return FRONT_BANNED.filter((word) => new RegExp(`(?<![a-z])${escaped(word)}(?:s|es)?(?![a-z])`).test(lowered))
}
