#!/usr/bin/env bash
SCRIPT_PATH=$(dirname $0)

echo "Cleanup old Python Virtual-Environment..."
/usr/bin/rm -rf $SCRIPT_PATH/.venv

echo "Initialize Python Virtual-Environment..."
/usr/bin/python3 -m venv $SCRIPT_PATH/.venv

echo "Joining Python Virtual-Environment..."
source $SCRIPT_PATH/.venv/bin/activate

echo "Install requirments via pip3 and requirements.txt..."
echo
$SCRIPT_PATH/.venv/bin/pip3 install --requirement $SCRIPT_PATH/requirements-venv.txt

echo "Initialization finished! Activate virtual environment via: source .venv/bin/activate"
