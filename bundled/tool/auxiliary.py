import ast
import re
from supported_strategies import supportedStrategies

class MaybeAlias:
    def __init__(self, name, alias = None) -> None:
        self.str = name
        self.alias = alias

    def hasAlias(self):
        return self.alias != None
    
    def __str__(self) -> str:
        if self.alias:
            return self.str + " as " + self.alias
        return self.str


class ImportEntry:
    def __init__(self, module: MaybeAlias, names: list[MaybeAlias] = [], importNameSpace = False) -> None:
        self.module = module
        self.names = names
        self.importNameSpace = importNameSpace
        self.saturated = True if "*" in list(map(lambda n: n.str, names)) else False

    def _isSameModule(self, other):
        return self.module.str == other.module.str

    def hasName(self, name: MaybeAlias):
        return name.str in list(map(lambda name: name.str, self.names))

    def addName(self, name: MaybeAlias):
        if not self.hasName(name):
            self.names += [name]

    def addNames(self, names: list[MaybeAlias]):
        for name in names:
            self.addName(name)

    def __add__(self, other):
        temp = ImportEntry(self.module, self.names, self.importNameSpace)
        temp.addNames(other.names)
        return temp
    
    def __str__(self) -> str:
        string = self.module.str + ("[+]" if self.importNameSpace else "") + ": "

        for name in self.names:
            string += "\n\t" + name.str

        return string
    
    def __eq__(self, __value: object) -> bool:
        return self.module.str == __value.module.str

        

        
class ImportStructure:
    def __init__(self) -> None:
        self.structure: dict[str: ImportEntry] = {}
        self.substitutions: dict[str: str] = {}

    def _isModuleInStructure(self, entry: ImportEntry):
        return entry.module.str in self.structure.keys()

    def addEntry(self, entry: ImportEntry):
        if self._isModuleInStructure(entry):
            self.structure[entry.module.str] += entry
        else:
            self.structure[entry.module.str] = entry

    def addEntries(self, entries: list[ImportEntry]):
        for e in entries:
            self.addEntry(e)
    
    def getEntries(self):
        return self.structure.values()

    def toSource(self):
        string = ""

        for entry in self.structure.values():
            if entry.importNameSpace:
                string += f"import {entry.module}\n"
            
            if entry.saturated:
                string += f"from {entry.module} import *\n"
                continue
                
            if entry.names:
                string += f"from {entry.module} import "
                for name in entry.names:
                    string += name.str

                    if name.hasAlias():
                        string += " as " + name.alias

                    string += ", "
                string = string[:-2] # removes last comma
                string += "\n"
                
        
        return string
    
    def __add__(self, other): 
        temp = ImportStructure()
        temp.addEntries(self.getEntries())
        temp.addEntries(other.getEntries())
        return temp


    def __str__(self) -> str:
        string = ""

        for entry in self.structure.values():
            string += str(entry) + "\n"
        
        return string
    

def rewriteImports(source, newStructure: ImportStructure):
    sourceWOimports = removeImports(source)
    imports = newStructure.toSource() + "\n"
    imports += "# This test code was written by the `hypothesis.extra.ghostwriter` module\n# and is provided under the Creative Commons Zero public domain dedication\n\n\n"
    return imports + sourceWOimports

def removeImports(source: str):
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
            tree.body.remove(node)
    return ast.unparse(tree)    

def removeComments(source: str):
    return ast.unparse(ast.parse(source))

def replaceNothingPlaceholder(pbt: str):
    i = 1

    def makeStrategyPlaceholder():
        nonlocal i
        temp = "${" + str(i) + "|"
        for strat in supportedStrategies.values():
            temp += strat + ","
        temp = temp[:-1]
        temp += "|}"
        i += 1
        return temp
    
    def replace(match):
        return makeStrategyPlaceholder()

    return re.sub(r"st\.nothing\(\)", replace, pbt) + "\n\n"

def makeImportStructure(source: str) -> ImportStructure:
    """Returns the import structure of a Python source file"""

    if not source:
        return ImportStructure()

    tree = ast.parse(source)
    structure = ImportStructure()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            _addImportNodeToStructure(structure, node)
        if isinstance(node, ast.ImportFrom):
            _addImportFromNodeToStructure(structure, node)

    return structure


def _addImportFromNodeToStructure(struct: ImportStructure, node: ast.ImportFrom):
    struct.addEntry(_makeImportFromEntry(node))

