# RandySkills 🎣

Randy 的專屬 AI 助手技能庫 (Agent Skills)。
目前收錄：
- **釣竿盲狙解碼矩陣 (Rod Spec Decrypter)**：根據物理幾何與材質，反推釣竿的真實調性與手感。（內建支援自動於當前目錄產出 Markdown 分析報告）

## 🚀 安裝方式

你可以透過 `npx` 輕鬆將這些 Skills 安裝到你的專案或是全域環境中，本腳本支援一次性注入到多款主流 AI 助手的設定檔內。

### 選項 1：安裝到當前專案 (Workspace)
這會將指令注入到你**當前所在目錄**的 AI 設定檔中。
```bash
npx github:randy-liu/RandySkills
```
*適用於：Claude Code (`CLAUDE.md`)、GitHub Copilot (`.github/copilot-instructions.md`)*

### 選項 2：全域安裝 (Global)
除了注入當前專案的 AI 設定檔外，還會將完整的 Skill 資料夾安裝到系統全域設定中。
```bash
npx github:randy-liu/RandySkills -g
```
*適用於：Antigravity (AGY) / Gemini Agent 系統 (`~/.gemini/config/skills/`)*

## 🤖 支援的 AI 工具

安裝腳本會自動配置以下 AI 工具的設定檔：
1. **Antigravity (AGY)**
2. **Claude Code** 
3. **GitHub Copilot**

## 💡 使用方式

安裝完成後，不須輸入特殊指令，直接在對話中呼叫 AI 即可：
> 「請幫我用釣竿解碼矩陣分析這個規格：先徑 1.2，元徑 9.8...」

AI 會自動讀取設定檔內的規則，並自主呼叫內附的 Python 腳本來完成專業計算。
