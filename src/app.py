import os
from pathlib import Path
from bottle import abort
import logging
import traceback

import data_util
from s3_util import download_files
from misc_util import str_to_bool

from config import APP_CONFIG

logging.basicConfig(level=APP_CONFIG["LOG_LEVEL"])


class App:
    def __init__(self, *args, **kwargs):
        # set up cache dir
        if not os.path.exists(APP_CONFIG["CACHE_DIR"]):
            os.makedirs(APP_CONFIG["CACHE_DIR"])

    def _prune_cache(self):
        cache_dir = APP_CONFIG["CACHE_DIR"]
        max_cache = APP_CONFIG["MAX_CACHE"]

        # get list of cached files sorted by last modified time
        paths = sorted(Path(cache_dir).iterdir(), key=os.path.getmtime, reverse=True)

        # find how many are over our max and delete the least recently modified ones
        diff_count = len(paths) - max_cache
        if diff_count > 0:
            del_list = paths[-diff_count:]
            for del_file in del_list:
                logging.info(f"Removing file from cache: {del_file}")
                Path.unlink(del_file)

    def get_data(self, request):
        # check for params
        if request.query.get("files") is None:
            abort(400, "missing query parameter")

        # pull out parameters from the request
        file_list = request.query.get("files").split(",")
        output_format = (
            request.query.get("format")
            if request.query.get("format")
            else APP_CONFIG["DEFAULT_FORMAT"]
        )
        keep_fill = str_to_bool(request.query.get("fill"))

        try:
            # download the files to our cache
            if len(file_list) == 0:
                abort(400, "no files specified")
            local_files = download_files(file_list)

            # compile all the data together
            data = data_util.get_plot_data(local_files, remove_fill=not keep_fill)
        except:
            traceback.print_exc()
            abort(500, "something went wrong")

        # prune cached data
        self._prune_cache()

        # return processed data
        json_data = data_util.dump_plot_data(data)
        return (json_data, output_format)
