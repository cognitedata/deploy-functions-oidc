from __future__ import annotations

import re
import sys
import time
import traceback

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from cognite.client import CogniteClient
from cognite.client.data_classes import Annotation, AnnotationFilter, FileMetadata, FileMetadataUpdate
from cognite.client.data_classes.contextualization import DiagramDetectResults
from cognite.client.utils._auxiliary import split_into_chunks
from cognite.client.utils._text import shorten
from config import AnnotationConfig
from constants import (
    ANNOTATION_RESOURCE_TYPE,
    ANNOTATION_STATUS_APPROVED,
    ASSET_ANNOTATION_TYPE,
    ASSET_MAX_LEN_META,
    CREATING_APP,
    CREATING_APPVERSION,
    FILE_ANNOTATION_TYPE,
    ORG_MIME_TYPE,
)


sys.path.append(str(Path(__file__).parent))


@dataclass
class Entity:
    external_id: str
    org_name: str
    name: list[str]
    id: int
    type: str = "file"

    def dump(self) -> dict[str, Any]:
        return {
            "externalId": self.external_id,
            "orgName": self.org_name,
            "name": self.name,
            "id": self.id,
            "type": self.type,
        }


def annotate_pnid(client: CogniteClient, config: AnnotationConfig) -> None:
    """
    Read configuration and start P&ID annotation process by
    1. Reading files to annotate
    2. Get file entities to be matched against files in P&ID
    3. Read existing annotations for the found files
    4. Get assets and put it into the list of entities to be found in the P&ID
    5. Process file:
        - detecting entities
        - creation annotations.
        - remove duplicate annotations

    Args:
        client: An instantiated CogniteClient
        config: A dataclass containing the configuration for the annotation process
    """
    try:
        all_file_external_ids_to_metadata, all_file_ids_to_external_id = get_all_files(client, config)
        all_file_entities = get_all_file_entities(all_file_external_ids_to_metadata)
        annotation_list = get_existing_annotations(client, all_file_entities) if all_file_entities else {}
        remaining_files_to_annotate: dict[str, FileMetadata] = {}

        if annotation_list and config.batch_size != -1:
            count = 0
            for file_id, file_annotations in annotation_list.items():
                if len(file_annotations) == 0 and count < config.batch_size:
                    file_external_id = all_file_ids_to_external_id[file_id]
                    remaining_files_to_annotate[file_external_id] = all_file_external_ids_to_metadata[file_external_id]
        else:
            remaining_files_to_annotate = (
                dict(list(all_file_external_ids_to_metadata.items())[: config.batch_size])
                if config.batch_size != -1
                else dict(list(all_file_external_ids_to_metadata.items()))
            )

        error_count, annotated_count = 0, 0
        if remaining_files_to_annotate:
            asset_entities = get_asset_entities(client, config)
            annotated_count, error_count = process_files(
                client, asset_entities, all_file_entities, remaining_files_to_annotate, annotation_list, config
            )
        msg = (
            f"Annotated P&ID files for dataset: {config.assets_data_set_external_id}, number of files annotated: {annotated_count}, "
            f"file not annotated due to errors: {error_count}"
        )

        print(f"[INFO] {msg}")
    except Exception as e:
        msg = (
            f"Annotated P&ID files failed on dataset: {config.assets_data_set_external_id}. "
            f"Message: {e!s}, traceback:\n{traceback.format_exc()}"
        )

        print(f"[ERROR] {msg}")


def get_all_files(client: CogniteClient, config: AnnotationConfig) -> ([dict[str, FileMetadata]], [dict[int, str]]):
    all_file_external_ids_to_metadata: dict[str, FileMetadata] = {}
    all_file_ids_to_external_id: dict[int, FileMetadata] = {}

    print(
        f"[INFO] Get files to annotate data set: {config.files_data_set_external_id!r}, "
        f"doc_type: {config.pnid_doc_type!r} and mime_type: {ORG_MIME_TYPE!r}"
    )

    file_list = client.files.list(
        mime_type=ORG_MIME_TYPE, limit=config.doc_limit, data_set_external_ids=[config.files_data_set_external_id]
    )

    for file in file_list:
        all_file_external_ids_to_metadata[file.external_id] = file
        all_file_ids_to_external_id[file.id] = file.external_id

    return all_file_external_ids_to_metadata, all_file_ids_to_external_id


