from enum import Enum

class PbtTypeId(Enum):
    DIFF_PATH_SAME_DEST = 0
    ROUNDTRIP = 1
    SOME_THINGS_NEVER_CHANGE = 2
    THE_MORE_THINGS_CHANGE = 3
    SOLVE_SMALLER_PROBLEM_FIRST = 4
    HARD_TO_PROVE = 5
    TEST_ORACLE = 6
    MODEL_BASED = 7
    WITHIN_EXPECTED_BOUNDS = 8
    METAMORPHIC_PROP = 9
    UNKNOWN = 10


pbtTypes = [
    {
        "typeId": PbtTypeId.DIFF_PATH_SAME_DEST,
        "name": 'Different Paths, Same Destination',
        "description": 'Tests the associativity of a function [e.g. add(2, 3) == add(3, 2)]',
        "argument": '--equivalent',
        "twoFunctions": False
    },
    {
        "typeId": PbtTypeId.ROUNDTRIP,
        "name": 'Roundtrip',
        "description": 'Tests a function and its inverse [e.g. decode(encode("msg")) == "msg"]',
        "argument": '--roundtrip',
        "twoFunctions": True
    },
    {
        "typeId": PbtTypeId.SOME_THINGS_NEVER_CHANGE,
        "name": 'Some Things Never Change',
        "description": 'Tests the idempotence of a function [e.g. abs(5) == 5]',
        "argument": '--idempotent',
        "twoFunctions": False
    },
    {
        "typeId": PbtTypeId.THE_MORE_THINGS_CHANGE,
        "name": 'The More Things Change, the More They Stay the Same',
        "description": 'Tests the idempotence of a function after one call [e.g. sorted(sorted(list))) == sorted(list)]',
        "argument": '--idempotent',
        "twoFunctions": False
    },
    {
        "typeId": PbtTypeId.SOLVE_SMALLER_PROBLEM_FIRST,
        "name": 'Solve a Smaller Problem First',
        "description": 'Tests the smaller parts of a data structure [e.g. test(list[0]); test(list[1]); ...]',
        "argument": '',
        "twoFunctions": False
    },
    {
        "typeId": PbtTypeId.HARD_TO_PROVE,
        "name": 'Hard to Prove, Easy to Verify',
        "description": 'Tests the output of a function using a predefined predicate [e.g. isCorrect(solution)]',
        "argument": '--equivalent',
        "twoFunctions": True
    },
    {
        "typeId": PbtTypeId.TEST_ORACLE,
        "name": 'The Test oracle',
        "description": 'Compares a function with a reference function [e.g. potentiallyCorrectSort(list) == quicksort(list)]',
        "argument": '--equivalent',
        "twoFunctions": True
    },
    {
        "typeId": PbtTypeId.MODEL_BASED,
        "name": 'Model Based',
        "description": 'Variant of test oracle, but a simpler version of the function is the reference [e.g. newFunc(x) == simplifiedFunc(x)]',
        "argument": '--equivalent',
        "twoFunctions": True
    },
    {
        "typeId": PbtTypeId.WITHIN_EXPECTED_BOUNDS,
        "name": 'Outputs Within Expected Bounds',
        "description": 'Tests the output domain of a function [e.g. sin(x) >= -1 and sin(x) <= 1]',
        "argument": '',
        "twoFunctions": False
    },
    {
        "typeId": PbtTypeId.METAMORPHIC_PROP,
        "name": 'Metamorphic Property',
        "description": 'Variant of test oracle, but the outputs are compared [e.g. newCompiler(src)(5) == oldCompiler(src)(5))]',
        "argument": '--equivalent',
        "twoFunctions": True
    },
    {
        "typeId": PbtTypeId.UNKNOWN,
        "name": 'Unknown',
        "description": 'Let the type be automatically determined by Hypothesis\' Ghostwriter function',
        "argument": '',
        "twoFunctions": False
    }
]
