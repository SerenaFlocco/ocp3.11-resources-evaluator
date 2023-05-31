# OCP 3.11 Resource Evaluator

## Purpose
This tool has been developed in order to extract a list of information regarding resources dimensioning and usage for different applications running in a OCP 3.11 cluster.

## Usage
Create a virtual environment:
`python3 -m venv env`

Activate it:
`source env/bin/activate`

Install required dependencies:
`python3 -m pip install -r requirements.txt`

In the project folder, create a file named *acronyms.txt* containing the list of acronyms (i.e. application names) for which you want to extract the information.

Run the script:
`API_URL=<cluster_api_url> USER=<your_username> PWD=<your_password> python3 ./resource-evaluator.py`

At the end of the execution, you will find the results of the extraction in a file named *output.csv*.