from bottle import Bottle, run, request, response
from app import App

from config import APP_CONFIG

bottle_app = Bottle()
dataApp = App()

@bottle_app.hook("before_request")
def strip_path():
    request.environ["PATH_INFO"] = request.environ["PATH_INFO"].rstrip("/")


@bottle_app.hook("after_request")
def enable_cors():
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET"
    response.headers["Access-Control-Allow-Headers"] = (
        "Origin, Accept, Content-Type, X-Requested-With, X-CSRF-Token"
    )


@bottle_app.route("/getData")
def get_data():
    (data, output_format) = dataApp.get_data(request)
    response.content_type = output_format
    return data


def main():
    run(
        bottle_app,
        host="0.0.0.0",
        port=APP_CONFIG["APP_PORT"],
        server="gunicorn",
        workers=5,
        timeout=900,
    )


if __name__ == "__main__":
    main()
