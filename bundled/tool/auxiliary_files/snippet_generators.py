import ast
from auxiliary_files.import_structs import *
from auxiliary_files.other import *


def createExampleSnippet(args):
    counter = 1
    temp = ""

    for arg in args:
        temp += arg + "=${" + str(counter) + ":\"insert_value_here\"}, "
        counter += 1 

    return f"@example({temp[:-2]})"


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
            # Replace "auxiliary" with moduleName 
            if isinstance(node, ast.Name) and node.id == "auxiliary":
                node.id = moduleName

            # Remove test_identity_binary_operation_*sutName* function
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


    # Put all that in a class
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
    tempPbt += "def test_within_expected_bounds_" + functionName + "(self, "
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


    # Add auxiliary functions
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

    # Add auxiliary functions
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

