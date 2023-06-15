# Copyright 2023, Battelle Energy Alliance, LLC

import os
import deep_lynx


def retrieve_file(data_sources_api: deep_lynx.DataQueryApi, file_id: str):
    """
    Downloads a file from Deep Lynx
    Args
        data_sources_api (deep_lynx.DataSourcesApi): deep lynx data source api
        file_id (string): the id of a file
    Return
        path (string), file_name (string)
    """
    # Get deep lynx environment variables
    container_id = os.environ["CONTAINER_ID"]

    retrieve_file = data_sources_api.retrieve_file(container_id, file_id)

    if not retrieve_file.is_error:
        retrieve_file = retrieve_file.to_dict()["value"]
        path = retrieve_file["adapter_file_path"] + retrieve_file["file_name"]
        file_name = retrieve_file["file_name"]
        return path, file_name
