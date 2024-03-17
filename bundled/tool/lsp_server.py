# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Implementation of tool support over LSP."""
from __future__ import annotations

import copy
import json
import os
import pathlib
import re
import sys
import sysconfig
import traceback
from typing import Any, Optional, Sequence

from pbt_types import *
from auxiliary import *
import ast
import hypothesis.extra.ghostwriter as gw


# **********************************************************
# Update sys.path before importing any bundled libraries.
# **********************************************************
def update_sys_path(path_to_add: str, strategy: str) -> None:
    """Add given path to `sys.path`."""
    if path_to_add not in sys.path and os.path.isdir(path_to_add):
        if strategy == "useBundled":
            sys.path.insert(0, path_to_add)
        elif strategy == "fromEnvironment":
            sys.path.append(path_to_add)


# Ensure that we can import LSP libraries, and other bundled libraries.
update_sys_path(
    os.fspath(pathlib.Path(__file__).parent.parent / "libs"),
    os.getenv("LS_IMPORT_STRATEGY", "useBundled"),
)

# **********************************************************
# Imports needed for the language server goes below this.
# **********************************************************
# pylint: disable=wrong-import-position,import-error
import lsp_jsonrpc as jsonrpc
import lsp_utils as utils
import lsprotocol.types as lsp
from pygls import server, uris, workspace

WORKSPACE_SETTINGS = {}
GLOBAL_SETTINGS = {}
RUNNER = pathlib.Path(__file__).parent / "lsp_runner.py"

MAX_WORKERS = 5
LSP_SERVER = server.LanguageServer(
    name="EasyPBT", version="0.0.1", max_workers=MAX_WORKERS
)


# **********************************************************
# Tool specific code goes below this.
# **********************************************************

# Reference:
#  LS Protocol:
#  https://microsoft.github.io/language-server-protocol/specifications/specification-3-16/
#
#  Sample implementations:
#  Pylint: https://github.com/microsoft/vscode-pylint/blob/main/bundled/tool
#  Black: https://github.com/microsoft/vscode-black-formatter/blob/main/bundled/tool
#  isort: https://github.com/microsoft/vscode-isort/blob/main/bundled/tool

TOOL_MODULE = "easypbt"

TOOL_DISPLAY = "EasyPBT"

TOOL_NAME = ["hypothesis"]
TOOL_ARGS = ["write"]  # default arguments always passed to your tool.

# **********************************************************
# Required Language Server Initialization and Exit handlers.
# **********************************************************
@LSP_SERVER.feature(lsp.INITIALIZE)
def initialize(params: lsp.InitializeParams) -> None:
    """LSP handler for initialize request."""
    log_to_output(f"CWD Server: {os.getcwd()}")

    paths = "\r\n   ".join(sys.path)
    log_to_output(f"sys.path used to run Server:\r\n   {paths}")

    GLOBAL_SETTINGS.update(**params.initialization_options.get("globalSettings", {}))

    settings = params.initialization_options["settings"]
    _update_workspace_settings(settings)
    log_to_output(
        f"Settings used to run Server:\r\n{json.dumps(settings, indent=4, ensure_ascii=False)}\r\n"
    )
    log_to_output(
        f"Global settings:\r\n{json.dumps(GLOBAL_SETTINGS, indent=4, ensure_ascii=False)}\r\n"
    )


@LSP_SERVER.feature(lsp.EXIT)
def on_exit(_params: Optional[Any] = None) -> None:
    """Handle clean up on exit."""
    jsonrpc.shutdown_json_rpc()


@LSP_SERVER.feature(lsp.SHUTDOWN)
def on_shutdown(_params: Optional[Any] = None) -> None:
    """Handle clean up on shutdown."""
    jsonrpc.shutdown_json_rpc()


@LSP_SERVER.feature(lsp.CUSTOM_TEST_COMMAND)
def on_test_command(params: Optional[Any] = None):
    """Handles the execution of the test command"""
    return {"stdout": "this is a test response"}


@LSP_SERVER.feature(lsp.CUSTOM_GET_PBT_TYPES)
def on_get_pbt_types_command(params: Optional[Any] = None):
    """Returns a JSON-RPC response with a list of all PBT types"""
    result = {}
    result["isError"] = False
    result["pbtTypes"] = pbtTypes
    return result


@LSP_SERVER.feature(lsp.CUSTOM_GET_ALL_DEFINED_FUNCTIONS_FROM_FILE)
def on_get_all_defined_functions_from_file(params: Optional[Any] = None):
    """Returns a JSON-RPC response with a list of all defined functions from given file"""
    functions = _get_functions_from_source(params.source)
    result = {}
    result["isError"] = False
    result["functions"] = functions
    return result

