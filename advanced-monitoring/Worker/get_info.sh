#!/bin/bash
source ##WORKINGDIR##/venv/bin/activate
python3 ##WORKINGDIR##/get_cloud_info.py $1
#env $(cat .env | xargs) python3 main.py