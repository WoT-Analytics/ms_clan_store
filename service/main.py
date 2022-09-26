"""This file contains the ms_clan_store microservice based on fastapi and redis"""
import os
from collections.abc import Generator

# 3rd party modules
import fastapi
import redis
import requests
from pydantic import BaseModel

# TODO Redis Error catching
# ENV vars
REDIS_HOST = os.getenv("REDIS_HOST", "")
redis_port = os.getenv("REDIS_PORT", "")
API_SERVICE_HOST = os.getenv("API_HOST", "")
api_port = os.getenv("API_PORT", "")
if not REDIS_HOST:
    raise ValueError("Missing Environment Variable: REDIS_HOST is missing or empty!")
if not redis_port:
    raise ValueError("Missing Environment Variable: REDIS_PORT is missing or empty!")
if not API_SERVICE_HOST:
    raise ValueError("Missing Environment Variable: API_HOST is missing or empty!")
if not api_port:
    raise ValueError("Missing Environment Variable: API_PORT is missing or empty!")

try:
    REDIS_PORT = int(redis_port)
    API_SERVICE_PORT = int(api_port)
except ValueError as exc:
    raise ValueError(
        "At least one value of the Environment Variables [REDIS_PORT, API_PORT] is not convertible to a number"
    ) from exc


API_TIMEOUT = 5

app = fastapi.FastAPI()


class ClanModel(BaseModel):
    """Base Pydantic Model to represent the most import data for a single clan."""

    clan_id: int
    clan_tag: str


def get_db_id_session() -> Generator:
    """
    yields a redis connection to database 1 (id -> tag)
    :return: redis.Redis object
    """
    red_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=1)
    try:
        yield red_client
    finally:
        red_client.close()


def get_db_tag_session() -> Generator:
    """
    yields a redis connection to database 2 (tag -> id)
    :return: redis.Redis object
    """
    red_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=2)
    try:
        yield red_client
    finally:
        red_client.close()


def update_clan(clan_id: int) -> ClanModel:
    """
    Retrieves the latest data from the api microservice for a given clan id
    :param clan_id: clan id of clan to look info up for
    :return: ClanModel with the latest data
    :raises: HTTPError on status codes 4XX & 5XX in the response from the api microservice
    """
    response = requests.get(f"http://{API_SERVICE_HOST}:{API_SERVICE_PORT}/clan/id/{clan_id}", timeout=API_TIMEOUT)
    response.raise_for_status()
    response_data = response.json()
    return ClanModel(**response_data)


@app.put(
    "/clans",
    response_class=fastapi.Response,
    description="Adds a new clan to the database.",
    responses={201: {"description": "Clan successfully created in database"}},
)
def add_clan(
    new_clan: ClanModel,
    db_ids: redis.Redis = fastapi.Depends(get_db_id_session),
    db_tags: redis.Redis = fastapi.Depends(get_db_tag_session),
) -> fastapi.Response:
    """
    Creates/ Saves a new clan in the database
    :param new_clan: Clan Information in the request
    :param db_ids: connection to redis table for ids
    :param db_tags: connection to redis table for tags
    :return: Response 201 on success
    """
    db_ids.set(name=str(new_clan.clan_id), value=new_clan.clan_tag)
    db_tags.set(name=new_clan.clan_tag, value=str(new_clan.clan_id))
    return fastapi.Response(status_code=fastapi.status.HTTP_201_CREATED)


@app.delete("/clans", response_class=fastapi.Response, description="Deletes a clan from the database.")
def delete_clan(
    new_clan: ClanModel,
    db_ids: redis.Redis = fastapi.Depends(get_db_id_session),
    db_tags: redis.Redis = fastapi.Depends(get_db_tag_session),
) -> fastapi.Response:
    """
    Deletes a clan from the database
    :param new_clan: Clan Information in the request
    :param db_ids: connection to redis table for ids
    :param db_tags: connection to redis table for tags
    :return: Response 200 on success
    """
    db_ids.delete(str(new_clan.clan_id))
    db_tags.delete(new_clan.clan_tag)
    return fastapi.Response(status_code=fastapi.status.HTTP_200_OK)


