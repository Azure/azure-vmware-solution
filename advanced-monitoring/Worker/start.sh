#!/bin/bash
source ./venv/bin/activate
python3 main.py
#env $(cat .env | xargs) python3 main.py