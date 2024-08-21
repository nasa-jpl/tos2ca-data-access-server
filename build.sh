echo "pulling containers"
docker pull nginx:1.24.0

echo "building containers"
docker build -t data_access_server .

# echo "creating network"
# docker network create -d bridge app_services_network
