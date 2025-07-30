# TOS2CA Data Access Server

Simple Python application served with Bottle via an NGINX proxy. The application provides and API to pull interpolated data files from S3 and repackage the contents for charting in a web-browser application. It relies on the following technologies:

- Docker
- NGINX
- Python
- Bottle
- Boto3
- NetCDF
- Numpy
- Pandas

### Getting started

- Get Docker
- Update the `.env` file
- run `docker compose build`

### Deployment

- Update the `.env` file
- run `docker compose up`

### Alternate in case of no `docker compose` support

 - `./scripts.old/build.sh` - to build images and setup container network
 - `./scripts.old/start.sh` - to start the containers
 - `./scripts.old/stop.sh` - to stop the containers
