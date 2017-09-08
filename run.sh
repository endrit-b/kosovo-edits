source ./venv/bin/activate
python main.py &
echo $! > pid
exit 0
