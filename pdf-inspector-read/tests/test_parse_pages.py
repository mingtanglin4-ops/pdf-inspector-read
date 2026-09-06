import pytest

import pdfread


@pytest.mark.parametrize("spec,expected", [
    (None, None),
    ("", None),
    ("1", [1]),
    ("1,3", [1, 3]),
    ("5-9", [5, 6, 7, 8, 9]),
    ("1,3,5-7", [1, 3, 5, 6, 7]),
    (" 2 , 4 ", [2, 4]),
    ("1,,2", [1, 2]),
])
def test_parse_pages(spec, expected):
    assert pdfread.parse_pages(spec) == expected
