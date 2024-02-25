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
import {
    checkIfConfigurationChanged,
    getExtensionSettings,
    getGlobalSettings,
    getInterpreterFromSetting,
    getWorkspaceSettings,
} from './common/settings';
import { loadServerDefaults } from './common/setup';
import { getLSClientTraceLevel } from './common/utilities';
import { createOutputChannel, getConfiguration, onDidChangeConfiguration, registerCommand } from './common/vscodeapi';

let lsClient: LanguageClient | undefined;
const extensionName: string = 'easypbt';
const publisherName: string = 'Ahmed-Atmani';
const namespace: string = extensionName + '.' + publisherName;

let pbtTypes: any = null; // For PBT Types Caching

export async function activate(context: vscode.ExtensionContext): Promise<void> {
    // This is required to get server name and module. This should be
    // the first thing that we do in this extension.
    const serverInfo = loadServerDefaults();
    const serverName = serverInfo.name;
    const serverId = serverInfo.module;

    // === Generate PBT
    const generatePbtCommand = vscode.commands.registerCommand(`${serverId}.generatePbt`, async () => {
        const settings = await getExtensionSettings(namespace);
        const settings2 = await getGlobalSettings(namespace);
        const settings3 = await getWorkspaceSettings(namespace, (vscode.workspace.workspaceFolders as any)[0]);
        const config = await getConfiguration(namespace);
        const test = config.get<string>('testFileNamePattern');

        console.log('EXTENSION SETTINGS: ');
        console.log(settings);

        console.log('GLOBAL SETTINGS: ');
        console.log(settings2);

        console.log('WORKSPACE SETTINGS: ');
        console.log(settings3);

        console.log('ENTIRE CONFIG: ');
        console.log(config);

        console.log('ENTRY: ');
        console.log(test);

        console.log('NAMESPACE: ');
        console.log(namespace);

        // Prompt PBT type
        const selectedType = await promptPbtType();

        console.log('Selected type: ');
        console.log(selectedType);

        // Prompt SUT;
        const selectedFunctions = await promptFunctionsToTest(selectedType.twoFunctions);

        console.log('Selected functions: ');
        console.log(selectedFunctions);

        // Get Source
        const source = vscode.window.activeTextEditor?.document.getText();

        // Generate PBT
        const result: any = await lsClient?.sendRequest('custom/generatePBT', {
            functions: selectedFunctions,
            pbtType: selectedType,
            source: source,
        });

        const pbt = await result.stdout;

        // await addPbtToEditor(pbt, selectedFunction.lineEnd + 1);
        await addPbtToEditor(pbt, selectedFunctions[0].lineEnd + 1);
    });

    context.subscriptions.push(generatePbtCommand);

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
    const result = (await lsClient?.sendRequest('custom/getPbtTypes', {})) as any;
    pbtTypes = await result.stdout;
    console.log(pbtTypes);
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

async function promptFunctionsToTest(
    selectTwoFunctions: boolean,
): Promise<[{ name: string; lineStart: number; lineEnd: number }]> {
    // selectMultiple is true when the chosen PBT type requires to have multiple functions
    // e.g. roundtrip (function and inverse), test oracle (function and oracle), ...

    const editor = vscode.window.activeTextEditor;
    const source = editor?.document.getText();

    // Check if file is empty
    if (source === undefined) {
        vscode.window.showInformationMessage('The file is empty');
        return Promise.reject('The file is empty');
    }
    const functions: any[] = await getDefinedFunctions(source);

    // Check if no functions are defined
    if (functions.length < 1) {
        vscode.window.showInformationMessage('There are no functions in this file');
        return Promise.reject('There are no functions in this file');
    }

    var selectedFunctions: any = await vscode.window.showQuickPick(functions, {
        title: 'System Under Test (SUT) selection', // Add your desired title here
        placeHolder: 'Search a function',
        canPickMany: selectTwoFunctions,
    });

    // Check if no function was selected
    if (selectedFunctions.length < 1) {
        return Promise.reject('No function selected');
    }

    // Make list of single function (a list of function has to be returned)
    if (!selectTwoFunctions) {
        selectedFunctions = [selectedFunctions];
    }

    // Check
    if (selectTwoFunctions && selectedFunctions.length !== 2) {
        vscode.window.showInformationMessage(
            'Please select exactly two functions: the function to test and its inverse',
        );
        return Promise.reject('Two functions have to be selected');
    }

    return selectedFunctions.map((selected: any) => {
        return {
            name: selected.label,
            lineStart: selected.lineStart,
            lineEnd: selected.lineEnd,
        };
    });
}

async function promptPbtType(): Promise<{
    typeId: number;
    name: string;
    description: string;
    argument: string;
    twoFunctions: boolean;
}> {
    // PBT Types Caching
    if (pbtTypes === null) {
        await getPbtTypes();
    }

    var selectedType: any = await vscode.window.showQuickPick(
        pbtTypes.map((type: any) => {
            return {
                label: type.name,
                detail: type.description,
                typeId: type.typeId,
            };
        }),
        {
            title: 'Choose a PBT type',
            placeHolder: 'Search a PBT type',
        },
    );

    return pbtTypes.find((type: any) => type.typeId === selectedType.typeId);
}

async function addPbtToEditor(pbt: string, lineNumber: number): Promise<void> {
    const editor = vscode.window.activeTextEditor;

    if (!editor) {
        vscode.window.showErrorMessage('No Python file is active');
        return;
    }

    const line = Math.max(0, lineNumber - 1);
    const lineText = editor.document.lineAt(line).text;
    const insertPosition = new vscode.Position(line, lineText.length);
    await editor.edit((editBuilder) => {
        editBuilder.insert(insertPosition, pbt);
    });
}
