"""This file contains the ms_clan_store microservice based on fastapi and redis"""
from __future__ import annotations
import os
from collections.abc import Generator

# 3rd party modules
import fastapi
import redis
from pydantic import BaseModel

# TODO Redis Error catching
# ENV vars
REDIS_HOST: str = os.getenv("REDIS_HOST", "")  # type: ignore
REDIS_PORT: int = int(os.getenv("REDIS_PORT", "8080"))  # type: ignore

API_TIMEOUT = 5

app = fastapi.FastAPI()


class ClanModel(BaseModel):
    """Base Pydantic Model to represent the most import data for a single clan."""

    clan_id: int
    clan_tag: str

    def __lt__(self, other: ClanModel):
        """
        Compares this object with another ClanModel object with the less than operator.
        :param other: ClanModel object to be compared to this object
        :return: True if this object is less than the other
        """
        return self.clan_tag <= other.clan_tag


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


@app.put(
    "/clans",
    response_class=fastapi.Response,
    description="Adds a new clan to the database.",
    responses={201: {"description": "Clan successfully created in database."},
               200: {"description": "Clan already existed in database, update done."}},
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
    response = fastapi.Response(status_code=fastapi.status.HTTP_201_CREATED)
    if db_ids.get(str(new_clan.clan_id)):
        response = fastapi.Response(status_code=fastapi.status.HTTP_200_OK)
    db_ids.set(name=str(new_clan.clan_id), value=new_clan.clan_tag)
    db_tags.set(name=new_clan.clan_tag, value=str(new_clan.clan_id))
    return response


@app.delete("/clans", response_class=fastapi.Response, description="Deletes a clan from the database.",
            responses={404: {"description": "Clan could not be deleted. It was not in the database."}})
def delete_clan(
    clan: ClanModel,
    db_ids: redis.Redis = fastapi.Depends(get_db_id_session),
    db_tags: redis.Redis = fastapi.Depends(get_db_tag_session),
) -> fastapi.Response:
    """
    Deletes a clan from the database
    :param clan: Clan Information in the request
    :param db_ids: connection to redis table for ids
    :param db_tags: connection to redis table for tags
    :return: Response 200 on success
    """
    if not db_ids.get(str(clan.clan_id)):
        raise fastapi.HTTPException(status_code=fastapi.status.HTTP_404_NOT_FOUND,
                                    detail=f"Clan [{clan.clan_id}]({clan.clan_id}) is not in the system.")
    db_ids.delete(str(clan.clan_id))
    db_tags.delete(clan.clan_tag)
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
    response_sorted = sorted(response)
    return response_sorted


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