def get_all_file_entities(all_pnid_files: dict[str, FileMetadata] = {}) -> [Entity]:
    """
    Get P&ID files and create a list of entities used for matching against file names in P&ID

    Args:
        all_pnid_files: All pnid files
    """

    entities: [Entity] = []

    for file_external_id, file_meta in all_pnid_files.items():
        if file_meta.name:
            entities.append(
                Entity(
                    external_id=file_external_id,
                    org_name=file_meta.name,
                    name=[file_meta.name],
                    id=file_meta.id,
                    type="file",
                )
            )
        else:
            print(
                f"[WARNING] No 'Document Number' or Name found for file with external ID: {file_external_id}, and metadata: {file_meta}"
            )
            continue

    return entities


def get_existing_annotations(client: CogniteClient, entities: list[Entity]) -> dict[Optional[int], list[Optional[int]]]:
    """
    Read list of already annotated files and get corresponding annotations

    :param client: Dict of files found based on filter
    :param entities:

    :returns: dictionary of annotations
    """
    annotated_file_text: dict[Optional[int], list[Optional[int]]] = defaultdict(list)

    print("[INFO] Get existing annotations based on annotated_resource_type= file, and filtered by found files")
    file_ids = [{"id": item.id} for item in entities]

    for sub_file_list in split_into_chunks(file_ids, 1000):
        annotation_list = client.annotations.list(
            AnnotationFilter(annotated_resource_type="file", annotated_resource_ids=sub_file_list),
            limit=None,
        )

        for annotation in annotation_list:
            # Only get old annotations created by this app - do not touch manual or other created annotations
            if annotation.creating_app == CREATING_APP:
                annotated_file_text[annotation.annotated_resource_id].append(annotation.id)
    return annotated_file_text


def get_asset_entities(client: CogniteClient, config: AnnotationConfig) -> [Entity]:
    """Get Asset used as input to contextualization and append to 'entities' list

    Args:
        entities: list of entites found so fare (file names)
        :param client: Instance of CogniteClient
        :param config:
    """

    asset_entities: [Entity] = []
    print(f"[INFO] Get assets based on data_set_external_ids = {config.assets_data_set_external_id}")
    assets = client.assets.list(data_set_external_ids=[config.assets_data_set_external_id], limit=-1)

    for asset in assets:
        sanitized_external_id = asset.external_id.replace("kall_", "")
        try:
            asset_entities.append(
                Entity(
                    external_id=asset.external_id,
                    org_name=sanitized_external_id,
                    name=sanitized_external_id,
                    id=asset.id,
                    type="asset",
                )
            )
        except Exception as e:
            print(
                f"[ERROR] Not able to get entities for asset name: {sanitized_external_id}, id {asset.external_id}. "
                f"Error: {type(e)}({e})"
            )

    return asset_entities


