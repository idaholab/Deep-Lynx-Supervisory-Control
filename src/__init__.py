# Copyright 2023, Battelle Energy Alliance, LLC

import math
import os
import re
import logging
import json
import time
import numpy as np
import pandas as pd
import datetime
from flask import Flask, request, Response, json
import deep_lynx
import threading

from .supervisory_control import *
from .deep_lynx_query import *

# Global variables
api_client = None
lock_ = threading.Lock()
threads = list()
number_of_files = 1
upper_limit_control_request_sent = False
lower_limit_control_request_sent = False

# configure logging. to overwrite the log file for each run, add option: filemode='w'
log_file_name = 'SupervisoryControl.log'
logging.basicConfig(filename=log_file_name,
                    level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(message)s',
                    filemode='w',
                    datefmt='%m/%d/%Y %H:%M:%S')

print(f'Application started. Logging to file {log_file_name}')


def create_app():
    """ This file and aplication is the entry point for the `flask run` command """
    global upper_limit_control_request_sent
    global lower_limit_control_request_sent

    app = Flask(os.getenv('FLASK_APP'), instance_relative_config=True)

    # Purpose to run flask once (not twice)
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        # Instantiate deep_lynx
        container_id, data_source_id, api_client = deep_lynx_init()
        os.environ["CONTAINER_ID"] = container_id
        os.environ["DATA_SOURCE_ID"] = data_source_id

        register_for_event(api_client)

        # A mount point is a directory (typically an empty one) in the currently accessible filesystem on which an additional filesystem is mounted (i.e., logically attached).
        mount_point = os.getenv("MOUNT_DIRECTORY")
        print("Mount directory exists", os.path.exists(mount_point))
        # Create mount point if does not exist
        if not os.path.exists(mount_point):
            os.makedirs(mount_point)

        # Unmount moint point
        unmount_command = "umount " + mount_point
        rete = os.system(unmount_command)
        print("Un-mount return", rete)

        # "mount_smbfs" command mounts a share from a remote server
        mount_command = "mount_smbfs " + os.getenv("SERVER_PATH") + " " + mount_point
        return_value = os.system(mount_command)
        print("Mount return", return_value)

        mr_mount_point = os.getenv("MR_MOUNT_DIRECTORY")
        if not os.path.exists(mr_mount_point):
            os.makedirs(mr_mount_point)

        # Unmount moint point
        mr_unmount_command = "umount " + mr_mount_point
        mr_rete = os.system(mr_unmount_command)
        print("MR Un-mount return", mr_rete)

        # "mount_smbfs" command mounts a share from a remote server
        mr_mount_command = "mount_smbfs " + os.getenv("MR_SERVER_PATH") + " " + mr_mount_point
        mr_return_value = os.system(mr_mount_command)
        print("MR Mount return", mr_return_value)

    @app.route('/supervisorycontrol', methods=['POST'])
    def events():
        global upper_limit_control_request_sent
        global lower_limit_control_request_sent
        """ 
        Receving function for events from DeepLynx.
        This function acts on file_created events and retrieves the file provided.
        It then validates file type, name, and saves locally if a match is found.
        It then applies the provided thresholds and determines if a control request should be created.
        If a request is generated, the control request file is written and also sent to DeepLynx.
        """
        if 'application/json' not in request.content_type:
            logging.warning('Received /events request with unsupported content type')
            return Response('Unsupported Content Type. Please use application/json', status=400)

        data = request.get_json()
        print(data)
        logging.info('Received event with data: ' + json.dumps(data))

        # Get file_id from event
        try:
            file_id = data["query"]["fileID"]
        except KeyError:
            logging.info('Received event without file_id')
            return Response(response=json.dumps({'received': True}), status=200, mimetype='application/json')

        # Retrieve file from DL
        data_sources_api = deep_lynx.DataSourcesApi(api_client)
        dl_file_path, ml_file_name = retrieve_file(data_sources_api, file_id)
        print(dl_file_path)

        # First validate that file is of type csv
        split_tup = os.path.splitext(dl_file_path)
        if split_tup[1] != '.csv':
            logging.info(f'Received non-csv file {dl_file_path}. Returning.')
            return Response(response=json.dumps({'received': True}), status=200, mimetype='application/json')

        # Then read retrieved file
        file_df = pd.read_csv(dl_file_path)

        # Flags to mark which filetype is being retrieved
        moose_df = False
        ml_df = False

        # Placeholder for the file to be read that is not being currently retrieved
        second_df = None

        # Write file locally (keep one copy each of latest ML and MOOSE)
        if re.search(os.getenv("MOOSE_FILE_PATTERN"), dl_file_path) is not None:
            file_df.to_csv(os.getenv("MOOSE_FILE"), index=False)
            moose_df = True
            logging.info('Received MOOSE file.')

        elif re.search(os.getenv("ML_FILE_PATTERN"), dl_file_path) is not None:
            file_df.to_csv(os.getenv("ML_FILE"), index=False)
            ml_df = True
            logging.info('Received ML file.')

        else:
            # File retrieved does not match a file pattern. exit
            logging.info(f'Received file {dl_file_path} that does not match any file pattern. Returning.')
            return Response(response=json.dumps({'received': True}), status=200, mimetype='application/json')

        # Read latest of each (if available), using retrieved file
        if moose_df:
            path = os.path.join(os.getcwd() + '/' + os.getenv("ML_FILE"))
            if os.path.exists(path):
                second_df = pd.read_csv(path)
        elif ml_df:
            path = os.path.join(os.getcwd() + '/' + os.getenv("MOOSE_FILE"))
            if os.path.exists(path):
                second_df = pd.read_csv(path)

        # Vectorize limit functions for future use
        upper_vect_func = np.vectorize(greater_than, otypes=[np.float], cache=False)
        lower_vect_func = np.vectorize(less_than, otypes=[np.float], cache=False)

        # Filter columns for upper and lower limit dataframes
        file_columns = file_df.columns
        upper_limit_df = file_df.copy(deep=True)
        lower_limit_df = file_df.copy(deep=True)
        # Exclude/include certain columns from examination
        upper_limit_df = upper_limit_df.loc[:, [
            x not in json.loads(os.getenv("UPPER_LIMIT_SKIP_COLUMNS")) for x in file_columns
        ]]
        lower_limit_df = lower_limit_df.loc[:, [
            x in json.loads(os.getenv("LOWER_LIMIT_INCLUDE_COLUMNS")) for x in file_columns
        ]]
        print(upper_limit_df.head())
        print(lower_limit_df.head())

        # Column header in the first tuple slot [0], list of values in second [1]
        upper_limit_items = [(item[0], item[1]) for item in upper_limit_df.items()]
        lower_limit_items = [(item[0], item[1]) for item in lower_limit_df.items()]

        # DateTime list for future use
        # Assumption that the time column is the first column of incoming data
        times = file_df.loc[:, [x in json.loads(os.getenv("TIME_COLUMN")) for x in file_columns]]
        print(times.head())

        # Flags for future use
        upper_met = False
        lower_met = False
        value = None
        event_date = None
        sensor = None

        for x in upper_limit_items:
            sensor_name = x[0]

            upper_results = np.array(upper_vect_func(x[1], float(os.getenv("UPPER_LIMIT"))))

            # NaN indicates the threshold has not been met. If other values are found, the threshold has been exceeded
            for index, result in enumerate(upper_results):

                if not math.isnan(result):
                    upper_met = True

                    # only provide one value and event_date, which should be the first instance exceeding a threshold
                    if value is None:
                        value = result
                        event_date = float(times.iloc[index])
                        sensor = sensor_name

                    logging.info(f'Upper limit threshold exceeded at {event_date} on {sensor_name}. Value: {result}')

        for x in lower_limit_items:
            # (If above condition not met) If any temp is less than lower limit, create request to raise power
            if not upper_met:
                sensor_name = x[0]

                lower_results = np.array(lower_vect_func(x[1], float(os.getenv("LOWER_LIMIT"))))

                # NaN indicates the threshold has not been met. If other values are found, the threshold has been exceeded
                for index, result in enumerate(lower_results):

                    if not math.isnan(result):
                        lower_met = True

                        # only provide one value and event_date, which should be the first instance exceeding a threshold
                        if value is None:
                            value = result
                            event_date = float(times.iloc[index])
                            sensor = sensor_name

                        logging.info(
                            f'Lower limit threshold exceeded at {event_date} on {sensor_name}. Value: {result}')

        # Form file containing contents of request, write to directory (for now)
        # out_file = os.path.join(os.getcwd() + '/' + os.getenv("OUTPUT_FILE"))

        if upper_met:
            # TODO: Update instruction to match adjustment
            instruction = f'Upper limit {os.getenv("UPPER_LIMIT")} threshold exceeded. Lower power to {os.getenv("CONTROL_REQUEST_ADJUSTMENT")} C.'

            print("upper_limit_control_request_sent", upper_limit_control_request_sent)
            if not upper_limit_control_request_sent:
                write_file()
                upper_limit_control_request_sent = True

                # Send request contents to DeepLynx
                deep_lynx_import('upper limit', instruction, float(os.getenv("UPPER_LIMIT")), sensor, value,
                                 str(event_date), ml_file_name)

        elif lower_met:
            # TODO: Update instruction to match adjustment
            instruction = f'Lower limit {os.getenv("LOWER_LIMIT")} threshold exceeded. Raise power to {os.getenv("CONTROL_REQUEST_ADJUSTMENT")} C.'

            print("lower_limit_control_request_sent", lower_limit_control_request_sent)
            if not lower_limit_control_request_sent:
                write_file()
                lower_limit_control_request_sent = True

                # Send request contents to DeepLynx
                deep_lynx_import('lower limit', instruction, float(os.getenv("LOWER_LIMIT")), sensor, value,
                                 str(event_date), ml_file_name)

        return Response(response=json.dumps({'received': True}), status=200, mimetype='application/json')

    return app


