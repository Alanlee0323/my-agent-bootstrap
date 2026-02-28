# Agent Bundle + Adapter 草案（對齊現有 bootstrap/scheduler）

## 0. 結論先行

你的核心需求是成立的：
- 同一份 `my-agent-skills` 作為統一來源
- 針對不同 CLI agent（Codex / Copilot CLI / Gemini CLI）套用不同技能組合包
- 輸出必須可重現、可版本追蹤

因此建議保留現有 `AGENTS.md + skill_scheduler.py` 路由架構，新增「Bundle + Adapter Compiler」層來做跨平台翻譯。

---

## 1. 既有架構（已驗證）

根據目前 repo：
- `agent-bootstrap` 已有 `AGENTS.md` 與 `skill_scheduler.py`
- scheduler 已支援 `./skills/`（project-local）覆寫 `./my-agent-skills/`（global）
- 既有流程是 `Discover -> Filter -> Targeted Read`，並有 `max-skill-reads` guardrail

這代表你不用推翻現有系統，只要補「如何為不同 agent 生成對應啟動上下文」。

---

## 2. 目標設計

### 2.1 單一真相來源（Canonical Source）

放在 `my-agent-skills`：
- `skills/<skill>/SKILL.md`：原子技能
- `bundles/<bundle>.yaml`：角色組合包（如 engineer, finance）
- `policies/base.yaml`：共通治理規則

### 2.2 轉譯層（Adapter Compiler）

放在 `agent-bootstrap`：
- 讀 canonical spec
- 產生每個 agent 的可用輸出（prompt/config/launcher 片段）
- 強制輸出包含 scheduler 呼叫規則
- 強制注入 `intent whitelist`、`feedback loop`、`absolute path/env`

---

## 3. my-agent-skills 規格草案

### 3.1 Bundle 檔案範例

`my-agent-skills/bundles/engineer.yaml`

```yaml
name: engineer
description: Engineering workflow bundle
skills:
  - planning-implementation
  - managing-environment
  - handling-review
policy_overrides:
  output_language: zh-TW
  max_skill_reads: 3
```

`my-agent-skills/bundles/finance.yaml`

```yaml
name: finance
description: Finance analysis workflow bundle
skills:
  - planning-implementation
  - evaluating-models
  - handling-review
policy_overrides:
  output_language: zh-TW
  max_skill_reads: 3
```

### 3.2 共通 policy（示意）

`my-agent-skills/policies/base.yaml`

```yaml
require_scheduler_for_complex_tasks: true
no_destructive_git: true
default_max_skill_reads: 3
require_traceable_routing_status: true
require_json_output: true
max_scheduler_retries: 2
```

---

## 4. agent-bootstrap 目錄調整草案

```text
agent-bootstrap/
  adapters/
    codex/
      template.md
      mapper.py
    copilot/
      template.md
      mapper.py
    gemini/
      template.md
      mapper.py
  compiler/
    bundle_loader.py
    skill_loader.py
    policy_loader.py
    ir_builder.py
    renderer.py
    validator.py
  tools/
    bootstrap_agent.sh
    bootstrap_agent.bat
  outputs/              # generated artifacts
```

---

## 5. CLI 介面（MVP）

```bash
bootstrap compile --agent <codex|copilot|gemini> \
  --bundle <engineer|finance> \
  --skills-repo <path-or-url> \
  --output <dir>
```

```bash
bootstrap compile --all-agents --bundle engineer --skills-repo ../my-agent-skills --output ./.agent
bootstrap validate-spec --skills-repo ../my-agent-skills
```

---

## 6. Compile 流程

1. 讀取 `bundles/<bundle>.yaml`
2. 檢查 `skills` 是否都存在於 `my-agent-skills`
3. 載入 `policies/base.yaml` + `policy_overrides`
4. 建 IR（中介語意）
5. 套用 adapter template（codex/copilot/gemini）
6. 產出目標檔案
7. 驗證輸出是否包含必要約束（scheduler hook + whitelist + feedback loop + path policy）

---

## 7. IR（中介結構）建議

```yaml
bundle: engineer
skills:
  - id: planning-implementation
  - id: managing-environment
  - id: handling-review
policies:
  require_scheduler_for_complex_tasks: true
  no_destructive_git: true
  max_skill_reads: 3
routing_contract:
  scheduler_command: "python <ABS_SCHEDULER_PATH> --task \"<task>\" --context \"<intent>\" --max-skill-reads 3 --format json"
  execution_order: ["plan", "domain", "review"]
intent_enum:
  - planning-implementation
  - managing-environment
  - handling-review
runtime:
  scheduler_path: "<ABS_SCHEDULER_PATH or $AGENT_SCHEDULER_PATH>"
  bootstrap_root: "<ABS_PROJECT_ROOT or $AGENT_BOOTSTRAP_ROOT>"
retry_policy:
  max_retries: 2
  retry_on:
    - parse_error
    - no_match
  fail_fast_on:
    - missing_scheduler
    - invalid_intent
```

