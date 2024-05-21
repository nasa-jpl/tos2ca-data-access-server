import os
import json
import time as pytime
from json import JSONEncoder
from collections import OrderedDict
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


def get_plot_data(file_list=[], remove_fill=False):
    logging.info(f"Collecting plot data for: {file_list}")
    p_start_time = pytime.time()

    if not isinstance(file_list, list):
        file_list = [file_list]

    fill_value = None
    varset = OrderedDict()  # use OrderedDict to preserve input file list order
    for filename in file_list:
        if os.path.isfile(filename):
            nc = Dataset(filename)
            nc.set_auto_mask(False)
            for children in walktree(nc):
                for child in children:
                    if len(child.groups) == 0 and child.name != "navigation":
                        for var_name in child.variables:
                            variable = child.variables[var_name]

                            # init variable value tracking
                            if var_name not in varset:
                                varset[var_name] = {
                                    "values": np.array([]),
                                    "times": np.array([]),
                                    "phenom_ids": np.array([]),
                                }

                            # add fill value and units string
                            if (
                                "fill_val" not in varset[var_name]
                                or "units" not in varset[var_name]
                            ):
                                try:
                                    # get fill value from defaults because it doesn't respect the metadata
                                    dtype = variable.dtype.str.replace("<", "").replace(
                                        ">", ""
                                    )  # ignore byteorder char
                                    fv = default_fillvals[dtype]
                                    varset[var_name]["fill_val"] = fv

                                    units = variable.Units
                                    varset[var_name]["units"] = units

                                    # check if this fill value is the same as the others
                                    if fill_value == None:
                                        fill_value = fv
                                    elif fill_value != fv:
                                        logging.warn(
                                            f"WARNING: mismatched fill values f{fill_value}, {fv}"
                                        )
                                        remove_fill = False

                                except AttributeError:
                                    continue

                            # collect measurement values
                            new_vals = variable[:, 2]
                            varset[var_name]["values"] = np.concatenate(
                                (
                                    varset[var_name]["values"],
                                    new_vals,
                                )
                            )

                            # collect time and phenomenon id
                            (time, id) = child.path.strip("/").split("/")
                            time_arr = np.full(new_vals.shape, int(time), dtype=int)
                            id_arr = np.full(new_vals.shape, int(id), dtype=int)
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
            print(f"{filename} is not a file")

    # stack all the variable values together into a single nD array
    plotset = {}
    for var_name in varset:
        if "values" not in plotset:
            plotset["title"] = to_title(var_name)
            plotset["values"] = varset[var_name]["values"]
            plotset["axis_labels"] = [f'{var_name} ({varset[var_name]["units"]})']
        else:
            plotset["title"] = f'{plotset["title"]} x {to_title(var_name)}'
            plotset["values"] = np.c_[plotset["values"], varset[var_name]["values"]]
            plotset["axis_labels"].append(f'{var_name} ({varset[var_name]["units"]})')

    # stack in the time and phenom ids
    for var_name in varset:
        plotset["values"] = np.c_[
            plotset["values"], varset[var_name]["times"], varset[var_name]["phenom_ids"]
        ]
        break  # all the times and IDs should match so we just need to do this once

    # optionally remove rows that contain the fill value
    # TODO - figure out why there are apparently multiple fill values?
    if remove_fill:
        expected_fill = -9999.0
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
