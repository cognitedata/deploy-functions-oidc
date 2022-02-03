#!/bin/bash

for FUNCTION in example_function1 example_function2
do
	poetry export -f requirements.txt --without-hashes > $FUNCTION/requirements.txt
done