---

## 8. 與現有 scheduler 的關係

Adapter 只做「讓不同 CLI 都會遵守同一套規則」，不取代 scheduler：
- scheduler 仍負責技能發現、去重、排名、guardrail
- bundle 只決定「可用技能範圍與治理參數」
- project-local `./skills/` override 規則保持不變

補充：scheduler 需支援執行層白名單檢查（intent 不在 enum 內直接失敗），避免僅依賴 LLM prompt 約束。

---

## 9. 版本與可追蹤性

輸出檔頭固定寫入：

```text
generated_by=agent-bootstrap@x.y.z
bundle=engineer@a.b.c
skills_repo=<git_sha_or_tag>
adapter=<codex|copilot|gemini>@p.q.r
generated_at=YYYY-MM-DDTHH:mm:ssZ
```

目的：快速定位是 bundle、skills repo、還是 adapter 造成行為變化。

---

## 10. 驗證策略

### 10.1 Spec 驗證
- bundle 引用 skill 必須存在
- `SKILL.md` frontmatter 必須有 `name` 與 `description`
- policy key 必須在允許清單內

### 10.2 產物驗證
- 必含 scheduler hook
- 必含安全規則（如 no destructive git）
- 必含 intent whitelist（由 bundle skills 編譯而來）
- 必含 feedback loop 規則（stdout/stderr + retry policy）
- scheduler 路徑需為絕對路徑或受控環境變數（不可裸相對路徑）
- 不可超過目標平台可接受的 prompt 長度上限

### 10.3 跨平台 smoke tests
- 同一任務餵給三個 agent 輸出
- 檢查是否都有「先路由再執行」
- 檢查 plan/domain/review 順序是否一致
- 檢查 intent 超出白名單時是否被拒絕
- 檢查 scheduler 失敗時是否按規則重試，成功時是否輸出摘要

---

## 11. Adapter 產物必備段落（規範）

每個目標平台產物都必須包含以下語意（文字可依平台調整）：

1. Intent Whitelist
- 你只能使用下列 intent 作為 `--context` 的核心語意：
  `<intent_enum_from_bundle>`
- 不可使用清單外 intent；若任務不吻合，先回報並請求澄清或切換 bundle。

2. Scheduler Feedback Loop
- 執行 scheduler 後必須讀取 `stdout/stderr`。
- 若失敗且錯誤屬於可重試類型，修正 `--context` 後重試，最多 `<max_scheduler_retries>` 次。
- 若成功，必須摘要 scheduler 結果（候選技能、信心、下一步）。

3. Path/Runtime Contract
- 只允許使用 `<ABS_SCHEDULER_PATH>` 或 `$AGENT_SCHEDULER_PATH` 執行 scheduler。
- 禁止直接使用相對路徑 `python skill_scheduler.py`（除非已明確 `cd` 到 root 並可驗證）。

---

## 12. MVP 落地順序

1. 在 `my-agent-skills` 新增 `bundles/` 與 `policies/base.yaml`
2. 在 `agent-bootstrap` 先完成 `codex` adapter + compiler 骨架（含 whitelist/path/retry 模板）
3. 補 `validate-spec` 與最小 smoke test
4. 複製同一 IR 到 `copilot`、`gemini` adapter
5. 將 compile 整合進 `tools/bootstrap_agent.sh/.bat`

---

## 13. 風險與對策

- 風險：三個 CLI 對 prompt 載入方式不同  
  對策：維持統一 IR，差異只在 adapter 模板。

- 風險：bundle 膨脹造成上下文過長  
  對策：bundle 只放必要 skill；詳細內容仍由 scheduler targeted read 控制。

- 風險：手改產物造成漂移  
  對策：將 `outputs/` 視為編譯產物，禁止手改，改動一律回到 canonical spec。

- 風險：LLM 幻覺未定義 intent  
  對策：編譯層注入 whitelist + 執行層拒絕非白名單 intent（雙保險）。

- 風險：CWD 漂移導致 scheduler 找不到  
  對策：統一使用絕對路徑或受控環境變數，並在啟動腳本先設置 runtime env。
