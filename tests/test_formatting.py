import pytest

from app.formatting import format_clp


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (0, "$0"),
        (990, "$990"),
        (12990, "$12.990"),
        (45990, "$45.990"),
        (1000000, "$1.000.000"),
    ],
)
def test_format_clp(amount, expected):
    assert format_clp(amount) == expected


def test_format_clp_rejects_non_integers():
    with pytest.raises(TypeError):
        format_clp(12.99)
    with pytest.raises(TypeError):
        format_clp(True)
