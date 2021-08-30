import pytest

from example_function1.handler import handle


@pytest.mark.unit
def test_handler(mocked_data, cognite_client_mock):
    result = handle(mocked_data, cognite_client_mock)
    assert result == mocked_data