def deep_lynx_import(name: str, instruction: str, threshold: str, sensor: str, value: str, event_date: str,
                     ml_file_name: str):
    """
    Puts together a control request object for import to DeepLynx.
    Args
        name (string): name of the control request
        instruction (string): the control request description to be displayed in the user interface
        file_path (string): path where the control request file was written
        threshold (string): the threshold that was reached
        value (string): the value indicated by a forecast/prediction that exceeds a threshold
        event_date (string): the time at which the value was predicted
    """
    control_request = list()

    payload = {
        'name': name,
        'instruction': instruction,
        'threshold': threshold,
        'primary_text': sensor,
        'value': value,
        'event_date': event_date,
        'creation_user': 'SUPERVISORY_CONTROL_ADAPTER',
        'creation_date': datetime.datetime.now(),
        'file_name': ml_file_name
    }

    control_request.append(payload)

    print(control_request)

    data_sources_api = deep_lynx.DataSourcesApi(api_client)
    import_result = data_sources_api.create_manual_import(body=control_request,
                                                          container_id=os.getenv("CONTAINER_ID"),
                                                          data_source_id=os.getenv("DATA_SOURCE_ID"))

    logging.info(f'Import to DeepLynx: {import_result}')
    print(f'Import to DeepLynx: {import_result}')

    # Write file containing control request for use by MR Import to mount directory
    file_name = "Supervisory_Control_" + str(event_date) + ".json"

    mr_mount_file_path = os.path.join(os.getenv("MR_MOUNT_DIRECTORY"), file_name)

    f = open(mr_mount_file_path, "w")
    json.dump(control_request, f, indent=4)
    f.close()


