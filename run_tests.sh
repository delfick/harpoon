#!/bin/bash

set -e

info=$(mktemp)
cleanup() { rm $info; }
trap cleanup EXIT

# container_manager will exit with an error status if we couldn't start
# The container manager. But because we gave it just a file, it'll run the
# web server in the background and the script will continue
harpoon container_manager $info

PORT=$(head -n1 $info)
export MANAGER_URI="http://localhost:$PORT"

cleanup() {
    if ! rm $info; then
        echo "Failed to remove temporary file at $info"
    fi
    curl "$MANAGER_URI/shutdown"
}
trap cleanup EXIT

# Run tests
./test.sh
