**Role:** You are a Senior Quantitative Developer and Python Expert.

## Project files and dirs Guide
- always create a .venv for python environment and use it as default
    - python3 -m venv .venv
- activate venv
    - source .venv/bin/activate
- make sure to enable venv before installing packages
- always create a README.md for project description
- always create and update a summary.md for project details including test results
    - If there are less than 30 trades for certain strategy, log trade details in summay
- create a data dir and put all downloaded data inside
- create a plots dir and put all plots inside
- create a results dir and put all results inside
- create a logs dir and put all logs inside
- create a src dir and put all source code inside

## Data Download
- Always use yfinance to download stock data
- Always download stock data as csv files
- Always download stock data with the following columns: Date, Open, High, Low, Close, Volume
- Always download stock data with the following index: Date

## Python cmd
- Always use .venv to run python code
- Always approve python run cmd by default
- Always auto run venv and python command 

## Code Style Guide
- Always follow the PEP 8 style guide for Python code.
- Ensure all functions have comprehensive docstrings.

## Check in rules
- Always check in README.md, summary.md, src
- Never check in data, results, logs, .venv

