import os
import json
import time as pytime
from collections import OrderedDict
from functools import partial
from multiprocessing import pool as mp_pool
import pandas as pd
import numpy as np
from netCDF4 import Dataset
import logging

from misc_util import to_title


def walktree(top):
    yield top.groups.values()
    for value in top.groups.values():
        yield from walktree(value)


def get_data_from_file(filename, times=None):
    statset = OrderedDict()

    if os.path.isfile(filename):
        logging.info(f"Processing data from: {filename}")
        nc = Dataset(filename, format="NETCDF4")
        nc.set_auto_mask(False)
        for children in walktree(nc):
            for child in children:
                if len(child.groups) == 0 and child.name != "navigation":
                    for var_name in child.variables:
                        variable = child.variables[var_name]
                        units = variable.Units

                        # collect time and phenomenon id into arrays
                        (time, id) = child.path.strip("/").split("/")
                        time = int(time[:12])
                        id = int(id)

                        # skip if this isn't in the include set of filters
                        if times and (time < times[0] or time > times[1]):
                            continue

                        # collect stats info
                        stats_row = []
                        try:
                            stats_row = np.array(
                                [
                                    time,
                                    id,
                                    float(variable.Min),
                                    float(variable.Max),
                                    float(variable.Mean),
                                    float(variable.Std_dev),
                                ]
                            )
                        except AttributeError:
                            logging.warning(
                                f"Failed to retrieve statistics from: {filename}/{var_name}/{time}/{id}"
                            )

                        # init accumulator
                        if var_name not in statset:
                            statset[var_name] = {"units": units, "values": []}
                        statset[var_name]["values"].append(stats_row)
    else:
        logging.error(f"{filename} is not a file")

    for var_name in statset:
        statset[var_name]["values"] = np.array(statset[var_name]["values"])
    return statset


def get_plot_data(
    file_list=[], anomaly_ids=None, times=None, area=None, remove_fill=False
):
    logging.info(f"Collecting plot data for: {file_list}")
    p_start_time = pytime.time()

    if not isinstance(file_list, list):
        file_list = [file_list]

    # filters are implicitly an 'include' set
    anomaly_ids = (
        []
        if not anomaly_ids
        else anomaly_ids if isinstance(anomaly_ids, list) else [anomaly_ids]
    )
    if times:
        if not isinstance(times, list):
            times = [times]
        # if only one time is given, assume its the min time
        if len(times) < 2:
            times.append(999999999999)  # impossible but large 12 char "date"

    # parallelize the data collection
    datasets = {}
    with mp_pool.Pool() as process_pool:
        for result in process_pool.map(
            partial(get_data_from_file, times=times), file_list
        ):
            for var_name in result:
                datasets[var_name] = result[var_name]

    # collapse all the file contents into a single dict for ease
    stats = None
    var_meta = {}

    # flatten variable results into a dict
    for var_name in datasets:
        var_meta[var_name] = {"units": datasets[var_name]["units"]}

        df = pd.DataFrame(datasets[var_name]["values"], columns=[
            "datetime",
            "anom_id",
            f"{var_name}_min",
            f"{var_name}_max",
            f"{var_name}_mean",
            f"{var_name}_std_dev",
        ])

        if stats is None:
            stats = df
        else:
            stats = stats.merge(df, on=["datetime", "anom_id"], how="outer")
    
    stats = stats.sort_values(by="datetime")

    # format plot package
    plotset = {}
    for var_name in var_meta:
        if "values" not in plotset:
            plotset["title"] = to_title(var_name)
            plotset["axis_labels"] = [f'{var_name} ({var_meta[var_name]["units"]})']
            plotset["var_list"] = [var_name]
            plotset["values"] = []
        else:
            plotset["title"] = f'{plotset["title"]} x {to_title(var_name)}'
            plotset["axis_labels"].append(f'{var_name} ({var_meta[var_name]["units"]})')
            plotset["var_list"].append(var_name)

    # build dataframe of stats data and add to the data package
    plotset["stats"] = stats.dropna(how="all")

    mask_start_time = pytime.time()

    # Mask out plot values
    stats_mask = None

    # optionally remove rows that contain the fill value
    if remove_fill:
        # TODO - figure out why there are apparently multiple fill values?
        expected_fill = -9999.0

        # remove fill from stats
        plotset["stats"] = plotset["stats"][
            plotset["stats"] != expected_fill
        ].dropna(how="all")

    # anomaly ids is a list of anomalies to include
    if len(anomaly_ids) > 0:
        stats_mask = plotset["stats"]["anom_id"].isin(anomaly_ids)

    # apply mask to values
    if stats_mask is not None:
        plotset["stats"] = plotset["stats"][stats_mask]

    logging.info(
        f"{file_list} Done. Elapsed time: {round(pytime.time() - p_start_time, 4)} seconds (masking: {round(pytime.time() - mask_start_time, 4)} seconds)"
    )
    return plotset


def dump_plot_data(plotData):
    p_start_time = pytime.time()

    # remove values from data for serializing
    stats_vals = plotData["stats"]
    stats_headers = plotData["stats"].columns.to_list()
    plotData.pop("stats", None)

    # get basic data string
    plot_data_str = json.dumps(plotData)

    # get data array as string
    stats_vals_str = stats_vals.to_json(orient="values")
    stats_sub_str = (
        '"stats": {"rows":'
        + stats_vals_str
        + ',"columns":'
        + json.dumps(stats_headers)
        + "}"
    )

    # splice the values into the return string
    json_str = plot_data_str[:-1] + "," + stats_sub_str + plot_data_str[-1:]

    logging.info(
        f"dumped data to json: {round(pytime.time() - p_start_time, 4)} seconds"
    )

    return json_str
