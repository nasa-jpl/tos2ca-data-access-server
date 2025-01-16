import os
import json
import time as pytime
from collections import OrderedDict
from functools import partial
from multiprocessing import pool as mp_pool
import pandas as pd
from netCDF4 import Dataset
import logging

from misc_util import to_title


def walktree(top):
    yield top.groups.values()
    for value in top.groups.values():
        yield from walktree(value)


def get_data_from_file(filename, times=None):
    varset = OrderedDict()
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
                        time = int(time)
                        id = int(id)

                        # skip if this isn't in the include set of filters
                        if times and (time < times[0] or time > times[1]):
                            continue

                        # collect stats info
                        try:
                            summ_stats = {
                                "min": float(variable.Min),
                                "max": float(variable.Max),
                                "mean": float(variable.Mean),
                                "std_dev": float(variable.Std_dev),
                            }
                        except AttributeError:
                            logging.warning(
                                f"Failed to retrieve statistics from: {filename}/{var_name}/{time}/{id}"
                            )

                        # init accumulator
                        if var_name not in statset:
                            varset[var_name] = {"units": units}
                            statset[var_name] = {}
                            statset[var_name][time] = {}
                        else:
                            if time not in statset[var_name]:
                                statset[var_name][time] = {}
                        statset[var_name][time][id] = {var_name: summ_stats}
    else:
        logging.error(f"{filename} is not a file")

    return (varset, statset)


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
    datasets = []
    with mp_pool.Pool() as process_pool:
        for result in process_pool.map(
            partial(get_data_from_file, times=times), file_list
        ):
            datasets.append(result)

    # collapse all the file contents into a single dict for ease
    varset = OrderedDict()
    time_arr = []
    anom_id_arr = []
    for dataset in datasets:
        (vset, sset) = dataset
        for varname in sset:
            varset[varname] = {"stats": sset[varname], "units": vset["units"]}
            var_times = list(sset[varname].keys())
            time_arr.extend(var_times)
            for var_time in var_times:
                anom_id_arr.extend(list(sset[varname][var_time].keys()))

    time_arr = sorted(list(set(time_arr)))
    anom_id_arr = sorted(list(set(anom_id_arr)))

    # collect all the variable info
    plotset = {}
    for var_name in varset:
        if "values" not in plotset:
            plotset["title"] = to_title(var_name)
            plotset["values"] = []
            plotset["axis_labels"] = [f'{var_name} ({varset[var_name]["units"]})']
            plotset["var_list"] = [var_name]
        else:
            plotset["title"] = f'{plotset["title"]} x {to_title(var_name)}'
            plotset["axis_labels"].append(f'{var_name} ({varset[var_name]["units"]})')
            plotset["var_list"].append(var_name)

    # build list of column names
    stats_columns = ["datetime", "anom_id"]
    for var_name in varset:
        stats_columns = stats_columns + [
            f"{var_name}_min",
            f"{var_name}_max",
            f"{var_name}_mean",
            f"{var_name}_std_dev",
        ]

    # build rows of stats data and add to the data package
    stats_rows = []
    for time in time_arr:
        for anom_id in anom_id_arr:
            row = [time, anom_id]
            for var_name in varset:
                if anom_id in varset[var_name]["stats"][time]:
                    entry = varset[var_name]["stats"][time][anom_id][var_name]
                    row = row + [
                        entry["min"],
                        entry["max"],
                        entry["mean"],
                        entry["std_dev"],
                    ]
            stats_rows.append(row)
    plotset["stats"] = {
        "columns": stats_columns,
        "rows": pd.DataFrame(stats_rows, columns=stats_columns).dropna(),
    }

    mask_start_time = pytime.time()

    # Mask out plot values
    stats_mask = None

    # optionally remove rows that contain the fill value
    if remove_fill:
        # TODO - figure out why there are apparently multiple fill values?
        expected_fill = -9999.0

        # remove fill from stats
        plotset["stats"]["rows"] = (
            plotset["stats"]["rows"][plotset["stats"]["rows"] != expected_fill].dropna()
        )

    # anomaly ids is a list of anomalies to include
    if len(anomaly_ids) > 0:
        stats_mask = plotset["stats"]["rows"]["anom_id"].isin(anomaly_ids)

    # apply mask to values
    if stats_mask is not None:
        plotset["stats"]["rows"] = plotset["stats"]["rows"][stats_mask]

    logging.info(
        f"{file_list} Done. Elapsed time: {pytime.time() - p_start_time} seconds (masking: {pytime.time() - mask_start_time} seconds)"
    )
    return plotset


def dump_plot_data(plotData):
    p_start_time = pytime.time()

    # remove values from data for serializing
    stats_vals = plotData["stats"]["rows"]
    stats_headers = plotData["stats"]["columns"]
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
    json_str = (
        plot_data_str[:-1]
        + ','
        + stats_sub_str
        + plot_data_str[-1:]
    )

    logging.info(f"dumped data to json: {pytime.time() - p_start_time} seconds")

    return json_str
