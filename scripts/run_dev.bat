@echo off
pushd "%~dp0.."
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
python -m ncepu_cloud_client.main
popd
