# Do not forget to add a '\' before a comma in the strategies!
supportedStrategies = {
    "integers": "st.integers()",
    "integers_bounded": "st.integers(min_value=-10\, max_value=10)",
    "floats": "st.floats(allow_infinity=False\, allow_nan=False)",
    "decimals": "st.decimals()",
    "strings": "st.text()",
    "strings_bounded": "st.text(min_size=0\, max_size=10)",
    "booleans": "st.booleans()",
    "characters": "st.characters()",
    "lists_of_integers": "st.lists(st.integers())",
    "lists_of_strings": "st.lists(st.text())",
    "lists": "st.lists()",
}