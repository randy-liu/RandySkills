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
    if (fs.existsSync(targetFilePath)) {
      content = fs.readFileSync(targetFilePath, 'utf8');
      if (content.includes(skillName)) {
        console.log(`[${toolName}] 已經包含此 Skill，跳過更新。`);
        return;
      }
      content += '\n\n';
    }
    
    // 加上分隔線與標籤，幫助各家 LLM 識別這是一組獨立的擴充指令
    const wrappedContent = `\n=========================================\n[Tool/Skill: ${skillName}]\n${skillContent}\n=========================================\n`;
    fs.writeFileSync(targetFilePath, content + wrappedContent, 'utf8');
    console.log(`[${toolName}] ✅ 已成功寫入指令到 ${targetFilePath}`);
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

// 2. 安裝給其他 AI Agent (將指令注入到對應的設定檔)
if (fs.existsSync(skillMdPath)) {
  const rawSkillContent = fs.readFileSync(skillMdPath, 'utf8');
  const targetSkillDir = path.join(agyTargetDir, skillName);
  
  // 將 markdown 裡面的 <skill_dir> 替換為實際複製過去的絕對路徑
  // 這樣其他的 AI 才知道要去哪裡執行 Python 腳本
  const resolvedContent = rawSkillContent.replace(/<skill_dir>/g, targetSkillDir);
  
  const cwd = process.cwd();

  // 定義各家主流 AI 在專案下認得的指令檔路徑
  const aiTargets = [
    { name: 'Claude Code', file: path.join(cwd, 'CLAUDE.md') },
    { name: 'GitHub Copilot', file: path.join(cwd, '.github', 'copilot-instructions.md') }
  ];

  console.log('\n開始注入指令到各家 AI 設定檔...');
  for (const target of aiTargets) {
    appendSkillToFile(target.file, resolvedContent, target.name);
  }
} else {
  console.warn(`\n⚠️ 找不到 SKILL.md (${skillMdPath})，無法注入指令到其他 AI。`);
}

console.log('\n🎉 安裝完成！你的 AI 助手們現在都學會釣竿解碼矩陣了！');
