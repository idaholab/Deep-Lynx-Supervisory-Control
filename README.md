# DeepLynx Supervisory Control

The Deep Lynx Supervisory Control Adapter is a generic adapter that receives machine learning and physics data from DeepLynx, applies process control logic, and may create a control request for the DAQ/HMI to consume. It updates DeepLynx with the details of any control request created. 

This project is a [DeepLynx](https://github.com/idaholab/Deep-Lynx) adapter that utilizes the DeepLynx event system.

## Getting Started
To run this code, first copy the `.env_sample` file and rename it to `.env`. 
See the `.env_sample` file comments to determine configuration needs and guidelines.
Additionally, `.flaskenv` must be configured for this Flask app to run. Defaults are provided, but may be updated as needed.

Logs will be written to a logfile, stored in the root directory of the project. The log filename is set in `src/__init__.py` and is by default called `SupervisoryControl.log`.

* Complete the [Poetry installation](https://python-poetry.org/)
* All following commands are run in the root directory of the project:
    * Run `poetry install` to install the defined dependencies for the project.
    * Run `poetry shell` to spawn a shell.
    * Finally, run the project with the command `flask run`

## Contributing

This project uses [yapf](https://github.com/google/yapf) for formatting. Please install it and apply formatting before submitting changes (e.g. `yapf --in-place --recursive . --style={column_limit:120}`)

## Other Software
Idaho National Laboratory is a cutting edge research facility which is a constantly producing high quality research and software. Feel free to take a look at our other software and scientific offerings at:

[Primary Technology Offerings Page](https://www.inl.gov/inl-initiatives/technology-deployment)

[Supported Open Source Software](https://github.com/idaholab)

[Raw Experiment Open Source Software](https://github.com/IdahoLabResearch)

[Unsupported Open Source Software](https://github.com/IdahoLabCuttingBoard)

## License

Copyright 2023 Battelle Energy Alliance, LLC
