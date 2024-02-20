// Copyright (c) Microsoft Corporation. All rights reserved.
// Licensed under the MIT License.

import * as vscode from 'vscode';
import { LanguageClient } from 'vscode-languageclient/node';
import { registerLogger, traceError, traceLog, traceVerbose } from './common/log/logging';
import {
    checkVersion,
    getInterpreterDetails,
    initializePython,
    onDidChangePythonInterpreter,
    resolveInterpreter,
} from './common/python';
import { restartServer } from './common/server';
import { checkIfConfigurationChanged, getInterpreterFromSetting } from './common/settings';
import { loadServerDefaults } from './common/setup';
import { getLSClientTraceLevel } from './common/utilities';
import { createOutputChannel, onDidChangeConfiguration, registerCommand } from './common/vscodeapi';

let lsClient: LanguageClient | undefined;

let pbtTypes: any = null; // For PBT Types Caching

export async function activate(context: vscode.ExtensionContext): Promise<void> {
    // This is required to get server name and module. This should be
    // the first thing that we do in this extension.
    const serverInfo = loadServerDefaults();
    const serverName = serverInfo.name;
    const serverId = serverInfo.module;

    // === Choose PBT TYPE
    const choosePbtTypeCommand = vscode.commands.registerCommand(`${serverId}.choosePbtType`, async () => {
        // PBT Types Caching
        if (pbtTypes === null) {
            await getPbtTypes();
        }

        var selectedType = await vscode.window.showQuickPick(pbtTypes);
        console.log('SELECTED PBT TYPE: ' + JSON.stringify(selectedType, null, 4));

        let editor = vscode.window.activeTextEditor;
        if (editor) {
            // if an editor is open
            let selectedCode = editor.document.getText(editor.selection);
            console.log(selectedCode);
        }
    });

    context.subscriptions.push(choosePbtTypeCommand);

    // === TEST COMMAND
    const testCommand = vscode.commands.registerCommand(`${serverId}.testCommand`, async () => {
        try {
            const response: any = await lsClient?.sendRequest('custom/testCommand', {
                functions: ['def encode(n: int) -> int:\n\treturn n+1\n', 'def decode(n: int) -> int:\n\treturn n-1\n'],
                pbtType: '--roundtrip',
            });
            console.log('Response:', response); // Log the response
            if (response !== undefined) {
                vscode.window.showInformationMessage('Received response: ' + response);
                vscode.window.showInformationMessage('Body: ' + response.stdout);
            } else {
                vscode.window.showErrorMessage('No response received or response is undefined');
            }
        } catch (error: any) {
            console.error('Error sending request:', error);
            vscode.window.showErrorMessage('Error sending request: ' + error.message);
        }
    });

    context.subscriptions.push(testCommand);

    // Setup logging
    const outputChannel = createOutputChannel(serverName);
    context.subscriptions.push(outputChannel, registerLogger(outputChannel));

    const changeLogLevel = async (c: vscode.LogLevel, g: vscode.LogLevel) => {
        const level = getLSClientTraceLevel(c, g);
        await lsClient?.setTrace(level);
    };

    context.subscriptions.push(
        outputChannel.onDidChangeLogLevel(async (e) => {
            await changeLogLevel(e, vscode.env.logLevel);
        }),
        vscode.env.onDidChangeLogLevel(async (e) => {
            await changeLogLevel(outputChannel.logLevel, e);
        }),
    );

    // Log Server information
    traceLog(`Name: ${serverInfo.name}`);
    traceLog(`Module: ${serverInfo.module}`);
    traceVerbose(`Full Server Info: ${JSON.stringify(serverInfo)}`);

    const runServer = async () => {
        const interpreter = getInterpreterFromSetting(serverId);
        if (interpreter && interpreter.length > 0) {
            if (checkVersion(await resolveInterpreter(interpreter))) {
                traceVerbose(`Using interpreter from ${serverInfo.module}.interpreter: ${interpreter.join(' ')}`);
                lsClient = await restartServer(serverId, serverName, outputChannel, lsClient);
            }
            return;
        }
        const interpreterDetails = await getInterpreterDetails();
        if (interpreterDetails.path) {
            traceVerbose(`Using interpreter from Python extension: ${interpreterDetails.path.join(' ')}`);
            lsClient = await restartServer(serverId, serverName, outputChannel, lsClient);
            return;
        }
        traceError(
            'Python interpreter missing:\r\n' +
                '[Option 1] Select python interpreter using the ms-python.python.\r\n' +
                `[Option 2] Set an interpreter using "${serverId}.interpreter" setting.\r\n` +
                'Please use Python 3.8 or greater.',
        );
    };

    context.subscriptions.push(
        onDidChangePythonInterpreter(async () => {
            await runServer();
        }),
        onDidChangeConfiguration(async (e: vscode.ConfigurationChangeEvent) => {
            if (checkIfConfigurationChanged(e, serverId)) {
                await runServer();
            }
        }),
        registerCommand(`${serverId}.restart`, async () => {
            await runServer();
        }),
    );

    setImmediate(async () => {
        const interpreter = getInterpreterFromSetting(serverId);
        if (interpreter === undefined || interpreter.length === 0) {
            traceLog(`Python extension loading`);
            await initializePython(context.subscriptions);
            traceLog(`Python extension loaded`);
        } else {
            await runServer();
        }
    });
}

export async function deactivate(): Promise<void> {
    if (lsClient) {
        await lsClient.stop();
    }
}

async function getPbtTypes(): Promise<void> {
    const response: any = await lsClient?.sendRequest('custom/getPbtTypes', {});
    pbtTypes = await response.stdout.map((type: any) => {
        return {
            label: type.name,
            detail: type.description,
            argument: type.argument,
        };
    });
    return;
}
