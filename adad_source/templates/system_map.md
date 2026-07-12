# ADAD Architecture Source

## Metadata
- Version: 1
- Status: planning

## Environment
- State: not_required
- Services: []

## Domains

### Domain: Calculation
- Description: 專門進行核心稅率與商務計算的領域。

#### Subsystem: Core_Calculator
- Description: 負責各國與各類型稅務核心計算子系統。

##### Module: calculate_tax
- Type: function
- Description: 計算各國稅金的最簡原子函數
- Source: src/tax/calculate_tax.py
- Preferred Pattern: pure_function
- Decisions: []
- Invariants: []
- Verification: []
- Observability: not_required
- Dependencies: []
- Input:
  - amount: float
  - country: string
- Output:
  - tax: float
- TODO:
  - [ ] 補齊細部國家例外稅率支持
- Checkpoint:
  - [ ] CP-1-001 (planned)
