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
import { Console } from 'console';

let lsClient: LanguageClient | undefined;
const extensionName: string = 'easypbt';
const publisherName: string = 'Ahmed-Atmani';
const namespace: string = extensionName + '.' + publisherName;

let pbtTypes: any = null; // For PBT Types Caching
let testFileNamePattern: string = '_test';

export async function activate(context: vscode.ExtensionContext): Promise<void> {
    // This is required to get server name and module. This should be
    // the first thing that we do in this extension.
    const serverInfo = loadServerDefaults();
    const serverName = serverInfo.name;
    const serverId = serverInfo.module;

    // === Generate PBT
    const generatePbtCommand = vscode.commands.registerCommand(
        `${serverId}.generatePbt`,
        async () => await getPbt(false),
    );
    context.subscriptions.push(generatePbtCommand);

    // === Generate PBT for Selected Function(s)
    const generatePbtSelectionCommand = vscode.commands.registerCommand(
        `${serverId}.generatePbtSelection`,
        async () => await getPbt(true),
    );
    context.subscriptions.push(generatePbtSelectionCommand);

    const generateExampleCommand = vscode.commands.registerCommand(`${serverId}.generateExample`, async () =>
        generateExample(),
    );
    context.subscriptions.push(generateExampleCommand);

    // === Insert Template
    const insertTemplateCommand = vscode.commands.registerCommand(
        `${serverId}.insertTemplate`,
        async () => await insertTemplate(),
    );
    context.subscriptions.push(insertTemplateCommand);

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

async function generateExample() {
    // == Prompt SUT;
    const selectedFunctions = await promptFunctionsToTest(false);

    console.log('Selected functions: ');
    console.log(selectedFunctions);

    // == Get Source
    const pbtSource = vscode.window.activeTextEditor?.document.getText();
    const pbtFilePath = vscode.window.activeTextEditor?.document.fileName;

    // == Generate PBT
    const result: any = await lsClient?.sendRequest('custom/generateExample', {
        selectedFunctions: selectedFunctions,
        pbtSource: pbtSource,
        pbtFilePath: pbtFilePath,
    });

    const isError: boolean = result.isError;
    var exampleSnippet = result.exampleSnippet;
    const line = result.line - 3;
    const column = result.column;
    const refresh = result.refresh;

    console.log('Snippet: ' + exampleSnippet);
    console.log('location: ' + [line, column]);

    if (refresh) {
        await refreshFileContents();
    }

    // == Insert snippet in the right place
    const testDocument = await vscode.workspace.openTextDocument(vscode.Uri.file(pbtFilePath as string));
    const editor = await vscode.window.showTextDocument(testDocument);
    const document: any = editor.document;
    const lastLine = document.lineAt(line);
    const endPosition = new vscode.Position(line, lastLine.range.end.character); // Adjusted position
    const selection = new vscode.Selection(endPosition, endPosition);
    await editor.insertSnippet(new vscode.SnippetString(exampleSnippet), selection);
}

async function getPbt(useSelection: boolean): Promise<void> {
    // == Prompt PBT type
    const selectedType = await promptPbtType();

    console.log('Selected type: ');
    console.log(selectedType);

    // == Prompt SUT;
    var selectedFunctions = null;
    if (!useSelection) {
        selectedFunctions = await promptFunctionsToTest(selectedType.twoFunctions);
        console.log('Selected functions: ');
        console.log(selectedFunctions);
    }

    // == Get Source
    const source = vscode.window.activeTextEditor?.document.getText();
    const filePath = vscode.window.activeTextEditor?.document.fileName;

    // == Get Selected code
    var editor2 = vscode.window.activeTextEditor;
    var selectedCode = '';
    if (editor2) {
        selectedCode = editor2.document.getText(editor2.selection);
    }

    // == Generate PBT
    const result: any = await lsClient?.sendRequest('custom/generatePBT', {
        functions: selectedFunctions,
        pbtType: selectedType,
        source: source,
        filePath: filePath,
        testFileNamePattern: testFileNamePattern,
        useSelection: useSelection,
        selectedCode: selectedCode,
    });

    console.log('RESULT: ');
    console.log(result);

    const isError: boolean = result.isError;
    var pbtSnippet = result.pbtSnippet;
    const testFileName: string = result.testFileName;
    const functionParameters = result.functionParameters;
    const pbt = result.pbt;
    const functions = result.functions;

    const customArgStrategyZip = await promptArgsCustomStrategy(functionParameters);

    const result2: any = await lsClient?.sendRequest('custom/generateSnippet', {
        pbt: pbt,
        customArgStrategyZip: customArgStrategyZip,
        functions: functions,
        useSelection: useSelection,
        selectedCode: selectedCode,
    });

    pbtSnippet = result2.pbtSnippet;

    // == Insert PBT snippet at the end of the test file
    await insertSnippetAtEndOfFile(pbtSnippet, testFileName);
}

async function insertSnippetAtEndOfFile(pbtSnippet: string, fileName: string) {
    const testDocument = await vscode.workspace.openTextDocument(vscode.Uri.file(fileName));
    const editor = await vscode.window.showTextDocument(testDocument);
    const document: any = editor.document;
    const lastLine = document.lineAt(document.lineCount - 1);
    const endPosition = new vscode.Position(document.lineCount - 1, lastLine.range.end.character); // Adjusted position
    const selection = new vscode.Selection(endPosition, endPosition);
    await editor.insertSnippet(new vscode.SnippetString(pbtSnippet), selection);
}

async function getPbtTypes(): Promise<void> {
    const result = (await lsClient?.sendRequest('custom/getPbtTypes', {})) as any;
    pbtTypes = await result.pbtTypes;
    console.log(pbtTypes);
    return;
}

async function getDefinedFunctions(source: string): Promise<[{ name: string; lineStart: number; lineEnd: number }]> {
    const response: any = await lsClient?.sendRequest('custom/getDefinedFunctionsFromFile', { source: source });
    const definedFunctions = await response.functions.map((cell: any) => {
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

async function promptArgsCustomStrategy(
    args: any,
): Promise<{ argsBooleanZip: { name: string; customStrategy: boolean }[] }> {
    var selectedArgs: any = await vscode.window.showQuickPick(
        args.map((arg: any) => {
            return {
                label: arg,
            };
        }),
        {
            title: 'Select the PBT arguments that would need a custom input generation strategy',
            placeHolder: 'Search an argument',
            canPickMany: true,
        },
    );

    var result = args.map((arg: any) => {
        return {
            name: arg,
            useCustomStrategy: selectedArgs.map((x: any) => x.label).includes(arg) ? true : false,
        };
    });

    console.log('===');
    console.log('Args: ');
    console.log(args);

    console.log('Selected: ');
    console.log(selectedArgs);

    console.log('Result: ');
    console.log(result);

    return result;
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

async function refreshFileContents() {
    const editor = vscode.window.activeTextEditor;
    if (editor) {
        const uri = editor.document.uri;
        const viewColumn = editor.viewColumn;
        await vscode.commands.executeCommand('workbench.action.closeActiveEditor');
        await vscode.workspace.openTextDocument(uri).then((newDocument) => {
            vscode.window.showTextDocument(newDocument, viewColumn);
        });
    }
}

async function insertTemplate() {
    const selectedType = await promptPbtType();
    const response: any = await lsClient?.sendRequest('custom/getTemplate', { selectedType: selectedType });
    const snippet = response.snippet;

    var currentFileName = '';
    const editor = vscode.window.activeTextEditor;
    if (editor) {
        currentFileName = editor.document.fileName;
    }

    await insertSnippetAtEndOfFile(snippet, currentFileName);
}
