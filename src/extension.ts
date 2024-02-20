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
import { Linter } from 'eslint';

let lsClient: LanguageClient | undefined;

let pbtTypes: any = null; // For PBT Types Caching

export async function activate(context: vscode.ExtensionContext): Promise<void> {
    // This is required to get server name and module. This should be
    // the first thing that we do in this extension.
    const serverInfo = loadServerDefaults();
    const serverName = serverInfo.name;
    const serverId = serverInfo.module;

    // === Generate PBT
    const generatePbtCommand = vscode.commands.registerCommand(`${serverId}.generatePbt`, async () => {
        // Prompt SUT
        const selectedFunction = await promptFunctionToTest();
        console.log(selectedFunction);

        // Prompt PBT type
        const selectedType = await promptPbtType();
        console.log(selectedType);

        // Get Source
        const source = vscode.window.activeTextEditor?.document.getText();

        // Generate PBT
        const result: any = await lsClient?.sendRequest('custom/generatePBT', {
            functions: [selectedFunction],
            pbtType: selectedType,
            source: source,
        });

        const pbt = result.stdout;

        await addPbtToEditor(pbt, selectedFunction.lineEnd + 1);
    });

    context.subscriptions.push(generatePbtCommand);

    // === Get All Defined Functions in File
    const getDefinedFunctionsFromFileCommand = vscode.commands.registerCommand(
        `${serverId}.getDefinedFunctionsFromFile`,
        async () => {
            var sourceCode: string = '';

            let editor = vscode.window.activeTextEditor;
            if (editor) {
                // if an editor is open
                sourceCode = editor.document.getText();
                console.log(sourceCode);
            }

            const functions: any = await getDefinedFunctions(sourceCode);

            vscode.window.showQuickPick(functions);
        },
    );

    context.subscriptions.push(getDefinedFunctionsFromFileCommand);

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

async function getDefinedFunctions(source: string): Promise<[{ name: string; lineStart: number; lineEnd: number }]> {
    const response: any = await lsClient?.sendRequest('custom/getDefinedFunctionsFromFile', { source: source });
    const definedFunctions = await response.stdout.map((cell: any) => {
        return {
            label: cell.name,
            detail: 'line ' + cell.lineStart.toString() + '-' + cell.lineEnd.toString(),
            lineStart: cell.lineStart,
            lineEnd: cell.lineEnd,
        };
    });

    return definedFunctions;
}

async function promptFunctionToTest(): Promise<{ name: string; lineStart: number; lineEnd: number }> {
    const editor = vscode.window.activeTextEditor;
    const source = editor?.document.getText();

    if (source === undefined) {
        vscode.window.showInformationMessage('The file is empty');
        return Promise.reject('The file is empty');
    }
    const functions: any = await getDefinedFunctions(source);
    var selectedFunction: any = await vscode.window.showQuickPick(functions);

    if (!selectedFunction) {
        return Promise.reject('No function selected');
    }

    return {
        name: selectedFunction.label,
        lineStart: selectedFunction.lineStart,
        lineEnd: selectedFunction.lineEnd,
    };
}

async function promptPbtType(): Promise<{ label: string; detail: string; argument: string }> {
    // PBT Types Caching
    if (pbtTypes === null) {
        await getPbtTypes();
    }

    var selectedType: any = await vscode.window.showQuickPick(pbtTypes);

    return selectedType;
}

async function addPbtToEditor(pbt: string, lineNumber: number): Promise<void> {
    const editor = vscode.window.activeTextEditor;

    if (!editor) {
        vscode.window.showErrorMessage('No Python file is active');
        return;
    }

    const line = lineNumber - 1;
    const lineText = editor.document.lineAt(line).text;
    const insertPosition = new vscode.Position(line, lineText.length);
    await editor.edit((editBuilder) => {
        editBuilder.insert(insertPosition, pbt);
    });
}
