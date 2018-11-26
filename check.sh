#!/bin/bash

if ! pgrep -f "monitor.py" > /dev/null
then
    nohup /home/papes/git/epsolar-tracer/monitor.py & 
fi
