#!/usr/bin/env node

const fs = require('fs');
const path = require('path');
const os = require('os');

const isGlobal = process.argv.includes('-g') || process.argv.includes('--global');
const sourceDir = path.join(__dirname, '..', 'skills');

let targetDir;
if (isGlobal) {
  targetDir = path.join(os.homedir(), '.gemini', 'config', 'skills');
} else {
  targetDir = path.join(process.cwd(), '.agents', 'skills');
}

function copyRecursiveSync(src, dest) {
  const exists = fs.existsSync(src);
  const stats = exists && fs.statSync(src);
  const isDirectory = exists && stats.isDirectory();
  
  if (isDirectory) {
    if (!fs.existsSync(dest)) {
      fs.mkdirSync(dest, { recursive: true });
    }
    fs.readdirSync(src).forEach(function(childItemName) {
      copyRecursiveSync(path.join(src, childItemName),
                        path.join(dest, childItemName));
    });
  } else {
    fs.copyFileSync(src, dest);
  }
}

console.log('📦 Installing Randy Skills...');
console.log(`Source: ${sourceDir}`);
console.log(`Target: ${targetDir}`);

try {
  copyRecursiveSync(sourceDir, targetDir);
  console.log(`✅ Skills successfully installed into ${isGlobal ? 'Global Config' : 'Workspace (.agents/skills)'}`);
} catch (error) {
  console.error('❌ Failed to install skills:', error.message);
  process.exit(1);
}
