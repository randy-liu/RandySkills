# RandySkills 🎣

Randy 的專屬 AI 助手技能庫 (Agent Skills)。

目前收錄：

### 釣竿盲狙解碼矩陣 (Rod Spec Decrypter)
無視官方型錄的行銷修辭，從釣竿的物理幾何與材質資料反推真實調性與手感。

- **嚴格獨立分析**：每支竿獨立推演，禁止拿其他竿款交叉比對腦補。
- **動態載入廠牌字典**：技術名詞與型號命名規則都採「精準比對」，查無資料時明確揭露「不在字典庫中」，**絕不臆測**。
- **型號自動解碼**：依廠牌命名字典逐欄位拆解型號字串（長度／繼數／力量／調性／種類／機能後綴／年份）。
  ⚠️ DAIWA **把調性標在型號裡，不在規格表裡**——規格表沒有獨立的 action 欄位，這是正常的。真正的風險在於原廠會不定期塞進**沒公佈定義的字元或修飾符**（如 `722MLRSS-24` 多出來的 `S`），那些只能靠推論，Skill 會強制標為回推並附上理由與證偽判準，不會混充成原廠定義。
- **錐度診斷**：內附 Python 腳本計算幾何錐度比，並主動示警兩點式比值的已知失效情況。
- **自動產出報告**：於當前目錄輸出 Markdown 分析報告。
- **白話書寫**：報告以**國中生看得懂**為標準。外文術語保留原文並加註（`胴調子（slow taper）`、`SVF COMPILE-X（碳纖維排得密所以又輕又硬）`），數字後面一定緊接「這代表什麼」。
  ⚠️ 白話化**只改變講法，不改變內容**——可信度標示一律保留，而且講得更直白：「這是原廠寫的」／「這是我推的」／「**這是猜的**」。

## 🎯 目前支援的廠牌

> ### ⚠️ 現階段**僅支援 DAIWA（ダイワ）**。

| 廠牌 | 技術字典 | 命名字典 | 狀態 |
|---|---|---|---|
| **DAIWA** | ✅ | ✅ | **完整支援** |
| Shimano | ❌ | ❌ | 未建立 |
| Megabass / Evergreen / 其他 | ❌ | ❌ | 未建立 |

**丟非 Daiwa 的竿子進去會怎樣？** 不會亂編，但能力會明顯降級：

- ❌ **無法自動解碼型號** —— 各廠牌命名規則互不相同（長度編碼、力量字母、後綴含義皆異），沒有字典就不得憑印象拆解。AI 會直接揭露「該廠牌的命名字典尚未建立」。
- ❌ **無法解析技術名詞** —— 找不到技術字典時，該廠牌的碳布等級與專利技術一律標示為「不在字典庫中」，不推導任何物理影響。
- ✅ **幾何推演仍可運作** —— 只要你提供先徑／元徑／全長／負載，錐度運算與失效診斷照常執行。
- ⚠️ **報告會標示「可信程度降低」**，說明結論僅建立在幾何之上。

換句話說：**非 Daiwa 竿款可以用，但你會拿到一份只有幾何、沒有材質疊加的分析。** 想要完整支援請比照 [擴充其他廠牌](#擴充其他廠牌) 建立字典。

## ⚙️ 前置需求

- **Node.js** — 執行安裝腳本。
- **Python 3** — Skill 於分析時會呼叫 `scripts/calculate_taper.py` 進行錐度運算。
  未安裝 Python 不影響安裝，但分析時 AI 將無法取得幾何判定結果。

## 🚀 安裝方式

透過 `npx` 將 Skills 安裝到專案或全域環境，一次性注入到多款主流 AI 助手的設定檔內。

### 選項 1：安裝到當前專案 (Workspace)
```bash
npx github:randy-liu/RandySkills
```
*適用於：Claude Code 原生 Skill (`.claude/skills/`)、Antigravity (`.agents/skills/`)、GitHub Copilot (`.github/copilot-instructions.md`)、Cursor (`.cursorrules`)、Windsurf (`.windsurfrules`)*

### 選項 2：全域安裝 (Global)
```bash
npx github:randy-liu/RandySkills -g
```
*適用於：Antigravity (AGY) (`~/.gemini/config/skills/`)、Claude Code 全域 Skill (`~/.claude/skills/`)*

> ⚠️ 兩種模式都會將 `.cursorrules` / `.windsurfrules` / `.github/copilot-instructions.md` 寫入**執行指令時所在的目錄**。

## 🤖 支援的 AI 工具

1. **Antigravity (AGY)** — 原生 Skill 目錄
2. **Claude Code** — 原生 Skill 目錄（自動探索，不需注入 `CLAUDE.md`）
3. **GitHub Copilot** — 透過 `.github/copilot-instructions.md` 注入
4. **Cursor** — 透過 `.cursorrules` 注入
5. **Windsurf** — 透過 `.windsurfrules` 注入

## 💡 使用方式

安裝完成後直接在對話中呼叫：

> 「請幫我用釣竿解碼矩陣分析 Daiwa HL 722MHRB-19，先徑 1.8、元徑 11.8、全長 2.18m、負載 7〜21g」

AI 會自動載入廠牌字典、拆解型號、呼叫 Python 腳本完成幾何運算，並產出報告。
**提供的規格越完整，推演可信度越高**——尤其是全長與負載上限，它們會啟用錐度腳本的進階診斷。

## 📁 專案結構

```
skills/rod-spec-decrypter/
├── SKILL.md                        # 角色定義、守則、執行流程
├── references/
│   ├── daiwa_technology.md         # 技術名詞字典（Step 2 查表用）
│   └── daiwa_model_naming.md       # 型號命名規則（Step 0 拆解用）
└── scripts/
    └── calculate_taper.py          # 錐度運算與失效診斷
```

### 擴充其他廠牌

新增廠牌需要在 `references/` 下建立**兩份**字典，Skill 會依廠牌自動載入：

```
references/<廠牌>_technology.md      # 技術名詞 → 物理影響
references/<廠牌>_model_naming.md    # 型號字串 → 規格欄位
```

請比照 `daiwa_*.md` 的格式撰寫，並為每個條目標註可信度：

- 🟢 **官方明文定義** —— 原廠文件直接載明。請一併附上出處連結與原文引用；若該文件屬**其他系列**，須註明套用至本系列屬推論。
- 🟡 **由官方文案回推** —— 從原廠敘述的語境推導而來。標為 🟡 者，AI 在報告中**必須**說明其為回推結果，不得當作原廠公佈的事實。
- ⚠️ **併存的競爭假說** —— 同一欄位存在其他尚未被排除的合理解讀時，一併記錄「目前採用哪一個」「不採用的理由」與「證偽判準」。

> 🔴 撰寫「不採用的理由」時，**不得使用循環論證**——例如以「該欄位已被 X 佔用」來排除 X 以外的解讀，因為欄位歸屬正是待證的結論本身。理由必須不預設拆解結果即可獨立成立。

## 🛠️ 開發須知

**Skill 的唯一真實來源是本 repo。**

安裝腳本會**整包覆寫**目標目錄，因此直接修改 `~/.claude/skills/` 或 `~/.gemini/config/skills/` 底下的副本，會在下次安裝時被無聲蓋掉。

正確流程：

```bash
# 1. 改本 repo 的檔案
# 2. 重新部署
node bin/install.js -g
```
