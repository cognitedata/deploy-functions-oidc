from __future__ import annotations

import os
import re
import sys

from pathlib import Path

from cognite.client import ClientConfig, CogniteClient
from cognite.client.credentials import OAuthClientCredentials
from constants import METADATA_LIMBER_FILE_COMPONENT_TAGS


sys.path.append(str(Path(__file__).parent))


def handle(data: dict, client: CogniteClient) -> dict:
    all_files = client.files.list(data_set_external_ids=data["files_data_set_external_id"], limit=None)
    all_assets = client.assets.list(data_set_external_ids=data["assets_data_set_external_id"], limit=None)
    files_to_update = []
    default_matching_asset = client.assets.retrieve(external_id=data["heatcube_control_asset_external_id"])

    for file in all_files:
        asset_ids = get_asset_ids(file=file, all_assets=all_assets, default_matching_asset=default_matching_asset)
        if len(asset_ids) > 0:
            asset_ids_to_update = set(asset_ids + (file.asset_ids if file.asset_ids else []))
            print(f"File: {file.external_id}, Number of contextualized assets: {len(asset_ids_to_update)}")
            files_to_update.append(file)

    client.files.update(item=files_to_update)
    return {"status": "succeeded", "data": data}


def get_asset_ids(file, all_assets, default_matching_asset):
    matching_asset_ids = []
    if file.metadata and METADATA_LIMBER_FILE_COMPONENT_TAGS in file.metadata.keys():
        file_tags = [tag.strip() for tag in file.metadata[METADATA_LIMBER_FILE_COMPONENT_TAGS].split(",")]
        if file_tags:
            for file_tag in file_tags:
                try:
                    pattern = get_regex_pattern(file_tag)
                    matching_asset_ids.extend(
                        [
                            asset.id
                            for asset in all_assets
                            if pattern.search(asset.external_id) and asset.id not in matching_asset_ids
                        ]
                    )
                except IndexError:
                    pass

    if len(matching_asset_ids) == 0:
        pattern = get_regex_pattern(file.name)
        matching_asset_ids.extend(
            [
                asset.id
                for asset in all_assets
                if pattern.search(asset.external_id) and asset.id not in matching_asset_ids
            ]
        )

    if len(matching_asset_ids) == 0:
        matching_asset_ids.append(default_matching_asset.id)

    return matching_asset_ids


def get_regex_pattern(file_tag: str):
    regex_tag = file_tag.replace("-", "_").replace("_", ".*")
    return re.compile(rf"{regex_tag}")


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

    cdf_project_name = os.environ["KYOTO_CDF_PROJECT"]
    cdf_cluster = os.environ["KYOTO_CDF_CLUSTER"]
    client_id = os.environ["KYOTO_IDP_CLIENT_ID"]
    client_secret = os.environ["KYOTO_IDP_CLIENT_SECRET"]
    token_uri = os.environ["KYOTO_IDP_TOKEN_URL"]
    base_url = f"https://{cdf_cluster}.cognitedata.com"

    client = CogniteClient(
        ClientConfig(
            client_name="P&ID pipeline",
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
        {
            "files_data_set_external_id": "src:kall:limber",
            "assets_data_set_external_id": "src:kall:assets",
            "reset": False,
            "heatcube_control_asset_external_id": "kall_C",
        },
        client,
    )


if __name__ == "__main__":
    run_locally()
