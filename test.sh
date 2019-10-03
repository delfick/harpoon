#!/bin/bash
exec pytest -q -m "not integration" $@
