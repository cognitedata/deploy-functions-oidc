import pytest

from example_with_logging.handler import handle


@pytest.mark.unit
def test_handler():
    handle()
    assert True
