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
        "description": 'Different Paths, Same Destination__"description"',
        "argument": '--equivalent',
        "twoFunctions": False
    },
    {
        "typeId": PbtTypeId.ROUNDTRIP,
        "name": 'Roundtrip',
        "description": 'Roundtrip__"description"',
        "argument": '--roundtrip',
        "twoFunctions": True
    },
    {
        "typeId": PbtTypeId.SOME_THINGS_NEVER_CHANGE,
        "name": 'Some Things Never Change',
        "description": 'Some Things Never Change__"description"',
        "argument": '--idempotent',
        "twoFunctions": False
    },
    {
        "typeId": PbtTypeId.THE_MORE_THINGS_CHANGE,
        "name": 'The More Things Change, the More They Stay the Same',
        "description": 'Some Things Never Change__"description"',
        "argument": '--idempotent',
        "twoFunctions": False
    },
    {
        "typeId": PbtTypeId.SOLVE_SMALLER_PROBLEM_FIRST,
        "name": 'Solve a Smaller Problem First',
        "description": 'Solve a Smaller Problem First__"description"',
        "argument": '',
        "twoFunctions": False
    },
    {
        "typeId": PbtTypeId.HARD_TO_PROVE,
        "name": 'Hard to Prove, Easy to Verify',
        "description": 'Hard to Prove, Easy to Verify__"description"',
        "argument": '--equivalent',
        "twoFunctions": False
    },
    {
        "typeId": PbtTypeId.TEST_ORACLE,
        "name": 'The Test oracle',
        "description": 'Test oracle__"description"',
        "argument": '--equivalent',
        "twoFunctions": True
    },
    {
        "typeId": PbtTypeId.MODEL_BASED,
        "name": 'Model Based',
        "description": 'Model Based__"description"',
        "argument": '',
        "twoFunctions": True
    },
    {
        "typeId": PbtTypeId.WITHIN_EXPECTED_BOUNDS,
        "name": 'Outputs Within Expected Bounds',
        "description": 'Outputs Within Expected Bounds__"description"',
        "argument": '',
        "twoFunctions": False
    },
    {
        "typeId": PbtTypeId.METAMORPHIC_PROP,
        "name": 'Metamorphic Property',
        "description": 'Metamorphic Property__"description"',
        "argument": '--equivalent',
        "twoFunctions": True
    },
    {
        "typeId": PbtTypeId.UNKNOWN,
        "name": 'Unknown',
        "description": 'Let the type be automatically determined',
        "argument": '',
        "twoFunctions": False
    }
]
