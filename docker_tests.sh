#!/bin/bash

export BASE_TAG=buildroot-2014.02
export BASE_IMAGE=busybox:$BASE_TAG
export DOCKER_MACHINE_NAME=harpoon-tests

marks=""
if [[ -z $TOX ]]; then
    marks="-m integration"
fi

if [[ -z $CI_SERVER ]]; then
    if podman machine ls | grep $DOCKER_MACHINE_NAME; then
        if ! podman machine ls | grep $DOCKER_MACHINE_NAME | grep "Currently running"; then
            podman machine stop
            podman machine start $DOCKER_MACHINE_NAME
            podman system connect default $DOCKER_MACHINE_NAME
        fi
    else
        echo "Use podman machine to create an environment called '$DOCKER_MACHINE_NAME'"
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
exec ./test.sh $marks $@
