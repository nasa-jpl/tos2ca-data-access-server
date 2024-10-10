# FROM ubuntu:16.04
FROM python:3.12

RUN apt-get -y update

COPY ./requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

RUN mkdir /app
COPY ./src /app
WORKDIR /app

ENV HDF5_USE_FILE_LOCKING=FALSE

CMD ["python", "./server.py"]
