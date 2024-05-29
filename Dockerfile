# FROM ubuntu:16.04
FROM python:3.9-bullseye

RUN apt-get -y update

COPY ./requirements.txt ./
RUN pip install -r requirements.txt

COPY ./src /app

WORKDIR /app

CMD ["python", "./server.py"]
