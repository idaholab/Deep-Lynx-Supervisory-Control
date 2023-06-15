# Copyright 2023, Battelle Energy Alliance, LLC

import os
import logging
import deep_lynx

api_client = None


def deep_lynx_init():
    """
    Returns the container id, data source id, and api client for use with the DeepLynx SDK.
    Assumes token authentication.

    Args
        None
    Return
        container_id (str), data_source_id (str), api_client (ApiClient)
    """
    # initialize an ApiClient for use with deep_lynx APIs
    configuration = deep_lynx.configuration.Configuration()
    configuration.host = os.getenv('DEEP_LYNX_URL')
    api_client = deep_lynx.ApiClient(configuration)

    # perform API token authentication only if values are provided
    if os.getenv('DEEP_LYNX_API_KEY') != '' and os.getenv('DEEP_LYNX_API_KEY') is not None:

        # authenticate via an API key and secret
        auth_api = deep_lynx.AuthenticationApi(api_client)

        try:
            token = auth_api.retrieve_o_auth_token(x_api_key=os.getenv('DEEP_LYNX_API_KEY'),
                                                   x_api_secret=os.getenv('DEEP_LYNX_API_SECRET'),
                                                   x_api_expiry='12h')
        except TypeError:
            print("ERROR: Cannot connect to DeepLynx.")
            logging.error("Cannot connect to DeepLynx.")
            return '', '', None

        # update header
        api_client.set_default_header('Authorization', 'Bearer {}'.format(token))

    # get container ID
    container_id = None
    containers = None
    container_api = deep_lynx.ContainersApi(api_client)

    try:
        containers = container_api.list_containers()
    except TypeError or Exception:
        print("ERROR: Cannot connect to DeepLynx.")
        logging.error("Cannot connect to DeepLynx.")
        return '', '', None

    for container in containers.value:
        if container.name == os.getenv('CONTAINER_NAME'):
            container_id = container.id
            continue

    if container_id is None:
        print("ERROR: Container not found")
        logging.error("ERROR: Container not found")
        return '', '', None

    # get data source ID, create if necessary
    data_source_id = None
    datasources_api = deep_lynx.DataSourcesApi(api_client)

    datasources = datasources_api.list_data_sources(container_id)
    for datasource in datasources.value:
        if datasource.name == os.getenv('DATA_SOURCE_NAME'):
            data_source_id = datasource.id
    if data_source_id is None:
        datasource = datasources_api.create_data_source(
            deep_lynx.CreateDataSourceRequest(os.getenv('DATA_SOURCE_NAME'), 'standard', True), container_id)
        data_source_id = datasource.value.id

    return container_id, data_source_id, api_client


def main():
    """
    Supervisory Control start of execution
    """
    container_id, data_source_id, api_client = deep_lynx_init()
    os.environ["CONTAINER_ID"] = container_id
    os.environ["DATA_SOURCE_ID"] = data_source_id

    if api_client is None:
        # Connection to DeepLynx unsuccessful
        print("ERROR: Cannot connect to DeepLynx. Please see logs. Exiting...")
        logging.error("Cannot connect to DeepLynx. Exiting...")
        return

    print('Please start this application with the \'flask run\' command')
    logging.info('Please start this application with the \'flask run\' command')
    return


if __name__ == '__main__':
    main()
