from fastapi.testclient import TestClient

from service.main import app, get_db_id_session, get_db_tag_session


class RedisMock:

    def __init__(self):
        self.values = {}

    def get(self, name: str):
        val = self.values.get(name)
        if val is None:
            return val
        return val.encode("utf-8")

    def set(self, name: str, value: str):
        self.values[name] = value

    def delete(self, key: str):
        del self.values[key]

    def keys(self):
        return sorted(list(self.values.keys()))


def get_db_id_override():
    return id_redis_mock


def get_db_tag_override():
    return tag_redis_mock


id_redis_mock = RedisMock()
tag_redis_mock = RedisMock()

client = TestClient(app)
app.dependency_overrides[get_db_id_session] = get_db_id_override
app.dependency_overrides[get_db_tag_session] = get_db_tag_override


def test_add_clan_new():
    id_redis_mock.values = {}
    tag_redis_mock.values = {}
    response = client.put("/clans", json={"clan_id": 1, "clan_tag": "TEST"})
    assert response.status_code == 201
    assert id_redis_mock.values == {"1": "TEST"}
    assert tag_redis_mock.values == {"TEST": "1"}


def test_add_clan_existing():
    id_redis_mock.values = {"1": "TEST"}
    tag_redis_mock.values = {"TEST": "1"}
    response = client.put("/clans", json={"clan_id": 1, "clan_tag": "TEST"})
    assert response.status_code == 200
    assert id_redis_mock.values == {"1": "TEST"}
    assert tag_redis_mock.values == {"TEST": "1"}


def test_delete_clan_error():
    id_redis_mock.values = {"1": "TEST"}
    tag_redis_mock.values = {"TEST": "1"}
    response = client.delete("/clans", json={"clan_id": 2, "clan_tag": "TE2T"})
    assert response.status_code == 404
    assert id_redis_mock.values == {"1": "TEST"}
    assert tag_redis_mock.values == {"TEST": "1"}


def test_delete_clan_existing():
    id_redis_mock.values = {"1": "TEST"}
    tag_redis_mock.values = {"TEST": "1"}
    response = client.delete("/clans", json={"clan_id": 1, "clan_tag": "TEST"})
    assert response.status_code == 200
    assert id_redis_mock.values == {}
    assert tag_redis_mock.values == {}


def test_list_clans():
    id_redis_mock.values = {"1": "TEST", "2": "TE2T", "3": "T3ST", "4": "T4ST"}
    response = client.get("/clans")
    assert response.status_code == 200
    assert response.json() == [{"clan_id": 3, "clan_tag": "T3ST"}, {"clan_id": 4, "clan_tag": "T4ST"},
                               {"clan_id": 2, "clan_tag": "TE2T"}, {"clan_id": 1, "clan_tag": "TEST"}]


def test_get_clan_error():
    id_redis_mock.values = {"2": "TE2T"}
    tag_redis_mock.values = {"TE2T": "2"}
    response = client.get("/clans/TEST")
    assert response.status_code == 404


def test_get_clan_success():
    id_redis_mock.values = {"1": "TEST"}
    tag_redis_mock.values = {"TEST": "1"}
    response = client.get("/clans/TEST")
    assert response.status_code == 200
    assert response.json() == {"clan_id": 1, "clan_tag": "TEST"}
