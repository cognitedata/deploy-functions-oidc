import pytest

from common.utilities import sum_integers


@pytest.mark.unit
def test_sum_integers():
    result = sum_integers(1, "2", 3.0)
    assert result == 6
    assert isinstance(result, int)
