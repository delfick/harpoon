#!/bin/bash -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

PUSH=0
CLEAN=0
while [[ ! -z $1 ]]; do
  case $1 in
    "-h"|"--help")
      echo "Usage: ./build.sh [--clean|--push|--help]"
      echo ""
      echo "Script to build the documentation"
      echo "It will create a virtualenv in the sphinx folder if one doesn't exist"
      echo ""
      echo "--clean"
      echo -e "\tRemove sphinx's cache first"
      echo ""
      exit 0
      ;;

    "--clean")
      CLEAN=1
      shift
      ;;

    *)
      echo "Unknown argument: $1"
      exit 1
      ;;
  esac
done

if [[ ! -d "$DIR/sphinx/venv" ]]; then
  echo "=========================================================================="
  echo "Making a virtualenv in sphinx/venv"
  echo "This is only done once and is required for the python dependencies"
  echo "Please wait a few minutes whilst this happens"
  echo "=========================================================================="
  echo ""

  if ! which virtualenv 2>&1 > /dev/null; then
    echo "Please install virtualenv and then run this"
    exit 1
  fi

  TMP_DIR="$DIR/sphinx/venv"
  if [[ ! -d $TMP_DIR ]]; then
    opts=""
    if [[ -f /usr/bin/python2.7 ]]; then
      question="
import sys
if sys.version.startswith('2.7'): sys.exit(1)
      "
      if python -c "$question"; then
        opts=" -p /usr/bin/python2.7"
      fi
    fi

    if ! virtualenv $opts $TMP_DIR; then
      echo "Couldn't make the virtualenv :("
      rm -rf $TMP_DIR
      exit 1
    fi
  fi

  source $TMP_DIR/bin/activate
  pip install -r sphinx/requirements.txt
  cd $DIR/..
  pip install -e .
fi

# use with --clean if you change anything in sphinx
if (($CLEAN==1)); then
  rm -rf sphinx/_build
fi

# Activate the virtualenv and build sphinx
source $DIR/sphinx/venv/bin/activate
pip install -r $DIR/sphinx/requirements.txt
cd $DIR/sphinx && pwd && $DIR/sphinx/venv/bin/sphinx-build -b html -d $DIR/sphinx/_build/doctrees . $DIR/sphinx/_build/html

