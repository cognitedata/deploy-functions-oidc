import pytest

from example_function2.handler import handle


@pytest.mark.unit
def test_handler__good_data(expected_input_data, cognite_client_mock):
    result = handle(expected_input_data, cognite_client_mock)
    assert result is not None
    assert "sum" in result
    assert result["sum"] == 5


@pytest.mark.unit
def test_handler__missing_data(missing_input_data, cognite_client_mock):
    with pytest.raises(KeyError):
        handle(missing_input_data, cognite_client_mock)


@pytest.mark.unit
def test_handler__bad_data(bad_input_data, cognite_client_mock):
    with pytest.raises(ValueError):
        handle(bad_input_data, cognite_client_mock)
