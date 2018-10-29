#!/bin/bash

export BASE_TAG=buildroot-2014.02
export BASE_IMAGE=busybox:$BASE_TAG

exclusions=""
if [[ -z $TOX ]]; then
  exclusions="--only-include-filename test_docker_*.py"
fi

if [[ -z $CI_SERVER ]]; then
  if docker-machine ls | grep harpoon-tests; then
    if [[ $(docker-machine status harpoon-tests) != "Running" ]]; then
      if ! docker-machine start harpoon-tests; then
        echo "Couldn't start harpoon-tests"
        exit 1
      fi
    fi
    captured=$(docker-machine env harpoon-tests --shell sh)
    if [[ $? != 0 ]]; then
      echo -e $captured
      echo "Failed to do harpoon-tests environment"
      exit 1
    else
      eval $captured
    fi
  else
    echo "Use docker-machine to create an environment called 'harpoon-tests'"
    exit 1
  fi
fi

docker ps -aq | xargs docker kill
docker ps -aq | xargs docker rm
docker images | grep -v $BASE_TAG | grep -v python | awk '{print $3}' | tail -n +2 | xargs docker rmi
docker network ls -q | xargs docker network rm

if [[ $(docker inspect $BASE_IMAGE | grep Id | cut -d'"' -f4) != "sha256:9875fb006e07a63f7e2a1713a8a73c71663be95bce7c122a36205cd1cd9c93eb" ]]; then
  echo "Making sure we have a base docker image"
  docker pull $BASE_IMAGE
fi

# We also need the python:3 image
docker pull python:3

export DESTRUCTIVE_DOCKER_TESTS=true
nosetests --exclude-path harpoon --exclude-path docs --with-noy $exclusions --with-focus $@
