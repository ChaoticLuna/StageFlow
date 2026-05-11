import * as vscode from 'vscode';
import { exec } from 'child_process';
import { watchFile } from 'fs';
import { join } from 'path';

interface StageState {
    current_stage: string;
    available_next?: string[];
    history?: Array<{ from: string; to: string; at: string }>;
}

const STAGE_COLORS: Record<string, string> = {
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

let statusBarItem: vscode.StatusBarItem;
let fileWatcher: vscode.FileSystemWatcher | undefined;
let statePath: string | undefined;

export function activate(context: vscode.ExtensionContext) {
    statusBarItem = vscode.window.createStatusBarItem(
        vscode.StatusBarAlignment.Left,
        100
    );
    statusBarItem.command = 'stageflow.showNextStages';
    statusBarItem.tooltip = 'Click to see available next stages';
    context.subscriptions.push(statusBarItem);

    context.subscriptions.push(
        vscode.commands.registerCommand('stageflow.showNextStages', showNextStages)
    );
    context.subscriptions.push(
        vscode.commands.registerCommand('stageflow.forceNext', forceNext)
    );

    findStateFile().then(path => {
        if (path) {
            statePath = path;
            updateStatusBar(path);
            fileWatcher = vscode.workspace.createFileSystemWatcher(
                new vscode.RelativePattern(
                    vscode.Uri.file(path.replace(/[\\/]current_stage\.json$/, '')),
                    'current_stage.json'
                )
            );
            fileWatcher.onDidChange(() => updateStatusBar(path));
            fileWatcher.onDidCreate(() => updateStatusBar(path));
            context.subscriptions.push(fileWatcher);
        } else {
            statusBarItem.text = '$(circle) StageFlow: ?';
            statusBarItem.show();
        }
    });
}

export function deactivate() {
    if (statusBarItem) {
        statusBarItem.dispose();
    }
    if (fileWatcher) {
        fileWatcher.dispose();
    }
}

async function findStateFile(): Promise<string | undefined> {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
        return undefined;
    }

    const root = workspaceFolders[0].uri.fsPath;
    const candidate = join(root, '.claude', 'current_stage.json');

    try {
        await vscode.workspace.fs.stat(vscode.Uri.file(candidate));
        return candidate;
    } catch {
        vscode.window.showWarningMessage(
            'StageFlow: No .claude/current_stage.json found. Run `python -m stageflow init` first.'
        );
        return undefined;
    }
}

async function readStageState(path: string): Promise<StageState | null> {
    try {
        const raw = await vscode.workspace.fs.readFile(vscode.Uri.file(path));
        return JSON.parse(Buffer.from(raw).toString('utf-8'));
    } catch {
        return null;
    }
}

async function updateStatusBar(path: string) {
    const state = await readStageState(path);
    if (state) {
        const stage = state.current_stage;
        const color = STAGE_COLORS[stage] || '#FFFFFF';
        statusBarItem.text = `$(${iconForStage(stage)}) StageFlow: ${capitalize(stage)}`;
        statusBarItem.color = color;
        statusBarItem.show();
    } else {
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
    const items: vscode.QuickPickItem[] = [];

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
    } else if (pick.label.startsWith('→ ')) {
        const target = pick.label.slice(2).toLowerCase();
        await runStageflowCommand(`python scripts/stage_next.py "${target}"`);
        if (statePath) {
            updateStatusBar(statePath);
        }
    }
}

async function forceNext() {
    const result = await vscode.window.showWarningMessage(
        'Force advance to next stage? Conditions will be skipped.',
        { modal: true },
        'Force Next'
    );
    if (result === 'Force Next') {
        await runStageflowCommand('python scripts/stage_next.py --force');
        if (statePath) {
            updateStatusBar(statePath);
        }
    }
}

function runStageflowCommand(command: string): Promise<void> {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    const cwd = workspaceFolders && workspaceFolders.length > 0
        ? workspaceFolders[0].uri.fsPath
        : undefined;

    return new Promise((resolve) => {
        exec(command, { cwd }, (error, stdout, stderr) => {
            if (error) {
                vscode.window.showErrorMessage(
                    `StageFlow: ${stderr || error.message}`
                );
            } else {
                vscode.window.showInformationMessage(
                    `StageFlow: ${stdout.trim()}`
                );
            }
            resolve();
        });
    });
}

function iconForStage(stage: string): string {
    const icons: Record<string, string> = {
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

function capitalize(s: string): string {
    return s ? s.charAt(0).toUpperCase() + s.slice(1).replace(/_/g, ' ') : s;
}