def greater_than(x, upper_limit: float):
    """
    Compares if the supplied value is greater than the supplied limit
    Args
        x (string or number): the value to be compared
        upper_limit (float): the limit to compare against
    Return
        x if limit exceeded, else NaN
    """
    if float(x) > upper_limit:
        return x
    else:
        return np.NaN


def less_than(x, lower_limit: float):
    """ Compares if the supplied value is less than the supplied limit
    Args
        x (string or number): the value to be compared
        lower_limit (float): the limit to compare against
    Return
        x if limit exceeded, else NaN
    """
    if float(x) < lower_limit:
        return x
    else:
        return np.NaN


def register_for_event(api_client: deep_lynx.ApiClient, iterations=30):
    """ Register with Deep Lynx to receive manual events on applicable data sources """
    registered = False

    # List of adapters to receive events from
    data_ingested_adapters = json.loads(os.getenv("DATA_SOURCES"))

    while registered == False and iterations > 0:
        # Get a list of data sources and validate that no error occurred
        datasource_api = deep_lynx.DataSourcesApi(api_client)
        data_sources = datasource_api.list_data_sources(os.getenv("CONTAINER_ID"))

        if data_sources.is_error == False:
            for data_source in data_sources.value:
                # If the data source is found, create a registered event
                if data_source.name in data_ingested_adapters:

                    events_api = deep_lynx.EventsApi(api_client)

                    # verify that this event action does not already exist
                    # by comparing to the established event action we would like to create
                    # TODO: Update to file created event
                    event_action = deep_lynx.CreateEventActionRequest(
                        data_source.container_id, data_source.id, "file_created", "send_data", None, "http://" +
                        os.getenv('FLASK_RUN_HOST') + ":" + os.getenv('FLASK_RUN_PORT') + "/supervisorycontrol",
                        os.getenv("DATA_SOURCE_ID"), True)

                    actions = events_api.list_event_actions()
                    for action in actions.value:

                        # if destination, event_type, and data_source_id match, we know that this
                        # event action already exists
                        if action.destination == event_action.destination and action.event_type == event_action.event_type \
                            and action.data_source_id == event_action.data_source_id:
                            # this exact event action already exists, remove data source from list
                            logging.info('Event action on ' + data_source.name + ' already exists')
                            data_ingested_adapters.remove(data_source.name)

                    # continue event action creation if the same was not already found
                    if data_source.name in data_ingested_adapters:
                        create_action_result = events_api.create_event_action(event_action)

                        if create_action_result.is_error:
                            logging.warning('Error creating event action: ' + create_action_result.error)
                        else:
                            logging.info('Successful creation of event action on ' + data_source.name + ' datasource')
                            data_ingested_adapters.remove(data_source.name)

                    # If all events are registered
                    if len(data_ingested_adapters) == 0:
                        registered = True
                        logging.info('Successful registration on all adapters')
                        return registered

        # If the desired data source and container is not found, repeat
        logging.info(
            f'Datasource(s) {", ".join(data_ingested_adapters)} not found. Next event registration attempt in {os.getenv("REGISTER_WAIT_SECONDS")} seconds.'
        )
        time.sleep(float(os.getenv('REGISTER_WAIT_SECONDS')))
        iterations -= 1

    return registered


def write_file():
    global number_of_files
    instruction = os.getenv("CONTROL_REQUEST_ADJUSTMENT")
    base, ext = os.path.splitext(os.getenv("OUTPUT_FILE"))

    output_file = os.getenv("MOUNT_DIRECTORY") + base + "_" + str(number_of_files) + ext
    print(output_file)
    f = open(output_file, "w")
    f.write(instruction)
    f.close()
    number_of_files += 1
