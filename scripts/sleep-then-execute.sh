#!/bin/bash

# This script is used in dry-run mode to add a delay before executing a command.

delay=$1
shift

sleep -- "$delay"
exec "$@"
