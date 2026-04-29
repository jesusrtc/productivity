from __future__ import annotations

import pytest

from lab.util import split_csv


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("", []),
        (None, []),
        ("a", ["a"]),
        ("a,b,c", ["a", "b", "c"]),
        ("  a , b ,  c ", ["a", "b", "c"]),
        ("a,,b", ["a", "b"]),
        (",a,b,", ["a", "b"]),
        ("a, ,b", ["a", "b"]),
    ],
)
def test_split_csv(raw, expected) -> None:
    assert split_csv(raw) == expected