def process_files(
    client: CogniteClient,
    asset_entities: list[Entity],
    file_entities: list[Entity],
    files: dict[str, FileMetadata],
    annotation_list: dict[Optional[int], list[Optional[int]]],
    config: AnnotationConfig,
) -> tuple[int, int]:
    """Contextualize files by calling the annotation function
    Then update the metadata for the P&ID input file

    Args:
        client: client id used to connect to CDF
        asset_entities: list of asset entities that are used to match content in file
        file_entities: list of file entities that are used to match the content in file
        files: dict of files found based on filter
        annotation_list: list of existing annotations for input files
        config: configuration for the annotation process

    Returns:
        number of annotated files and number of errors
    """
    annotated_count = 0
    error_count = 0
    annotation_list = annotation_list or {}

    for file_xid, file in files.items():
        try:
            # contextualize, create annotation and get list of matched tags
            entities_name_found, entities_id_found = detect_create_annotation(
                client, config.match_threshold, file_xid, asset_entities, file_entities, annotation_list
            )
            # create a string of matched tag - to be added to metadata
            asset_names = shorten(",".join(map(str, entities_name_found)), ASSET_MAX_LEN_META)

            # merge existing assets with new-found, and create a list without duplicates
            file_asset_ids = file.asset_ids or []
            asset_ids_list = list(set(file_asset_ids + entities_id_found))

            # If list of assets more than 1000 items, cut the list at 1000
            if len(asset_ids_list) > 1000:
                print(
                    f"[WARNING] List of assetsIds for file {file.external_id} > 1000 ({len(asset_ids_list)}), "
                    "cutting list at 1000 items"
                )

                asset_ids_list = asset_ids_list[:1000]

            if config.debug:
                print(f"[INFO] Converted and created (not upload due to DEBUG) file: {file_xid}")
                print(f"[INFO] Assets found: {asset_names}")
                continue

            annotated_count += 1
            file_update = FileMetadataUpdate(id=file.id).asset_ids.set(asset_ids_list)

            safe_files_update(client, file_update, file.external_id)
        except Exception as e:
            error_count += 1
            print(f"[ERROR] Failed to annotate the document: {file_xid!r}, error: {type(e)}({e})")

    return annotated_count, error_count


