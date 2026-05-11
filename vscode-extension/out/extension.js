"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const child_process_1 = require("child_process");
const path_1 = require("path");
const STAGE_COLORS = {
    pick: '#8B8B8B',
    analyze: '#3B8CFF',
    plan: '#FFA500',
    implement: '#FF6B35',
    verify: '#2ECC71',
    document: '#9B59B6',
    review: '#3498DB',
    wrap_up: '#E67E22',
    mr: '#1ABC9C',
    done: '#7F8C8D',
};
let statusBarItem;
let fileWatcher;
let statePath;
function activate(context) {
    statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBarItem.command = 'stageflow.showNextStages';
    statusBarItem.tooltip = 'Click to see available next stages';
    context.subscriptions.push(statusBarItem);
    context.subscriptions.push(vscode.commands.registerCommand('stageflow.showNextStages', showNextStages));
    context.subscriptions.push(vscode.commands.registerCommand('stageflow.forceNext', forceNext));
    findStateFile().then(path => {
        if (path) {
            statePath = path;
            updateStatusBar(path);
            fileWatcher = vscode.workspace.createFileSystemWatcher(new vscode.RelativePattern(vscode.Uri.file(path.replace(/[\\/]current_stage\.json$/, '')), 'current_stage.json'));
            fileWatcher.onDidChange(() => updateStatusBar(path));
            fileWatcher.onDidCreate(() => updateStatusBar(path));
            context.subscriptions.push(fileWatcher);
        }
        else {
            statusBarItem.text = '$(circle) StageFlow: ?';
            statusBarItem.show();
        }
    });
}
function deactivate() {
    if (statusBarItem) {
        statusBarItem.dispose();
    }
    if (fileWatcher) {
        fileWatcher.dispose();
    }
}
async function findStateFile() {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
        return undefined;
    }
    const root = workspaceFolders[0].uri.fsPath;
    const candidate = (0, path_1.join)(root, '.claude', 'current_stage.json');
    try {
        await vscode.workspace.fs.stat(vscode.Uri.file(candidate));
        return candidate;
    }
    catch {
        vscode.window.showWarningMessage('StageFlow: No .claude/current_stage.json found. Run `python -m stageflow init` first.');
        return undefined;
    }
}
async function readStageState(path) {
    try {
        const raw = await vscode.workspace.fs.readFile(vscode.Uri.file(path));
        return JSON.parse(Buffer.from(raw).toString('utf-8'));
    }
    catch {
        return null;
    }
}
async function updateStatusBar(path) {
    const state = await readStageState(path);
    if (state) {
        const stage = state.current_stage;
        const color = STAGE_COLORS[stage] || '#FFFFFF';
        statusBarItem.text = `$(${iconForStage(stage)}) StageFlow: ${capitalize(stage)}`;
        statusBarItem.color = color;
        statusBarItem.show();
    }
    else {
        statusBarItem.text = '$(error) StageFlow: error';
        statusBarItem.show();
    }
}
async function showNextStages() {
    if (!statePath) {
        vscode.window.showInformationMessage('StageFlow state file not found.');
        return;
    }
    const state = await readStageState(statePath);
    if (!state) {
        vscode.window.showErrorMessage('Failed to read StageFlow state.');
        return;
    }
    const current = state.current_stage;
    const items = [];
    items.push({
        label: `Current stage: ${capitalize(current)}`,
        description: '$(circle-filled)',
        alwaysShow: true,
    });
    items.push({ label: '', kind: vscode.QuickPickItemKind.Separator, alwaysShow: false });
    const nextStages = state.available_next || [];
    if (nextStages.length > 0) {
        items.push({
            label: 'Available Next Stages',
            kind: vscode.QuickPickItemKind.Separator,
        });
        for (const ns of nextStages) {
            items.push({
                label: `→ ${capitalize(ns)}`,
                description: `Transition to ${ns}`,
            });
        }
    }
    if (state.history && state.history.length > 0) {
        items.push({
            label: 'Recent History',
            kind: vscode.QuickPickItemKind.Separator,
        });
        for (const h of state.history.slice(-3).reverse()) {
            items.push({
                label: `${capitalize(h.from)} → ${capitalize(h.to)}`,
                description: new Date(h.at).toLocaleString(),
            });
        }
    }
    items.push({
        label: 'Force Next Stage',
        kind: vscode.QuickPickItemKind.Separator,
    });
    items.push({
        label: '$(debug-step-over) Force next stage',
        description: 'Skip conditions and advance',
    });
    const pick = await vscode.window.showQuickPick(items, {
        placeHolder: `StageFlow — ${capitalize(current)}`,
        matchOnDescription: true,
    });
    if (!pick) {
        return;
    }
    if (pick.label === '$(debug-step-over) Force next stage') {
        forceNext();
    }
    else if (pick.label.startsWith('→ ')) {
        const target = pick.label.slice(2).toLowerCase();
        await runStageflowCommand(`python scripts/stage_next.py "${target}"`);
        if (statePath) {
            updateStatusBar(statePath);
        }
    }
}
async function forceNext() {
    const result = await vscode.window.showWarningMessage('Force advance to next stage? Conditions will be skipped.', { modal: true }, 'Force Next');
    if (result === 'Force Next') {
        await runStageflowCommand('python scripts/stage_next.py --force');
        if (statePath) {
            updateStatusBar(statePath);
        }
    }
}
function runStageflowCommand(command) {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    const cwd = workspaceFolders && workspaceFolders.length > 0
        ? workspaceFolders[0].uri.fsPath
        : undefined;
    return new Promise((resolve) => {
        (0, child_process_1.exec)(command, { cwd }, (error, stdout, stderr) => {
            if (error) {
                vscode.window.showErrorMessage(`StageFlow: ${stderr || error.message}`);
            }
            else {
                vscode.window.showInformationMessage(`StageFlow: ${stdout.trim()}`);
            }
            resolve();
        });
    });
}
function iconForStage(stage) {
    const icons = {
        pick: 'search',
        analyze: 'search-view-icon',
        plan: 'lightbulb',
        implement: 'tools',
        verify: 'check-all',
        document: 'book',
        review: 'eye',
        wrap_up: 'package',
        mr: 'git-pull-request',
        done: 'check',
    };
    return icons[stage] || 'circle';
}
function capitalize(s) {
    return s ? s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, ' ') : s;
}
//# sourceMappingURL=extension.js.map