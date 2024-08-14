# FROM ubuntu:16.04
FROM python:3.9

RUN addgroup appgroup
RUN adduser --disabled-password --home '/home/appuser' --ingroup appgroup appuser

USER appuser

RUN mkdir /app
WORKDIR /app
RUN chown appuser:appuser -R /app

# RUN apt-get -y update

COPY ./src /app
COPY ./requirements.txt ./app/requirements.txt
RUN pip install -r requirements.txt

CMD ["python", "./server.py"]
