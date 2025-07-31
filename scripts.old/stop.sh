#! /bin/bash

echo "sourcing .env"
set -a
source .env
set +a

echo "stopping containers"
docker stop data_access_server_app
docker stop data_access_server_proxy

echo "pausing..."
sleep 3

echo "removing containers"
docker rm data_access_server_app
docker rm data_access_server_proxy

# echo "pausing..."
# sleep 3

# echo "removing network"
# docker network rm app_services_network
