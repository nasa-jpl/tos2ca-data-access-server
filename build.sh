echo "pulling containers"
docker build -t data_access_server_proxy -f Dockerfile.proxy .

echo "building containers"
docker build -t data_access_server_app -f Dockerfile.app .

# echo "creating network"
# docker network create -d bridge app_services_network