@LSP_SERVER.feature(lsp.CUSTOM_GENERATE_PBT)
def on_generate_PBT(params: Optional[Any] = None):
    """Returns a JSON-RPC response with the generated PBT"""

    # === Parse parameters
    functions = params.functions
    pbtType = params.pbtType
    source = params.source
    filePath = params.filePath
    testFileNamePattern = params.testFileNamePattern

    # === Generate PBT 
    # Run ghostwriter
    fileName = os.path.basename(filePath)
    moduleName = fileName[:-3]
    # (isError, pbt) = _get_PBT(moduleName, list(map(lambda f: f.name, functions)), pbtType)
    
    sutNames = list(map(lambda f: f.name, functions))
    sutSourceList = getSutSourceList(source, sutNames)
    print("\n\nSOURCELIST: ", sutSourceList)
    (isError, pbt) = _get_PBT(sutNames, sutSourceList, pbtType, moduleName, list(map(lambda f: f.name, functions)))

    # Return error
    if isError:
        log_error("Ghostwriter error:\n" + pbt)
        result = {}
        result["isError"] = True
        result["pbt"] = pbt
        return result
    
    # Get PBT import structure
    pbtImports = makeImportStructure(pbt)

    
    # === Compute imports
    # Read test file
    testFileName = getTestFileName(fileName, testFileNamePattern)
    testFileContents = ""
    if os.path.isfile(testFileName):
        testFile = open(testFileName, "r")
        testFileContents = testFile.read()
        testFile.close()

    # Get current import structure of test file
    testFileImports = makeImportStructure(testFileContents)

    # Merge import structures
    newImports = testFileImports + pbtImports
    newTestFileContents = rewriteImports(testFileContents, newImports) + "\n\n"

    # === Write to test file
    testFile = open(testFileName, "w+")
    testFile.write(newTestFileContents)
    testFile.close()

    # === Create vscode snippet 
    snippet = replaceNothingPlaceholder(removeImports(pbt))


    # === Return result
    result = {}
    result["isError"] = False
    result["pbt"] = pbt
    result["pbtSnippet"] = snippet 
    result["testFileName"] = os.path.dirname(filePath) + "/" + testFileName
    result["functionParameters"] = getParameters(pbt)
    result["functions"] = functions

    return result

@LSP_SERVER.feature(lsp.CUSTOM_GENERATE_SNIPPET)
def on_make_snippet(params: Optional[Any] = None):
    pbt = params.pbt
    customArgStrategyZip = params.customArgStrategyZip
    functions = params.functions

    # Get functions that need strategy
    customStrategyFunctions = []
    for name, needsCustomStrategy in customArgStrategyZip:
        if needsCustomStrategy:
            customStrategyFunctions += [name]

    sutName = list(map(lambda f: f[0], functions))[0]

    strategiesString, argNames, strategiesNames = makeCustomGenerators(customArgStrategyZip, sutName)
    finalPbt = addCustomStrategyPlaceholders(removeImports(pbt), argNames, strategiesNames)
    snippet = replaceNothingPlaceholder(strategiesString + finalPbt)

    result = {}
    result["isError"] = False
    result["pbtSnippet"] = snippet 

    return result

@LSP_SERVER.feature(lsp.CUSTOM_GENERATE_EXAMPLE)
def on_make_example(params: Optional[Any]=None):
    selectedPbt = params.selectedFunction[0]
    pbtSource = params.pbtSource
    pbtFilePath = params.pbtFilePath


    # === Add example in imports

    # Read test file
    testFileName = os.path.basename(pbtFilePath)
    testFileContents = ""
    if os.path.isfile(testFileName):
        testFile = open(testFileName, "r")
        testFileContents = testFile.read()
        testFile.close()

    # Get current import structure of test file
    testFileImports = makeImportStructure(testFileContents)

    alreadyHasExampleImport = testFileImports.containsName("hypothesis", "example")

    if not alreadyHasExampleImport:
        # Create import structure for example
        exampleImport = makeImportStructure("from hypothesis import example")

        # Merge import structures
        newImports = testFileImports + exampleImport
        newTestFileContents = rewriteImports(testFileContents, newImports) + "\n\n"

        # Write to test file
        testFile = open(testFileName, "w")
        testFile.write(newTestFileContents)
        testFile.close()

    # === Get PBT
    pbtName = selectedPbt.name.split(".")[::-1][0]
    pbt, line, col = fishOutPbt(pbtSource, pbtName)

    # === Parse out arguments
    # from @given 
    args = getArgsFromPbt(pbt)
    print("ARGS: ", args)

    # === Create @example() snippet
    snippet = "\n" + createExampleSnippet(args)

    # === Return snippet and paste location
    result = {}
    result["isError"] = False
    result["exampleSnippet"] = snippet 
    result["line"] = line + 1
    result["column"] = col
    result["refresh"] = not alreadyHasExampleImport

    return result



