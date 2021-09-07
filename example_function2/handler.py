from common.utilities import sum_integers


def handle(data, client):
    print("I got the following data:")
    print(data)

    if not ("a" in data and "b" in data):
        raise KeyError("Data should contain both keys: 'a' and 'b'")

    data["sum"] = sum_integers(data["a"], data["b"])

    print("Will now return updated data")

    return data
