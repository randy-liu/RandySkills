#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const os = require('os');

const isGlobal = process.argv.includes('-g') || process.argv.includes('--global');
const sourceDir = path.join(__dirname, '..', 'skills');

// 掃描 skills/ 底下所有含 SKILL.md 的目錄，新增 skill 不需再改本檔
function discoverSkills(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .filter((name) => fs.existsSync(path.join(dir, name, 'SKILL.md')));
}

const skillNames = discoverSkills(sourceDir);

// Helper to copy directory recursively
function copyRecursiveSync(src, dest) {
  const exists = fs.existsSync(src);
  if (!exists) return;
  const stats = fs.statSync(src);
  const isDirectory = stats.isDirectory();

  if (isDirectory) {
    if (!fs.existsSync(dest)) {
      fs.mkdirSync(dest, { recursive: true });
    }
    fs.readdirSync(src).forEach(function(childItemName) {
      copyRecursiveSync(path.join(src, childItemName), path.join(dest, childItemName));
    });
  } else {
    fs.copyFileSync(src, dest);
  }
}

function escapeRegExp(str) {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Helper to append skill content to a file
function appendSkillToFile(targetFilePath, skillContent, toolName, skillName) {
  try {
    const dir = path.dirname(targetFilePath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }

    let content = '';
    const marker = `[Tool/Skill: ${skillName}]`;
    const wrappedContent = `\n=========================================\n${marker}\n${skillContent}\n=========================================\n`;

    if (fs.existsSync(targetFilePath)) {
      content = fs.readFileSync(targetFilePath, 'utf8');

      // 使用 Regex 尋找舊的 Skill 區塊並移除
      const regex = new RegExp(`\\n=========================================\\n\\[Tool/Skill: ${escapeRegExp(skillName)}\\][\\s\\S]*?\\n=========================================\\n`, 'g');

      if (content.match(regex)) {
        console.log(`[${toolName}] 🔄 偵測到舊版 ${skillName}，正在進行覆寫更新...`);
        content = content.replace(regex, '');
      } else if (content.includes(marker)) {
        // 只認 marker，不認裸的 skill 名稱：skill 之間會互相引用，
        // 用裸名稱判斷會把「別的 skill 內文提到我」誤判成殘留區塊而整個跳過安裝。
        console.log(`[${toolName}] ⚠️ 發現 ${skillName} 的殘留標記但格式不符，請手動清理舊內容後再安裝。`);
        return;
      }
    }

    fs.writeFileSync(targetFilePath, content + wrappedContent, 'utf8');
    console.log(`[${toolName}] ✅ ${skillName} 已寫入 ${targetFilePath}`);
  } catch (err) {
    console.error(`[${toolName}] ❌ ${skillName} 寫入失敗:`, err.message);
  }
}

console.log('📦 Installing Randy Skills for ALL AI Agents...\n');

if (skillNames.length === 0) {
  console.warn(`⚠️ ${sourceDir} 下找不到任何含 SKILL.md 的 skill。`);
} else {
  console.log(`偵測到 ${skillNames.length} 個 skill: ${skillNames.join('、')}`);
}

// 1. 安裝給 AGY (Gemini) 的標準目錄
let agyTargetDir;
if (isGlobal) {
  agyTargetDir = path.join(os.homedir(), '.gemini', 'config', 'skills');
  console.log('配置模式: 全域安裝 (-g)');
} else {
  agyTargetDir = path.join(process.cwd(), '.agents', 'skills');
  console.log('配置模式: 專案工作區安裝 (Workspace)');
}

try {
  copyRecursiveSync(sourceDir, agyTargetDir);
  console.log(`[AGY / Gemini] ✅ 完整 Skill 資料夾已安裝至 ${agyTargetDir}`);
} catch (error) {
  console.error(`[AGY / Gemini] ❌ 安裝失敗:`, error.message);
}

// 2. 安裝給 Claude Code 的原生 Skill 目錄 (.claude/skills)
let claudeTargetDir;
if (isGlobal) {
  claudeTargetDir = path.join(os.homedir(), '.claude', 'skills');
} else {
  claudeTargetDir = path.join(process.cwd(), '.claude', 'skills');
}

try {
  copyRecursiveSync(sourceDir, claudeTargetDir);
  console.log(`[Claude Code] ✅ 完整 Skill 資料夾已安裝至 ${claudeTargetDir}`);
} catch (error) {
  console.error(`[Claude Code] ❌ 安裝失敗:`, error.message);
}

// 3. 安裝給其他 AI Agent (將所有 skill 的指令注入到對應的設定檔)
if (skillNames.length > 0) {
  // 將 markdown 裡面的 <skill_dir> 替換為實際複製過去的絕對路徑
  // 這樣其他的 AI 才知道要去哪裡執行 Python 腳本
  const skillPayloads = skillNames.map((skillName) => ({
    name: skillName,
    content: fs.readFileSync(path.join(sourceDir, skillName, 'SKILL.md'), 'utf8')
      .replace(/<skill_dir>/g, path.join(agyTargetDir, skillName))
  }));

  // Cursor / Windsurf / Copilot 沒有「全域規則檔」的概念，只認專案根目錄下的設定檔。
  //
  // -g + 本機 repo checkout：寫回 repo 根目錄（= 這三個檔的維護本體），
  //   使用者不必先 cd 進 repo，也不會在別的資料夾亂灑設定檔。
  // 其餘情況（npx 執行、或專案工作區模式）：跟著 cwd 走。
  //   🔴 npx 執行時 __dirname 位於 npm 的暫存快取（_npx/...），用完即刪，
  //   寫進去等於沒寫；此時 cwd 才是使用者真正想設定的專案。
  const repoRoot = path.join(__dirname, '..');
  const isLocalCheckout = fs.existsSync(path.join(repoRoot, '.git'));
  const rulesDir = (isGlobal && isLocalCheckout) ? repoRoot : process.cwd();

  // 定義各家主流 AI 在專案下認得的指令檔路徑
  const aiTargets = [
    { name: 'GitHub Copilot', file: path.join(rulesDir, '.github', 'copilot-instructions.md') },
    { name: 'Cursor', file: path.join(rulesDir, '.cursorrules') },
    { name: 'Windsurf', file: path.join(rulesDir, '.windsurfrules') }
  ];

  console.log(`\n開始注入指令到各家 AI 設定檔... (寫入目錄: ${rulesDir})`);
  for (const target of aiTargets) {
    for (const skill of skillPayloads) {
      appendSkillToFile(target.file, skill.content, target.name, skill.name);
    }
  }
} else {
  console.warn(`\n⚠️ 沒有可注入的 skill，略過各家 AI 設定檔。`);
}

console.log('\n🎉 安裝完成！你的 AI 助手們現在都學會釣竿解碼矩陣了！');