def _get_global_defaults():
    return {
        "path": GLOBAL_SETTINGS.get("path", []),
        "interpreter": GLOBAL_SETTINGS.get("interpreter", [sys.executable]),
        "args": GLOBAL_SETTINGS.get("args", []),
        "importStrategy": GLOBAL_SETTINGS.get("importStrategy", "useBundled"),
        "showNotifications": GLOBAL_SETTINGS.get("showNotifications", "off"),
        "testFileNamePattern":  GLOBAL_SETTINGS.get("testFileNamePattern", "_test"),
    }


def _update_workspace_settings(settings):
    if not settings:
        key = os.getcwd()
        WORKSPACE_SETTINGS[key] = {
            "cwd": key,
            "workspaceFS": key,
            "workspace": uris.from_fs_path(key),
            **_get_global_defaults(),
        }
        return

    for setting in settings:
        key = uris.to_fs_path(setting["workspace"])
        WORKSPACE_SETTINGS[key] = {
            "cwd": key,
            **setting,
            "workspaceFS": key,
        }


def _get_settings_by_path(file_path: pathlib.Path):
    workspaces = {s["workspaceFS"] for s in WORKSPACE_SETTINGS.values()}

    while file_path != file_path.parent:
        str_file_path = str(file_path)
        if str_file_path in workspaces:
            return WORKSPACE_SETTINGS[str_file_path]
        file_path = file_path.parent

    setting_values = list(WORKSPACE_SETTINGS.values())
    return setting_values[0]


def _get_document_key(document: workspace.Document):
    if WORKSPACE_SETTINGS:
        document_workspace = pathlib.Path(document.path)
        workspaces = {s["workspaceFS"] for s in WORKSPACE_SETTINGS.values()}

        # Find workspace settings for the given file.
        while document_workspace != document_workspace.parent:
            if str(document_workspace) in workspaces:
                return str(document_workspace)
            document_workspace = document_workspace.parent

    return None


def _get_settings_by_document(document: workspace.Document | None):
    if document is None or document.path is None:
        return list(WORKSPACE_SETTINGS.values())[0]

    key = _get_document_key(document)
    if key is None:
        # This is either a non-workspace file or there is no workspace.
        key = os.fspath(pathlib.Path(document.path).parent)
        return {
            "cwd": key,
            "workspaceFS": key,
            "workspace": uris.from_fs_path(key),
            **_get_global_defaults(),
        }

    return WORKSPACE_SETTINGS[str(key)]


# *****************************************************
# Internal execution APIs.
# *****************************************************

def getPbtUsingCli(moduleName, functionNames, pbtType = "") -> utils.RunResult:
    """Runs Hypothesis' ghostwriter and sends the output back to the client
    Returns: (ISeRROR, PBT | ERROR)"""

    # === Create command
    argv = TOOL_NAME + TOOL_ARGS # e.g. ["hypothesis", "write"]

    # Add PBT type (if applicable)
    if pbtType != "":
        argv += [pbtType] # adds e.g. '--roundtrip'

    # Add all functions to test
    for f in functionNames:
        argv += [moduleName + "." + f]

    print("COMMAND: " + str(argv))

    # === Run the command
    settings = copy.deepcopy(_get_settings_by_document(None))
    cwd = settings["workspaceFS"]
    result = utils.run_path(argv=argv, use_stdin=True, cwd=cwd)

    # === Check for error/output
    pbt = result.stdout
    error = result.stderr
    isError = False

    if error:
        log_error(error)
        isError = True

    log_to_output(f"\r\n{pbt}\r\n")

    return (isError, pbt if not isError else error)


