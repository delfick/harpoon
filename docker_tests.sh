#!/bin/bash

export BASE_IMAGE=busybox:buildroot-2014.02

if docker-machine ls | grep harpoon-tests; then
  eval $(docker-machine env harpoon-tests)
  docker ps -aq | xargs docker kill
  docker ps -aq | xargs docker rm
  docker images | awk '{print $1}' | tail -n +2 | grep -v busybox | xargs docker rmi

  if [[ $(docker inspect $BASE_IMAGE | grep Id | cut -d'"' -f4) != "8c2e06607696bd4afb3d03b687e361cc43cf8ec1a4a725bc96e39f05ba97dd55" ]]; then
    echo "Making sure we have a base docker image"
    docker pull $BASE_IMAGE
  fi
else
  echo "Use docker-machine to create an environment called 'harpoon-tests'"
  exit 1
fi

export DESTRUCTIVE_DOCKER_TESTS=true
nosetests --exclude-path harpoon --exclude-path docs --with-noy --only-include-filename "test_docker_*.py" $@

