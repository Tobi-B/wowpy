# wowpy
Python package for simple robot control with blockpy etc.

## Features
- Python control of the WowWee MiP robot over Bluetooth LE
- Browser dashboard: a button for every MiP command, live status and decoded log
- Blockly editor: build programs from blocks, compose your own blocks, run them on the robot
- Mock robot so everything works without hardware
- More robots available soon

## Quick start
```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[test]"
.venv\Scripts\python.exe -m wowpy.dashboard      # dashboard on http://127.0.0.1:8000, blocks at /blocks
.venv\Scripts\python.exe main.py                 # minimal script example
```

## Dependencies
- bleak, fastapi, uvicorn