def _addImportNodeToStructure(struct: ImportStructure, node: ast.Import):
    struct.addEntries(_makeImportEntries(node))

def _makeImportFromEntry(node: ast.ImportFrom):
    module = MaybeAlias(node.module)
    names = list(map(lambda name: MaybeAlias(name.name, name.asname), node.names))
    return ImportEntry(module, names)

def _makeImportEntries(node: ast.Import):
    modules = list(map(lambda name: MaybeAlias(name.name, name.asname), node.names))
    entries = list(map(lambda module: ImportEntry(module, importNameSpace=True), modules))
    return entries

def getTestFileName(fileName, pattern):
    result = fileName[0 : -3] # removes the .py suffix
    result += pattern
    result += ".py"
    return result


def split_generated_code(pbt):
    """Splits code generated by hypothesis into imports and the actual PBT"""
    
    tree = ast.parse(pbt)
    importNodes = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
            importNodes += [ast.unparse(node)]
            tree.body.remove(node)

    return (ast.unparse(tree), importNodes)

def getParameters(pbt):
    tree = ast.parse(pbt)

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            temp = list(map(lambda x: x.arg, node.args.posonlyargs + node.args.args))
            temp.remove("self") # Should stay in case the SUT is a class method
            return temp

# def makeCustomGenerators(customStrategyFunctions, sutName):
#     def createCustomStrategy(argName):
#         strategyName = "strategyFor_" + argName + "_in_" + sutName
#         strategy = "def " + strategyName + "():\n\t"
#         strategy += "return st.nothing()\n\n"
#         return strategy, strategyName

#     strategiesString = ""
#     strategiesNames = []
#     for function in customStrategyFunctions:
#         strategy, name = createCustomStrategy(function)
#         strategiesString += strategy
#         strategiesNames += name
    

#     return strategiesString, strategiesNames

def makeCustomGenerators(customArgStrategyZip, sutName):
    def createCustomStrategy(argName):
        strategyName = "strategyFor_" + argName + "_in_" + sutName
        strategy = "def " + strategyName + "():\n\t"
        strategy += "return st.nothing()\n\n"
        return strategy, strategyName

    strategiesString = "" # source of all strategies combined
    strategiesNames = [] # name of custom strategy function
    argNames = [] # names of args

    for name, makeCustomStrategy in customArgStrategyZip:
        argNames += [name]
        if makeCustomStrategy:
            strategySource, strategyName = createCustomStrategy(name)
            strategiesString += strategySource
            strategiesNames += [strategyName]
        else:
            strategiesNames += ["st.nothing"]

    print("\n")
    print(customArgStrategyZip)
    print(argNames)
    print(strategiesNames)


    return strategiesString, argNames, strategiesNames

def addCustomStrategyPlaceholders(pbt, argNames, strategiesNames):
    tree = ast.parse(pbt)

    def makeStrategyCall(strategy):
        return ast.Call(func=ast.Name(id=strategy, ctx=ast.Load()), args=[], keywords=[])

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "st" and node.func.attr == "nothing":
                node.func = makeStrategyCall(strategiesNames[0]).func
                strategiesNames = strategiesNames[1:]

    return ast.unparse(tree)
            



# Test expression
expr = """import ast
from math import pi


def dummyFunction():
    pass

def sortingAlgorithm(lst: list[int]) -> list[int]:
    return sorted(lst)

x = 10
y = 20

# Test comment

def dummyFunction2():
    pass
    """

expr2 = """import ast
from math import sqr

x = 10
y = 20"""

expr3 = """from ast import walk
import math

x = 50"""

expr4 = """from math import *
x = 50"""

noTypePbtExample = """# This test code was written by the `hypothesis.extra.ghostwriter` module
# and is provided under the Creative Commons Zero public domain dedication. 
import sample 
import unittest 
from hypothesis import given, strategies as st 

# TODO: replace st.nothing() with an appropriate strategy 
class TestIdempotentFac(unittest.TestCase): 
    @given(n=st.nothing()) 
    def test_idempotent_fac(self, n): 
        result = sample.fac(n=n) 
        repeat = sample.fac(n=result) 
        self.assertEqual(result, repeat)"""

# DEBUG

# w = makeImportStructure(expr)
# x = makeImportStructure(expr2)
# y = makeImportStructure(expr3)
# z = makeImportStructure(expr4)

# print(w)
# print("---")
# a = w + x
# print(a)
# print("---")
# b = a + y
# print(b)
# print("---")
# c = b + z
# print(c)

