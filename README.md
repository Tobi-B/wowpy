# wowpy
Python package for simple robot control with blockpy etc.

## Features
- Control blocks for wowwee MIP robot
- Bindings for Blockly programming language
- More robots evailable soon

## Quick start
```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[test]"
.venv\Scripts\python.exe -m wowpy.dashboard      # browser dashboard on http://127.0.0.1:8000
.venv\Scripts\python.exe main.py                 # minimal script example
```

## Dependencies
- bleak, fastapi, uvicorn
