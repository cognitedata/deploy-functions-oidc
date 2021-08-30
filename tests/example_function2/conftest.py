import pytest

from cognite.client.testing import monkeypatch_cognite_client


@pytest.fixture
def cognite_client_mock():
    with monkeypatch_cognite_client() as client:
        yield client


@pytest.fixture
def expected_input_data():
    return {"a": 2, "b": 3}


@pytest.fixture
def missing_input_data():
    return {"wrong": 90}


@pytest.fixture
def bad_input_data():
    return {"a": "I'm not a number", "b": 3}
