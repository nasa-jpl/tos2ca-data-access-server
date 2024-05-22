import os
import json
import time as pytime
from json import JSONEncoder
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from netCDF4 import Dataset, default_fillvals
import logging

from misc_util import to_title


class NumpyArrayEncoder(JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return super(NumpyArrayEncoder, self).default(obj)


def walktree(top):
    yield top.groups.values()
    for value in top.groups.values():
        yield from walktree(value)


def get_data_from_file(filename):
    varset = OrderedDict()

    if os.path.isfile(filename):
        nc = Dataset(filename)
        nc.set_auto_mask(False)
        for children in walktree(nc):
            for child in children:
                if len(child.groups) == 0 and child.name != "navigation":
                    for var_name in child.variables:
                        variable = child.variables[var_name]

                        # collect time and phenomenon id into arrays
                        (time, id) = child.path.strip("/").split("/")
                        time_arr = np.full(len(variable), int(time), dtype=int)
                        id_arr = np.full(len(variable), int(id), dtype=int)

                        # init accumulator
                        if var_name not in varset:
                            units = variable.Units

                            # get fill value from defaults because it doesn't respect the metadata
                            dtype = variable.dtype.str.replace("<", "").replace(
                                ">", ""
                            )  # ignore byteorder char
                            fv = default_fillvals[dtype]

                            varset[var_name] = {
                                "values": variable,
                                "times": time_arr,
                                "phenom_ids": id_arr,
                                "fill_val": fv,
                                "units": units,
                            }
                        else:
                            varset[var_name]["values"] = np.concatenate(
                                (
                                    varset[var_name]["values"],
                                    variable,
                                )
                            )
                            varset[var_name]["times"] = np.concatenate(
                                (
                                    varset[var_name]["times"],
                                    time_arr,
                                )
                            )
                            varset[var_name]["phenom_ids"] = np.concatenate(
                                (
                                    varset[var_name]["phenom_ids"],
                                    id_arr,
                                )
                            )
    else:
        logging.error(f"{filename} is not a file")

    return varset


def get_plot_data(file_list=[], remove_fill=False):
    logging.info(f"Collecting plot data for: {file_list}")
    p_start_time = pytime.time()

    if not isinstance(file_list, list):
        file_list = [file_list]

    # multi-thread the data collection
    datasets = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        for i in executor.map(get_data_from_file, file_list):
            datasets.append(i)

    # collapse all the file contents into a single dict for ease
    varset = OrderedDict()
    for dataset in datasets:
        for varname in dataset:
            varset[varname] = dataset[varname]

    # stack all the variable values together into a single nD array
    plotset = {}
    for var_name in varset:
        vals = varset[var_name]["values"][:, 2]  # grab the value column
        if "values" not in plotset:
            plotset["title"] = to_title(var_name)
            plotset["values"] = vals
            plotset["axis_labels"] = [f'{var_name} ({varset[var_name]["units"]})']
        else:
            plotset["title"] = f'{plotset["title"]} x {to_title(var_name)}'
            plotset["values"] = np.c_[plotset["values"], vals]
            plotset["axis_labels"].append(f'{var_name} ({varset[var_name]["units"]})')

    # stack in the lat, lon, time, and phenom ids and pull fill value
    fill_value = None
    for var_name in varset:
        lat_lon = varset[var_name]["values"][:, :2]  # grab the first two columns
        plotset["values"] = np.c_[
            plotset["values"],
            lat_lon,
            varset[var_name]["times"],
            varset[var_name]["phenom_ids"],
        ]
        fill_value = varset[var_name]["fill_val"]
        break  # all the lats, lons, times, IDs, and fill values should match so we just need to do this once

    # optionally remove rows that contain the fill value
    if remove_fill:
        expected_fill = (
            -9999.0
        )  # TODO - figure out why there are apparently multiple fill values?
        mask = ~(
            np.logical_or(
                plotset["values"] == fill_value, plotset["values"] == expected_fill
            )
        )
        if len(varset) > 1:
            plotset["values"] = plotset["values"][np.all(mask, axis=1), :]
        else:
            plotset["values"] = plotset["values"][mask]

    logging.info(
        f"{file_list} Done. Elapsed time: {pytime.time() - p_start_time} seconds"
    )
    return plotset


def dump_plot_data(plotData):
    return json.dumps(plotData, cls=NumpyArrayEncoder)
