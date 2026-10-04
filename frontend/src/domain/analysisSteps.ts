// Stages 2-5 in the order they run (docs/SPECS.md section 8): each reads the file the one before wrote.

export type AnalysisStep = 'analyze' | 'diagnose' | 'predict' | 'report'

export const ANALYSIS_STEPS: readonly AnalysisStep[] = ['analyze', 'diagnose', 'predict', 'report']
