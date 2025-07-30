
echo "building containers"

docker build -t tos2ca_data_access_server_proxy -f Dockerfile.proxy --platform linux/amd64 .
docker build -t tos2ca_data_access_server_app -f Dockerfile.app --platform linux/amd64 .

# echo "creating network"
# docker network create -d bridge app_services_network
