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
    
    def containsName(self, module: str, name: str) -> bool:
        for entry in self.getEntries():
            if entry.module.str == module:
                return entry.hasName(MaybeAlias(name=name))
                
        return False

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
        temp.addEntries([ImportEntry(entry.module, entry.names, entry.importNameSpace) for entry in self.getEntries()])
        temp.addEntries([ImportEntry(entry.module, entry.names, entry.importNameSpace) for entry in other.getEntries()])
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
            if node in tree.body:
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

    result = re.sub(r"st\.nothing\(\)", replace, pbt) + "\n\n"
    result = result.replace("'", "")
    return result

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

def fishOutPbt(pbtSource, selectedPbtName):
    tree = ast.parse(pbtSource)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == selectedPbtName:
            return (ast.unparse(node), node.lineno, node.col_offset)
    
    return (None, None, None)

def getArgsFromPbt(pbt):
    def getGivenNode(tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and node.func.id == "given":
                # print("func: ", node.func, " ## ", "keywords: ", node.keywords, " ## " "args: ", node.args, " ## " "type: ", type(node))
                return node
    
    tree = ast.parse(pbt)
    givenNode = getGivenNode(tree)
    args = list(map(lambda keyword: keyword.arg, givenNode.keywords))

    return args

def getArgsFromSut(sut):
    def getFunctionNode(tree):
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # print("func: ", node.func, " ## ", "keywords: ", node.keywords, " ## " "args: ", node.args, " ## " "type: ", type(node))
                return node
    
    tree = ast.parse(sut)
    functionNode = getFunctionNode(tree)
    args = list(map(lambda arg: arg.arg, functionNode.args.args))

    return args

def createExampleSnippet(args):
    counter = 1
    temp = ""

    for arg in args:
        temp += arg + "=${" + str(counter) + ":\"insert_value_here\"}, "
        counter += 1 

    return f"@example({temp[:-2]})"

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
            if "self" in temp:
                temp.remove("self") # Should stay in case the SUT is a class method
            return temp

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
                if strategiesNames == []:
                    break

    return ast.unparse(tree)
            

def getSutSourceList(source: str, sutNames: list[str]):
    tree = ast.parse(source)
    result = []

    def isClassMethod(name: str):
        return '.' in name
    
    def lookupFunction(tree, funcName):
        nonlocal result
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if node.name == funcName:
                    result += [ast.unparse(node)]
                    return

    def lookupClass(tree, className, methodName):
        nonlocal result
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if node.name == className:
                    # return lookupFunction(node, methodName) # This line returns the method, not the entire class
                    result += [ast.unparse(node)]
                    return

    for sut in sutNames:
        if isClassMethod(sut):
            (className, methodName) = sut.split('.')
            lookupClass(tree, className, methodName)
        else:
            lookupFunction(tree, sut)

    return result
        
def getEvaluatedSouceList(sutNames, sutSourceList):
    # Make copy of environment and evaluate the source
    env = globals().copy()
    fullSource = "\n".join(sutSourceList)
    exec(fullSource, env)
    
    # Put all evaluated functions in a list
    result = []
    for name in sutNames:
        result += [env[name]]

    return result


def processDiffPathSameDest(pbt, moduleName, functionName):
    nameOfFuncToRemove = "test_identity_binary_operation_" + functionName
    tempImports = ""

    tree = ast.parse(pbt)
    for node in ast.walk(tree):
        # Fish out imports
        if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
            tempImports += ast.unparse(node) + "\n"
            tree.body.remove(node)
        else:
            # TODO: Replace "auxiliary" with moduleName 
            if isinstance(node, ast.Name) and node.id == "auxiliary":
                node.id = moduleName

            # TODO: Remove test_identity_binary_operation_*sutName* function
            if isinstance(node, ast.FunctionDef) and node.name == nameOfFuncToRemove:
                tree.body.remove(node)

            # Add "self" arg to pbt
            elif isinstance(node, ast.FunctionDef):
                test = ast.arg()
                test.arg = "self"
                node.args.args = [test] + node.args.args
    
    # make import structure
    importStruct = makeImportStructure(tempImports)
    for entry in importStruct.getEntries():
        if entry.module.str == "auxiliary":
            entry.module.str = moduleName
    
    newImports = importStruct.toSource() + "\n"


    # TODO: Put all that in a class
    tempPbt = ast.unparse(tree)
    tempPbtWithClass = []
    className = "TestDifferentPathSameDestination" + functionName.capitalize()
    tempPbtWithClass += ["class " + className + "(unittest.TestCase):\n"]

    # Add indented content
    for i in tempPbt.split("\n"):
        tempPbtWithClass += ["\t" + i]

    result = newImports
    result += "\n".join(tempPbtWithClass)


    return result
    

def makeWithinExpectedBoundsSnippet(source, moduleName, functionName):
    # Add imports
    tempPbt = "import unittest\nfrom hypothesis import given, strategies as st\nimport " + moduleName + "\n\n"

    # Add wrapper class
    className = "TestWithinExpectedBounds" + functionName.capitalize()
    tempPbt += "class " + className + "(unittest.TestCase):\n\n\t"

    # Add @given decorator
    tempPbt += "@given("
    args = getArgsFromSut(source)
    for arg in args:
        tempPbt += arg + "=st.nothing(), "
    tempPbt = tempPbt[:-2]
    tempPbt += ")\n\t"

    # Add pbt
    tempPbt += "def test_within_expected_bounds_" + functionName + "("
    for arg in args:
        tempPbt += arg + ", "
    tempPbt = tempPbt[:-2]
    tempPbt += "):\n\t\t"

    argCounter = len(args) + 1
    tempPbt += "lowerBound, upperBound = '${" + str(argCounter) + ":lowerBound}', '${"
    argCounter += 1
    tempPbt +=  str(argCounter) + ":upperBound}'\n\t\t"

    tempPbt += "output = " + moduleName + "." + functionName + "("
    for arg in args:
        tempPbt += arg + "=" + arg + ", "
    tempPbt = tempPbt[:-2]
    tempPbt += ")\n\t\t"

    tempPbt += "assert lowerBound <= output and output <= upperBound\n"

    return tempPbt


def makeSomeThingsNeverChangeSnippet(source, moduleName, functionName):
    # Add imports
    tempPbt = "import unittest\nfrom hypothesis import given, strategies as st\nimport " + moduleName + "\n\n"

    # Add wrapper class
    className = "TestSomeThingsNeverChange" + functionName.capitalize()
    tempPbt += "class " + className + "(unittest.TestCase):\n\n\t"

    # Add @given decorator
    tempPbt += "@given("
    args = getArgsFromSut(source)
    for arg in args:
        tempPbt += arg + "=st.nothing(), "
    tempPbt = tempPbt[:-2]
    tempPbt += ")\n\t"

    # Add pbt
    tempPbt += "def test_some_things_never_change_" + functionName + "("
    for arg in args:
        tempPbt += arg + ", "
    tempPbt = tempPbt[:-2]
    tempPbt += "):\n\t\t"

    tempPbt += "output = " + moduleName + "." + functionName + "("
    for arg in args:
        tempPbt += arg + "=" + arg + ", "
    tempPbt = tempPbt[:-2]
    tempPbt += ")\n\t\t"

    tempPbt += "assert ("
    for arg in args:
        tempPbt += arg + ", "
    tempPbt = tempPbt[:-2]
    tempPbt += ") == output\n"

    return tempPbt

def makeHardToProveEasyToVerifySnippet(sutSource, moduleName, sutName, testerName):
    # Add imports
    tempPbt = "import unittest\nfrom hypothesis import given, strategies as st\nimport " + moduleName + "\n\n"

    # Add wrapper class
    className = "TestHardToProveEasyToVerify" + sutName.capitalize()
    tempPbt += "class " + className + "(unittest.TestCase):\n\n\t"

    # Add @given decorator
    tempPbt += "@given("
    args = getArgsFromSut(sutSource)
    for arg in args:
        tempPbt += arg + "=st.nothing(), "
    tempPbt = tempPbt[:-2]
    tempPbt += ")\n\t"

    # Add pbt
    tempPbt += "def test_hard_to_prove_easy_to_verify_" + sutName + "("
    for arg in args:
        tempPbt += arg + ", "
    tempPbt = tempPbt[:-2]
    tempPbt += "):\n\t\t"

    tempPbt += "output = " + moduleName + "." + sutName + "("
    for arg in args:
        tempPbt += arg + "=" + arg + ", "
    tempPbt = tempPbt[:-2]
    tempPbt += ")\n\t\t"

    tempPbt += "assert " + moduleName + "." + testerName + "(output) == True\n"

    return tempPbt
    
def makeSolveSmallerProblemFirstSnippet(sutSource, moduleName, functionName):
    # Add imports
    tempPbt = "import unittest\nfrom hypothesis import given, strategies as st\nimport " + moduleName + "\n\n"

    # Add wrapper class
    className = "TestSolveSmallerProblemFirst" + functionName.capitalize()
    tempPbt += "class " + className + "(unittest.TestCase):\n\n\t"


    ### TODO: ADD aux funcs
    tempPbt += "def isCorrect(self, element):\n\t\t"
    args = getArgsFromSut(sutSource)
    counter = len(args) + 1
    tempPbt += "'${" + str(counter) + ":enter code here to test an element}'\n\t\tpass\n\t\n\t"
    counter += 1

    tempPbt += "def isDone(self, element):\n\t\t"
    tempPbt += "'${" + str(counter) + ":enter code here that returns True if the element is empty}'\n\t\tpass\n\t\n\t"
    counter += 1

    tempPbt += "def getNextElement(self, element):\n\t\t"
    tempPbt += "'${" + str(counter) + ":enter code here that returns the next element}'\n\t\tpass\n\t\n\t"
    counter += 1

    # Add @given decorator
    tempPbt += "@given("
    args = getArgsFromSut(sutSource)
    for arg in args:
        tempPbt += arg + "=st.nothing(), "
    tempPbt = tempPbt[:-2]
    tempPbt += ")\n\t"

    # Add pbt
    tempPbt += "def test_solve_smaller_problem_first_" + functionName + "(self, "
    for arg in args:
        tempPbt += arg + ", "
    tempPbt = tempPbt[:-2]
    tempPbt += "):\n\t\t"

    tempPbt += "output = " + moduleName + "." + functionName + "("
    for arg in args:
        tempPbt += arg + "=" + arg + ", "
    tempPbt = tempPbt[:-2]
    tempPbt += ")\n\t\t\n\t\t"

    tempPbt += "currentElement = output\n\t\t"
    tempPbt += "while not self.isDone(currentElement):\n\t\t\t"
    tempPbt += "assert self.isCorrect(currentElement)\n\t\t\t"
    tempPbt += "currentElement = self.getNextElement(currentElement)\n"

    return tempPbt

def makeMetamorphicPropertySnippet(sutSource, moduleName, sutName, testerName):
    # Add imports
    tempPbt = "import unittest\nfrom hypothesis import given, strategies as st\nimport " + moduleName + "\n\n"

    # Add wrapper class
    className = "TestMetamorphicProperty" + sutName.capitalize()
    tempPbt += "class " + className + "(unittest.TestCase):\n\n\t"

    ### TODO: ADD aux funcs
    tempPbt += "def testMetamorphicProperty(self, sutOutput, oracleOutput, extraArg):\n\t\t"
    args = getArgsFromSut(sutSource) + ["extraArg"]
    counter = len(args) + 1
    tempPbt += '"""Compare the outputs based on the metamorphic property"""\n\t\t'
    tempPbt += "return '${" + str(counter) + ":sutOutput(extraArg) == oracleOutput(extraArg)}'\n\t\n\t"
    counter += 1

    # Add @given decorator
    tempPbt += "@given("
    args = getArgsFromSut(sutSource) + ["extraArg"]
    for arg in args:
        tempPbt += arg + "=st.nothing(), "
    tempPbt = tempPbt[:-2]
    tempPbt += ")\n\t"

    # Add pbt
    tempPbt += "def test_metamorphic_property_" + sutName + "(self, "
    for arg in args:
        tempPbt += arg + ", "
    tempPbt = tempPbt[:-2]
    tempPbt += "):\n\t\t"

    args = getArgsFromSut(sutSource)
    tempPbt += "sutOutput = " + moduleName + "." + sutName + "("
    for arg in args:
        tempPbt += arg + "=" + arg + ", "
    tempPbt = tempPbt[:-2]
    tempPbt += ")\n\t\t"

    tempPbt += "oracleOutput = " + moduleName + "." + testerName + "("
    for arg in args:
        tempPbt += arg + "=" + arg + ", "
    tempPbt = tempPbt[:-2]
    tempPbt += ")\n\n\t\t"

    tempPbt += '\'"""Adding arguments should also be added to the @given decorator, this function and isCorrect"""\'\n\t\t'
    tempPbt += "extraArguments = [extraArg]\n\t\t"
    tempPbt += "isCorrect = self.testMetamorphicProperty(sutOutput, oracleOutput, *extraArguments)\n\n\t\t"
    
    tempPbt += "assert isCorrect == True\n"

    return tempPbt


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

