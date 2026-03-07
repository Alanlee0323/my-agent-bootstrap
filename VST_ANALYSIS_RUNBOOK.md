# VST 財報分析 Runbook（Finance Bundle）

這份 Runbook 讓你用同一套 `my-agent-skills` + `agent-bootstrap` 流程，穩定驅動 `Codex / Copilot CLI / Gemini CLI` 分析美股 `VST (Vistra Corp.)`。

## 1. 目標

- 分析範圍：財報結構、企業品質、估值、總體環境、結論驗證、最終審核。
- 執行原則：每個關鍵階段都先跑 `skill_scheduler.py`，並用 finance intents 白名單限制上下文。
- 可重現性：固定使用 `finance` bundle + profile。

## 2. 前置條件

1. 已有兩個 repo：
- `agent-bootstrap`
- `my-agent-skills`

2. 目標專案（分析工作區）有 Python 可執行環境。

## 3. 初始化工作區（一次性）

以下以 Windows 為例：

```bat
cd C:\Users\alana\SideProjects
mkdir vst-analysis
cd vst-analysis
git init
```

建立 profile：

```bat
copy C:\Users\alana\SideProjects\agent-bootstrap\examples\agent.profile.finance-all.yaml .\agent.profile.yaml
```

套用 bootstrap + profile：

```bat
C:\Users\alana\SideProjects\agent-bootstrap\tools\bootstrap_agent.bat --target . --profile agent.profile.yaml --force
```

## 4. 驗證安裝結果

```bat
python skill_scheduler.py --status --format text
```

你應該能看到：
- `my-agent-skills` 有被掃描到
- finance 相關 skills 可被發現
- `.agent` 目錄已生成對應 adapter 產物

## 5. 固定 Intent 白名單（建議每次 session 先設）

```bat
set FIN_INTENTS=planning-financial-analysis,parsing-sec-filings,normalizing-financial-statements,analyzing-business-quality,valuing-company,analyzing-macro-regime,verifying-financial-conclusions,reviewing-financial-analysis,managing-long-term-investment-policy,conducting-investment-postmortem
```

## 6. VST 分析流程（逐步執行）

每一步都執行 scheduler，避免 agent 跳步或亂選 skill。

### Step 1: 研究規劃

```bat
python skill_scheduler.py --task "分析美股 VST，定義研究範圍、資料來源、交付格式" --context "planning-financial-analysis" --intent-whitelist "%FIN_INTENTS%" --format json
```

輸出重點：
- 研究問題清單
- 期間（例如最近 3 年 + TTM）
- 主要資料來源清單

### Step 2: 解析法規與公司揭露資料

```bat
python skill_scheduler.py --task "擷取 VST 最新與近年 10-K/10-Q/8-K 重點並保留引用鍵值" --context "parsing-sec-filings" --intent-whitelist "%FIN_INTENTS%" --format json
```

輸出重點：
- form / date / accession
- 關鍵章節摘要與引用位置

### Step 3: 財報標準化

```bat
python skill_scheduler.py --task "把 VST 財報欄位做期間對齊、單位一致化、缺值標記" --context "normalizing-financial-statements" --intent-whitelist "%FIN_INTENTS%" --format json
```

輸出重點：
- 標準化報表（IS / BS / CF）
- 單位與口徑檢查結果

### Step 4: 企業品質分析

```bat
python skill_scheduler.py --task "分析 VST 商業模式品質、競爭優勢、風險與 bull/bear 證據" --context "analyzing-business-quality" --intent-whitelist "%FIN_INTENTS%" --format json
```

### Step 5: 估值分析

```bat
python skill_scheduler.py --task "以 DCF 與可比法估值 VST，輸出 bear/base/bull 區間與敏感度" --context "valuing-company" --intent-whitelist "%FIN_INTENTS%" --format json
```

### Step 6: 總體環境映射

```bat
python skill_scheduler.py --task "評估當前總體變數對 VST 的需求、成本、資本成本與估值影響" --context "analyzing-macro-regime" --intent-whitelist "%FIN_INTENTS%" --format json
```

### Step 7: 結論驗證（重點）

```bat
python skill_scheduler.py --task "逐條驗證 VST 分析結論，優先使用 primary sources（SEC、公司官網、官方公告）" --context "verifying-financial-conclusions" --intent-whitelist "%FIN_INTENTS%" --format json
```

### Step 8: 最終審核

```bat
python skill_scheduler.py --task "對 VST 報告做 findings-first 審核，列出證據不足與假設風險" --context "reviewing-financial-analysis" --intent-whitelist "%FIN_INTENTS%" --format json
```

### Step 9: 長期投資政策（可選）

```bat
python skill_scheduler.py --task "根據 VST 分析制定長期持有/加減碼/再平衡規則與風險預算" --context "managing-long-term-investment-policy" --intent-whitelist "%FIN_INTENTS%" --format json
```

### Step 10: 事後檢討（可選，決策週期後）

```bat
python skill_scheduler.py --task "對 VST 決策進行 postmortem，區分流程錯誤與結果波動並更新規則" --context "conducting-investment-postmortem" --intent-whitelist "%FIN_INTENTS%" --format json
```

## 7. 三個 CLI Agent 的接線方式

Profile 套用後，會生成：

- `.\.agent\codex\finance\AGENTS.generated.md`
- `.\.agent\copilot\finance\copilot.prompt.md`
- `.\.agent\gemini\finance\gemini.prompt.md`

以及 launcher：

- `.\.agent\launchers\launch_codex.bat`
- `.\.agent\launchers\launch_copilot.bat`
- `.\.agent\launchers\launch_gemini.bat`

先用 launcher 設好環境變數：

```bat
.\.agent\launchers\launch_codex.bat
.\.agent\launchers\launch_copilot.bat
.\.agent\launchers\launch_gemini.bat
```

之後在各自 CLI 中載入對應 prompt 檔，並執行同一份分析任務，確保三個 agent 行為一致。

## 8. 建議的最終交付格式

每次輸出至少包含：

1. 資料時間戳（資料截止日）
2. 來源清單（primary sources 優先）
3. 核心假設與敏感度
4. 估值區間（bear/base/bull）
5. 主要風險與失效條件
6. 信心等級（High / Medium / Low）

## 9. 常見問題

1. `invalid_intent`
- `--context` 不在 `--intent-whitelist` 內。請修正 context 名稱。

2. `missing skill` 或 `0 skill(s)`
- 檢查 `my-agent-skills` 是否正確掛載在目標專案中。

3. CLI 行為不一致
- 確認三個 CLI 都使用同一個 finance adapter prompt。
- 確認每一步都有先執行 scheduler，而不是直接自由發揮。