def detect_create_annotation(
    client: CogniteClient,
    match_threshold: float,
    file_external_id: str,
    asset_entities: list[Entity],
    file_entities: list[Entity],
    annotation_list: dict[Optional[int], list[Optional[int]]],
) -> tuple[list[Any], list[Any]]:
    """
    Detect tags + files and create annotation for P&ID

    Args:
        client: client id used to connect to CDF
        match_threshold: score used to qualify match
        file_external_id: file to be processed
        asset_entities: list of input asset entities that are used to contextualize content in file
        file_entities: list of input file entities that are used contextualize content in file
        annotation_list: list of existing annotations for input files

    Returns:
        list of found entities and list of found entities ids
    """

    print(f"Processing file {file_external_id}")

    asset_contextualization_job = retrieve_diagram_with_retry(
        client=client, entities=asset_entities, file_id=file_external_id, min_tokens=1
    )

    asset_ids_found = []
    asset_names_found = []
    asset_annotation_list_to_create: list[Annotation] = []
    file_annotation_list_to_create: list[Annotation] = []
    to_delete_annotation_list: list[int] = []

    # Asset annotation processing
    asset_annotated_resource_id = asset_contextualization_job.result["items"][0]["fileId"]
    if asset_annotated_resource_id in annotation_list:
        to_delete_annotation_list.extend(annotation_list[asset_annotated_resource_id])

    for asset_annotation in asset_contextualization_job.result["items"][0]["annotations"]:
        asset_entity = asset_annotation["entities"][0]
        assert asset_entity["type"] == "asset"
        annotation_type, ref_type, annotation_name = ASSET_ANNOTATION_TYPE, "assetRef", asset_entity["orgName"]
        assert annotation_type == ASSET_ANNOTATION_TYPE

        if 3 <= len(annotation_name):
            print(f"annotation name={annotation_name}")
            # Logic to create suggestions for annotations if system number is missing from tag in P&ID
            # but a suggestion matches the most frequent system number from P&ID
            matched_tokens_count = annotation_name.split("-")
            if asset_annotation["confidence"] >= match_threshold and len(asset_annotation["entities"]) == 1:
                annotation_status = ANNOTATION_STATUS_APPROVED
            # If there are long asset names a lower confidence is ok to create a suggestion
            elif asset_annotation["confidence"] >= 0.7 and len(matched_tokens_count) == 1:
                annotation_status = ANNOTATION_STATUS_APPROVED
            else:
                continue

            if not is_black_listed_text(annotation_name):
                if annotation_status == ANNOTATION_STATUS_APPROVED:
                    asset_names_found.append(asset_entity["orgName"])
                    asset_ids_found.append(asset_entity["id"])

                asset_annotation_list_to_create.append(
                    Annotation(
                        annotation_type=annotation_type,
                        data={
                            ref_type: {"id": asset_entity["id"]},
                            "pageNumber": asset_annotation["region"]["page"],
                            "text": annotation_name,
                            "textRegion": get_coordinates(asset_annotation["region"]["vertices"]),
                        },
                        status=annotation_status,
                        annotated_resource_type=ANNOTATION_RESOURCE_TYPE,
                        annotated_resource_id=asset_annotated_resource_id,
                        creating_app=CREATING_APP,
                        creating_app_version=CREATING_APPVERSION,
                        creating_user=f"job.{asset_contextualization_job.job_id}",
                    )
                )

        # Create annotations once we hit 1k (to spread insertion over time):
        if len(asset_annotation_list_to_create) == 1000:
            client.annotations.create(asset_annotation_list_to_create)
            asset_annotation_list_to_create.clear()

    client.annotations.create(asset_annotation_list_to_create)
    print(
        f"Completed creating asset annotations for file: {file_external_id}, Created asset annotation count: {len(asset_annotation_list_to_create)}"
    )

    # File annotation processing
    file_contextualization_job = retrieve_diagram_with_retry(
        client=client, entities=file_entities, file_id=file_external_id
    )

    file_annotated_resource_id = file_contextualization_job.result["items"][0]["fileId"]
    if file_annotated_resource_id in annotation_list:
        to_delete_annotation_list.extend(annotation_list[file_annotated_resource_id])

    for file_annotation in file_contextualization_job.result["items"][0]["annotations"]:
        for entity in file_annotation["entities"]:
            assert entity["type"] == "file"
            annotation_type, ref_type, annotation_name = FILE_ANNOTATION_TYPE, "fileRef", entity["orgName"]

            if annotation_type == FILE_ANNOTATION_TYPE:
                # Logic to create suggestions for annotations if system number is missing from tag in P&ID
                # but a suggestion matches the most frequent system number from P&ID
                matched_tokens = re.split(r"[-/]", file_annotation["text"])
                matched_tokens_count = len(matched_tokens)
                annotation_name_splits = re.split(r":", annotation_name)

                if len(annotation_name_splits) <= 2:
                    annotation_name_tokens = re.split(r"[-/]", annotation_name_splits[0])
                    annotation_name_token_count = len(annotation_name_tokens)
                else:
                    assert False

                delta_tokens = annotation_name_token_count - matched_tokens_count
                if file_annotation["confidence"] == 1:
                    if delta_tokens == 0:
                        if is_equal(matched_tokens, annotation_name_tokens):
                            annotation_status = ANNOTATION_STATUS_APPROVED
                        else:
                            annotation_status = ANNOTATION_STATUS_APPROVED  # ANNOTATION_STATUS_SUGGESTED
                    elif delta_tokens == 1:
                        annotation_status = ANNOTATION_STATUS_APPROVED  # ANNOTATION_STATUS_SUGGESTED
                    else:
                        continue
                elif file_annotation["confidence"] >= match_threshold:
                    if delta_tokens <= 2:
                        annotation_status = ANNOTATION_STATUS_APPROVED  # ANNOTATION_STATUS_SUGGESTED
                    else:
                        continue
                else:
                    continue

                if not is_black_listed_text(annotation_name):
                    file_annotation_list_to_create.append(
                        Annotation(
                            annotation_type=annotation_type,
                            data={
                                ref_type: {"id": entity["id"]},
                                "pageNumber": file_annotation["region"]["page"],
                                "text": annotation_name,
                                "textRegion": get_coordinates(file_annotation["region"]["vertices"]),
                            },
                            status=annotation_status,
                            annotated_resource_type=ANNOTATION_RESOURCE_TYPE,
                            annotated_resource_id=file_annotated_resource_id,
                            creating_app=CREATING_APP,
                            creating_app_version=CREATING_APPVERSION,
                            creating_user=f"job.{file_contextualization_job.job_id}",
                        )
                    )

            # Create annotations once we hit 1k (to spread insertion over time):
            if len(file_annotation_list_to_create) == 1000:
                client.annotations.create(file_annotation_list_to_create)
                file_annotation_list_to_create.clear()

    client.annotations.create(file_annotation_list_to_create)
    print(
        f"Completed creating file annotations for file: {file_external_id}, Created file annotation count: {len(file_annotation_list_to_create)}"
    )

    safe_delete_annotations(to_delete_annotation_list, client)
    # De-duplicate list of names and id before returning:
    return list(set(asset_names_found)), list(set(asset_ids_found))