@app.get(
    "/clans",
    response_model=list[ClanModel],
    description="Returns the list of all Clans in the db",
    responses={500: {"description": "Internal Server Error"}},
)
def list_clans(db_ids: redis.Redis = fastapi.Depends(get_db_id_session)) -> list[ClanModel]:
    """
    Returns a list with all clans which are contained in the database
    :param db_ids: connection to redis table for ids
    :return: Response 200 on success
    """
    response = []
    clan_ids = db_ids.keys()
    for clan_id in clan_ids:
        clan_id_f = int(clan_id)
        clan_tag_b = db_ids.get(str(clan_id_f))
        if clan_tag_b is None:
            raise fastapi.HTTPException(
                status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Entry in Database table for clan id {clan_id_f} was empty.",
            )
        clan_tag = clan_tag_b.decode("utf-8")
        response.append(ClanModel(clan_id=clan_id_f, clan_tag=clan_tag))
    return response


@app.post(
    "/clans",
    response_class=fastapi.Response,
    description="Trigger the update process to update all clans from the api.",
    responses={500: {"description": "Update failed"}},
)
def update_clans(
    db_ids: redis.Redis = fastapi.Depends(get_db_id_session), db_tags: redis.Redis = fastapi.Depends(get_db_tag_session)
) -> fastapi.Response:
    """
    Updates all clan tags with the latest information from the api service
    :param db_ids: connection to redis table for ids
    :param db_tags: connection to redis table for tags
    :return: Response 200 on success, 500 on failed updates
    """
    clans = db_ids.keys()
    failed_updates = []

    for clan_id in clans:
        clan_id_f = int(clan_id)
        old_clan_tag_b = db_ids.get(str(clan_id_f))
        if old_clan_tag_b is None:
            failed_updates.append((clan_id_f, "???"))
            print(f"Value for clan id {clan_id_f} was empty.")
            continue

        old_clan_tag = old_clan_tag_b.decode("utf-8")

        try:
            new_clan = update_clan(clan_id_f)
        except Exception as exc:
            failed_updates.append((clan_id_f, old_clan_tag))
            print(exc)
            continue

        if new_clan.clan_tag == old_clan_tag:
            continue

        db_tags.delete(old_clan_tag)
        db_ids.set(name=str(new_clan.clan_id), value=new_clan.clan_tag)
        db_tags.set(name=new_clan.clan_tag, value=str(new_clan.clan_id))

    if len(failed_updates) == 0:
        clan_list_formatted = [f"Clan [{clan[1]}({clan[0]})]" for clan in failed_updates]
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Updates failed for clans: [{', '.join(clan_list_formatted)}].",
        )
    return fastapi.Response(status_code=fastapi.status.HTTP_200_OK)


@app.get(
    "/clans/{clan_tag}",
    response_model=ClanModel,
    description="Deletes a clan from the database.",
    responses={404: {"description": "Requested Clan does not exist"}},
)
def get_clan(clan_tag: str, db_tags: redis.Redis = fastapi.Depends(get_db_tag_session)) -> ClanModel:
    """
    Looks up the clan tag for a certain clan to retrieve the stored information from the database for it.
    :param clan_tag: Clan tag to retrieve clan information for
    :param db_tags: connection to redis table for tags
    :return: ClanModel if the clan is stored in the database, else Response 404
    """
    clan_id = db_tags.get(clan_tag)
    if clan_id is None:
        raise fastapi.HTTPException(
            status_code=fastapi.status.HTTP_404_NOT_FOUND, detail=f"Clan with tag {clan_tag} is not in the clan db."
        )
    return ClanModel(clan_id=int(clan_id), clan_tag=clan_tag)
