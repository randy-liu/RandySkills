#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const os = require('os');

const isGlobal = process.argv.includes('-g') || process.argv.includes('--global');
const sourceDir = path.join(__dirname, '..', 'skills');
const skillName = 'rod-spec-decrypter';
const skillMdPath = path.join(sourceDir, skillName, 'SKILL.md');

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

// Helper to append skill content to a file
function appendSkillToFile(targetFilePath, skillContent, toolName) {
  try {
    const dir = path.dirname(targetFilePath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    
    let content = '';
    const wrappedContent = `\n=========================================\n[Tool/Skill: ${skillName}]\n${skillContent}\n=========================================\n`;
    
    if (fs.existsSync(targetFilePath)) {
      content = fs.readFileSync(targetFilePath, 'utf8');
      
      // 使用 Regex 尋找舊的 Skill 區塊並移除
      const regex = new RegExp(`\\n=========================================\\n\\[Tool/Skill: ${skillName}\\][\\s\\S]*?\\n=========================================\\n`, 'g');
      
      if (content.match(regex)) {
        console.log(`[${toolName}] 🔄 偵測到舊版 Skill，正在進行覆寫更新...`);
        content = content.replace(regex, '');
      } else if (content.includes(skillName)) {
        console.log(`[${toolName}] ⚠️ 發現殘留標記但格式不符，請手動清理舊內容後再安裝。`);
        return;
      }
    }
    
    fs.writeFileSync(targetFilePath, content + wrappedContent, 'utf8');
    console.log(`[${toolName}] ✅ 已成功寫入最新指令到 ${targetFilePath}`);
  } catch (err) {
    console.error(`[${toolName}] ❌ 寫入失敗:`, err.message);
  }
}

console.log('📦 Installing Randy Skills for ALL AI Agents...\n');

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

// 3. 安裝給其他 AI Agent (將指令注入到對應的設定檔)
if (fs.existsSync(skillMdPath)) {
  const rawSkillContent = fs.readFileSync(skillMdPath, 'utf8');
  const targetSkillDir = path.join(agyTargetDir, skillName);
  
  // 將 markdown 裡面的 <skill_dir> 替換為實際複製過去的絕對路徑
  // 這樣其他的 AI 才知道要去哪裡執行 Python 腳本
  const resolvedContent = rawSkillContent.replace(/<skill_dir>/g, targetSkillDir);
  
  const cwd = process.cwd();

  // 定義各家主流 AI 在專案下認得的指令檔路徑
  const aiTargets = [
    { name: 'GitHub Copilot', file: path.join(cwd, '.github', 'copilot-instructions.md') },
    { name: 'Cursor', file: path.join(cwd, '.cursorrules') },
    { name: 'Windsurf', file: path.join(cwd, '.windsurfrules') }
  ];

  console.log('\n開始注入指令到各家 AI 設定檔...');
  for (const target of aiTargets) {
    appendSkillToFile(target.file, resolvedContent, target.name);
  }
} else {
  console.warn(`\n⚠️ 找不到 SKILL.md (${skillMdPath})，無法注入指令到其他 AI。`);
}

console.log('\n🎉 安裝完成！你的 AI 助手們現在都學會釣竿解碼矩陣了！');
