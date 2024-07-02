from __future__ import annotations

import datetime as dt
import os
import sys

from pathlib import Path

import pandas as pd

from cognite.client import ClientConfig, CogniteClient
from cognite.client.credentials import OAuthClientCredentials

from fn_uptime_data_generator.uptime import insert_uptime_kpi


sys.path.append(str(Path(__file__).parent))


def handle(data: dict, client: CogniteClient) -> dict:
    today = pd.Timestamp(dt.datetime.today().strftime("%Y-%m-%d"))

    insert_uptime_kpi(today, client)
    return {"status": "succeeded", "data": data}


def run_locally():
    required_envvars = (
        "KYOTO_CDF_PROJECT",
        "KYOTO_CDF_CLUSTER",
        "KYOTO_IDP_CLIENT_ID",
        "KYOTO_IDP_CLIENT_SECRET",
        "KYOTO_IDP_TOKEN_URL",
    )

    if missing := [envvar for envvar in required_envvars if envvar not in os.environ]:
        raise ValueError(f"Missing one or more env.vars: {missing}")

    cdf_project_name = "kyotogroup-dev"  # os.environ["CDF_PROJECT"]
    cdf_cluster = os.environ["KYOTO_CDF_CLUSTER"]
    client_id = os.environ["KYOTO_IDP_CLIENT_ID"]
    client_secret = os.environ["KYOTO_IDP_CLIENT_SECRET"]
    token_uri = os.environ["KYOTO_IDP_TOKEN_URL"]
    base_url = f"https://{cdf_cluster}.cognitedata.com"

    client = CogniteClient(
        ClientConfig(
            client_name="uptime pipeline",
            base_url=base_url,
            project=cdf_project_name,
            credentials=OAuthClientCredentials(
                token_url=token_uri,
                client_id=client_id,
                client_secret=client_secret,
                scopes=[f"{base_url}/.default"],
            ),
        )
    )

    handle(
        {},
        client,
    )


if __name__ == "__main__":
    run_locally()
