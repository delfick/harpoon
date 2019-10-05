#!/bin/bash

export BASE_TAG=buildroot-2014.02
export BASE_IMAGE=busybox:$BASE_TAG
export DOCKER_MACHINE_NAME=harpoon-tests

marks=""
if [[ -z $TOX ]]; then
    marks="-m integration"
fi

if [[ -z $CI_SERVER ]]; then
    if docker-machine ls | grep $DOCKER_MACHINE_NAME; then
        if [[ $(docker-machine status $DOCKER_MACHINE_NAME) != "Running" ]]; then
            if ! docker-machine start $DOCKER_MACHINE_NAME; then
                echo "Couldn't start $DOCKER_MACHINE_NAME"
                exit 1
            fi
        fi
        captured=$(docker-machine env $DOCKER_MACHINE_NAME --shell sh)
        if [[ $? != 0 ]]; then
            echo -e $captured
            echo "Failed to do $DOCKER_MACHINE_NAME environment"
            exit 1
        else
            eval $captured
        fi
    else
        echo "Use docker-machine to create an environment called '$DOCKER_MACHINE_NAME'"
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
if [[ -z $DONT_PULL_PYTHON ]]; then
    docker pull python:3
fi

export DESTRUCTIVE_DOCKER_TESTS=true
exec pytest -q $marks $@