def _get_PBT(sutNames, sutSourceList, pbtType, moduleName, functionNames):
    """Runs Hypothesis' ghostwriter and sends the output back to the client"""

    # === Create function objects
    # ghostwriter module only works with evaluated functions
    # ghostwriter cli only works with source strings (what we are currently working with)
    evaluatedSouceList = getEvaluatedSouceList(sutNames, sutSourceList)

    # === Generate PBT
    pbt = ""
    isError = False

    print("\n\n\n===TypeId", pbtType.typeId)

    match pbtType.typeId:

        ### == Supported by Hypothesis Ghostwriter
        case PbtTypeId.DIFF_PATH_SAME_DEST.value: # binary_operation (with only associativity enabled)
            temp = gw.binary_operation(*evaluatedSouceList, commutative=True, identity=False, associative=False)
            pbt = processDiffPathSameDest(temp, moduleName, functionNames[0])
            pass

        case PbtTypeId.ROUNDTRIP.value: # roundtrip
            isError, pbt = getPbtUsingCli(moduleName, functionNames, pbtType.argument)
            pass

        case PbtTypeId.TEST_ORACLE.value: # equivalent
            isError, pbt = getPbtUsingCli(moduleName, functionNames, pbtType.argument)
            pass

        case PbtTypeId.MODEL_BASED.value: # equivalent
            isError, pbt = getPbtUsingCli(moduleName, functionNames, pbtType.argument)
            pass

        case PbtTypeId.THE_MORE_THINGS_CHANGE.value: # idempotent
            isError, pbt = getPbtUsingCli(moduleName, functionNames, pbtType.argument)
            pass

        ### == Partially supported by Hypothesis Ghostwriter
        case PbtTypeId.SOME_THINGS_NEVER_CHANGE.value: # Based on idempotent (input mustn't be changed)
            pbt = makeSomeThingsNeverChangeSnippet(sutSourceList[0], moduleName, functionNames[0])
            pass

        case PbtTypeId.METAMORPHIC_PROP.value: # Based on equivalent (add extra step to test e.g. compiler output instead of compiler itself)
            pbt = makeMetamorphicPropertySnippet(sutSourceList[0], moduleName, functionNames[0], functionNames[1])
            pass

        ### == Not supported by Hypothesis Ghostwriter
        case PbtTypeId.SOLVE_SMALLER_PROBLEM_FIRST.value: # 
            pbt = makeSolveSmallerProblemFirstSnippet(sutSourceList[0], moduleName, functionNames[0])
            pass

        case PbtTypeId.HARD_TO_PROVE.value: # add dummy strategy and dummy checker predicate
            pbt = makeHardToProveEasyToVerifySnippet(sutSourceList[0], moduleName, functionNames[0], functionNames[1])
            pass

        case PbtTypeId.WITHIN_EXPECTED_BOUNDS.value: # add bounds assertions
            pbt = makeWithinExpectedBoundsSnippet(sutSourceList[0], moduleName, functionNames[0])
            pass

        case PbtTypeId.UNKNOWN.value: # magic
            isError, pbt = getPbtUsingCli(moduleName, functionNames, pbtType.argument)
            pass

    if isError:
        isError = True
        log_error(pbt)
    else:
        log_to_output(f"\r\n{pbt}\r\n")

    print("\n\nRESULTING PBT: ")
    print(pbt)
    return isError, pbt


def _get_functions_from_source(source: str):
    tree = ast.parse(source)
    functions = {}

    # Iteration through all nodes of class node
    def getClassMethods(classNode: ast.ClassDef):
        for node in ast.walk(classNode):
           if isinstance(node, ast.FunctionDef):
            fullName = classNode.name + "." + node.name
            functions[fullName] = {"name": classNode.name + "." + node.name, "lineStart": node.lineno, "lineEnd": node.end_lineno, "class": classNode.name, "method": node.name}

    # Checks if function already added (because it's a method)
    def isAlreadyDefined(line):
        for f in functions.values():
            if f["lineStart"] == line:
                return True
        return False

    # Iteration through all tree nodes
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            getClassMethods(node)
            continue
        if isinstance(node, ast.FunctionDef):
            if not isAlreadyDefined(node.lineno):
                functions[node.name] = {"name": node.name, "lineStart": node.lineno, "lineEnd": node.end_lineno, "class": "", "method": ""}

    return list(functions.values())


# *****************************************************
# Logging and notification.
# *****************************************************
def log_to_output(
    message: str, msg_type: lsp.MessageType = lsp.MessageType.Log
) -> None:
    LSP_SERVER.show_message_log(message, msg_type)


def log_error(message: str) -> None:
    LSP_SERVER.show_message_log(message, lsp.MessageType.Error)
    if os.getenv("LS_SHOW_NOTIFICATION", "off") in ["onError", "onWarning", "always"]:
        LSP_SERVER.show_message(message, lsp.MessageType.Error)


def log_warning(message: str) -> None:
    LSP_SERVER.show_message_log(message, lsp.MessageType.Warning)
    if os.getenv("LS_SHOW_NOTIFICATION", "off") in ["onWarning", "always"]:
        LSP_SERVER.show_message(message, lsp.MessageType.Warning)


def log_always(message: str) -> None:
    LSP_SERVER.show_message_log(message, lsp.MessageType.Info)
    if os.getenv("LS_SHOW_NOTIFICATION", "off") in ["always"]:
        LSP_SERVER.show_message(message, lsp.MessageType.Info)


# *****************************************************
# Start the server.
# *****************************************************
if __name__ == "__main__":
    LSP_SERVER.start_io()