def is_equal(list_1: [str], list_2: [str]):
    return sorted(list_1) == sorted(list_2)


def is_black_listed_text(text: str):
    sanitized_text_splits = text.split(":")
    sanitized_text = sanitized_text_splits[0] if len(sanitized_text_splits) >= 2 else text
    return sanitized_text in []


def retrieve_diagram_with_retry(
    client: CogniteClient,
    entities: list[Entity],
    file_id: str,
    retries: int = 3,
    min_tokens: int = 2,
    multiple_jobs: bool = False,
) -> DiagramDetectResults:
    for retry_num in range(1, retries + 1):
        try:
            return client.diagrams.detect(
                file_external_ids=[file_id],
                search_field="name",
                entities=[e.dump() for e in entities],
                partial_match=True,
                min_tokens=min_tokens,
                multiple_jobs=multiple_jobs,
            )
        except Exception as e:
            # retry func if CDF api returns an error
            if retry_num < 3:
                print(f"[WARNING] Failed to detect entities, retry #{retry_num}, error: {type(e)}({e})")
                time.sleep(retry_num * 5)
            else:
                msg = f"Failed to detect entities, error: {type(e)}({e})"
                print(f"[ERROR] {msg}")
                raise RuntimeError(msg)


def get_coordinates(vertices: list[dict]) -> dict[str, int]:
    """Get coordinates for text box based on input from contextualization
    and convert it to coordinates used in annotations.

    Args:
        vertices (list[dict]): coordinates from contextualization

    Returns:
        dict[str, int]: coordinates used by annotations.
    """
    x_min, *_, x_max = sorted(min(1, vert["x"]) for vert in vertices)
    y_min, *_, y_max = sorted(min(1, vert["y"]) for vert in vertices)

    # Adjust if min and max are equal
    if x_min == x_max:
        x_min, x_max = (x_min - 0.001, x_max) if x_min > 0.001 else (x_min, x_max + 0.001)
    if y_min == y_max:
        y_min, y_max = (y_min - 0.001, y_max) if y_min > 0.001 else (y_min, y_max + 0.001)

    return {"xMax": x_max, "xMin": x_min, "yMax": y_max, "yMin": y_min}


def safe_delete_annotations(delete_annotation_list: list[int], client: CogniteClient) -> None:
    """
    Delete existing annotations

    Handles any exception and log error if delete fails

    Args:
        delete_annotation_list: list of annotation IDs to be deleted
        client: CogniteClient
    """
    try:
        client.annotations.delete(list(set(delete_annotation_list)))
    except Exception as e:
        print(f"[ERROR] Failed to delete annotations, error: {type(e)}({e})")


def safe_files_update(
    client: CogniteClient,
    file_update: FileMetadataUpdate,
    file_external_id: str,
) -> None:
    """
    Update metadata of original pdf file with list of tags

    Catch exception and log error if update fails

    Args:
        client: client id used to connect to CDF
        file_update: list of updates to be done
        file_external_id: file to be updated
    """
    try:
        client.files.update(file_update)
    except Exception as e:
        print(f"[ERROR] Failed to update the file {file_external_id!r}, error: {type(e)}({e})")
