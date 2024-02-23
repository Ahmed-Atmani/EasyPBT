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

from pbt_types import pbtTypes
import ast


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
    functions = params.functions
    pbtType = params.pbtType

    dirName = "easypbt"
    moduleName = "temp_functions"
    fileName = dirName + "/" + moduleName + ".py"
    
    # # Check if folder exists
    if not os.path.isdir(dirName):
        os.mkdir(dirName)

    # Save functions in temporary file
    f = open(fileName, "a")
    for func in functions:
        f.write(func + "\n")
    f.close()

    # Get PBT
    functionNames = ["encode", "decode"] # needs to be parsed using AST
    result = _get_PBT(dirName + "." + moduleName, functionNames, pbtType)

    # Delete temporary file
    os.remove(fileName)

    return result


@LSP_SERVER.feature(lsp.CUSTOM_GET_PBT_TYPES)
def on_get_pbt_types_command(params: Optional[Any] = None):
    """Returns a JSON-RPC response with a list of all PBT types"""
    return utils.RunResult(pbtTypes, "")


@LSP_SERVER.feature(lsp.CUSTOM_GET_ALL_DEFINED_FUNCTIONS_FROM_FILE)
def on_get_all_defined_functions_from_file(params: Optional[Any] = None):
    """Returns a JSON-RPC response with a list of all defined functions from given file"""
    return utils.RunResult(_get_functions_from_source(params.source), "")

@LSP_SERVER.feature(lsp.CUSTOM_GENERATE_PBT)
def on_generate_PBT(params: Optional[Any] = None):
    """Returns a JSON-RPC response with the generated PBT"""
    # === Parse parameters
    functions = params.functions
    pbtType = params.pbtType.argument
    source = params.source

    # === Write functions to temporary file (hypothesis' ghostwriter only works on python modules)
    moduleName = "temp_functions"
    fileName = moduleName + ".py"

    # TODO: Check if file is saved
    # not saved => append PBT under SUT
    # saved? => check if test file exists (based on settings)
    #   exists? => append to file and check imports
    #   not exist? => create it and append tests there

    # Save source in temporary file
    f = open(fileName, "w")
    f.write(source)
    f.close()

    # === Generate PBT 
    result = _get_PBT(moduleName, list(map(lambda f: f.name, functions)), pbtType)
    
    if result.stderr != '':
        log_error("Ghostwriter error:\n" + result.stderr)

    

    # === Delete temporary file
    os.remove(fileName)

    return result


def _get_global_defaults():
    return {
        "path": GLOBAL_SETTINGS.get("path", []),
        "interpreter": GLOBAL_SETTINGS.get("interpreter", [sys.executable]),
        "args": GLOBAL_SETTINGS.get("args", []),
        "importStrategy": GLOBAL_SETTINGS.get("importStrategy", "useBundled"),
        "showNotifications": GLOBAL_SETTINGS.get("showNotifications", "off"),
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
def _get_PBT(moduleName, functionNames, pbtType = "") -> utils.RunResult:
    """Runs Hypothesis' ghostwriter and sends the output back to the client (based on _run_tool)"""
    argv = TOOL_NAME + TOOL_ARGS # e.g. ["hypothesis", "write"]

    # Add PBT type (if applicable)
    if pbtType != "":
        argv += [pbtType] # adds e.g. '--roundtrip'

    # Add all functions to test
    for f in functionNames:
        argv += [moduleName + "." + f]

    # Run the command
    settings = copy.deepcopy(_get_settings_by_document(None))
    cwd = settings["workspaceFS"]
    result = utils.run_path(argv=argv, use_stdin=True, cwd=cwd)

    # Log errors and output
    if result.stderr:
        log_error(result.stderr)

    log_to_output(f"\r\n{result.stdout}\r\n")

    return result


def _get_functions_from_source(source: str):
    tree = ast.parse(source)
    functions = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            functions += [{"name": node.name, "lineStart": node.lineno, "lineEnd": node.end_lineno}]

    return functions

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
