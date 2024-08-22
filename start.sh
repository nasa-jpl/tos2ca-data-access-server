#! /bin/bash

echo "sourcing .env"
set -a
source .env
set +a

echo "starting containers"
docker run -d \
    -e APP_CACHE_DATA=${APP_CACHE_DATA} \
    -e APP_CACHE_ITEM_MAX=${APP_CACHE_ITEM_MAX} \
    -e APP_S3_BUCKET=${APP_S3_BUCKET} \
    -e APP_LOG_LEVEL=${APP_LOG_LEVEL} \
    -e APP_PORT=${APP_PORT} \
    -e APP_LOCAL_ONLY=${APP_LOCAL_ONLY} \
    -v ${APP_CACHE_DIR}:/app_data_cache \
    --expose ${APP_PORT} \
    --name data_access_server_app \
    data_access_server_app

echo "pausing..."
sleep 5

docker run -d \
    -p ${APP_PORT}:80 \
    --name data_access_server_proxy \
    data_access_server_proxy