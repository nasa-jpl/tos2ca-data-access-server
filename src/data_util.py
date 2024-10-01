import os
import json
import time as pytime
from collections import OrderedDict
from functools import partial
from multiprocessing import pool as mp_pool
import numpy as np
import pandas as pd
from netCDF4 import Dataset, default_fillvals
import logging
from deepmerge import always_merger

from misc_util import to_title


def walktree(top):
    yield top.groups.values()
    for value in top.groups.values():
        yield from walktree(value)


def get_data_from_file(filename, anomaly_ids=None, times=None):
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

                        # collect time and phenomenon id into arrays
                        (time, id) = child.path.strip("/").split("/")
                        time = int(time)
                        id = int(id)

                        # skip if this isn't in the include set of filters
                        if (anomaly_ids and id not in anomaly_ids) or (
                            times and (time < times[0] or time > times[1])
                        ):
                            continue

                        time_arr = np.full(len(variable), time, dtype=int)
                        id_arr = np.full(len(variable), id, dtype=int)

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
        for result in process_pool.map(partial(get_data_from_file, anomaly_ids=anomaly_ids, times=times), file_list):
            datasets.append(result)

    # collapse all the file contents into a single dict for ease
    varset = OrderedDict()
    for dataset in datasets:
        (vset, sset) = dataset
        for varname in vset:
            varset[varname] = vset[varname]
            varset[varname]["stats"] = sset[varname]

    # stack all the variable values together into a single nD array
    plotset = {}
    for var_name in varset:
        vals = varset[var_name]["values"][:, 2]  # grab the value column
        if "values" not in plotset:
            plotset["title"] = to_title(var_name)
            plotset["values"] = vals
            plotset["axis_labels"] = [f'{var_name} ({varset[var_name]["units"]})']
            plotset["var_list"] = [var_name]
        else:
            plotset["title"] = f'{plotset["title"]} x {to_title(var_name)}'
            plotset["values"] = np.c_[plotset["values"], vals]
            plotset["axis_labels"].append(f'{var_name} ({varset[var_name]["units"]})')
            plotset["var_list"].append(var_name)

    # stack in the lat, lon, time, and phenom ids and pull fill value
    fill_value = None
    for var_name in varset:
        # grab the first two columns data format is [lat, long, value]
        lat_lon = varset[var_name]["values"][:, :2]
        plotset["values"] = np.c_[
            plotset["values"],
            lat_lon,
            varset[var_name]["times"],
            varset[var_name]["phenom_ids"],
        ]

        # grab the fill value
        fill_value = varset[var_name]["fill_val"]

        # all the lats, lons, times, IDs, and fill values should match so we just need to do this once
        break

    # stack the stats together into wide table
    time_arr = sorted(list(set(plotset["values"][:, -2])))
    anom_id_arr = sorted(list(set(plotset["values"][:, -1])))

    # build list of column names
    stats_columns = ["datetime"]
    for var_name in varset:
        for anom_id in anom_id_arr:
            stats_columns = stats_columns + [
                f"{int(anom_id)}_{var_name}_min",
                f"{int(anom_id)}_{var_name}_max",
                f"{int(anom_id)}_{var_name}_mean",
                f"{int(anom_id)}_{var_name}_std_dev",
            ]

    # init empty entry
    empty_cols = [None, None, None, None]

    # build rows of stats data
    stats_rows = []
    for time in time_arr:
        row = [time]
        for anom_id in anom_id_arr:
            for var_name in varset:
                if anom_id in varset[var_name]["stats"][time]:
                    entry = varset[var_name]["stats"][time][anom_id][var_name]
                    row = row + [
                        entry["min"],
                        entry["max"],
                        entry["mean"],
                        entry["std_dev"],
                    ]
                else:
                    row = row + empty_cols
        stats_rows.append(row)

    plotset["stats"] = {"columns": stats_columns, "rows": stats_rows}

    # Mask out plot values
    # init a mask for removing rows by removing None values (there should never be any)
    mask = plotset["values"] != None

    # optionally remove rows that contain the fill value
    if remove_fill:
        # TODO - figure out why there are apparently multiple fill values?
        expected_fill = -9999.0

        # add the fill values to mask
        mask = np.logical_and(
            mask,
            ~(
                np.logical_or(
                    plotset["values"] == fill_value, plotset["values"] == expected_fill
                )
            ),
        )

    # area is inclusive within [min_lon(x), min_lat(y), max_lon(x), max_lat(y)]
    if area:
        # index from the right because the number of value columns is variable
        lon_ind = -3
        lat_ind = -4
        if isinstance(area, list) and len(area) == 4:
            # update the mask
            mask[:, lon_ind] = np.ma.masked_inside(
                plotset["values"][:, lon_ind], area[0], area[2]
            ).mask
            mask[:, lat_ind] = np.ma.masked_inside(
                plotset["values"][:, lat_ind], area[1], area[3]
            ).mask
        else:
            # no way to correct poor formatting
            logging.warning(f"Improper bounding box format: {area}")

    # apply mask
    plotset["values"] = plotset["values"][np.all(mask, axis=1), :]

    logging.info(
        f"{file_list} Done. Elapsed time: {pytime.time() - p_start_time} seconds"
    )
    return plotset


def dump_plot_data(plotData):
    p_start_time = pytime.time()

    # convert values to a Pandas DataFrame because json serializing is so much faster
    # TODO - convert to DataFrames during data aggregation for better filtering performance
    plot_vals = pd.DataFrame(plotData["values"])
    stats_vals = pd.DataFrame(plotData["stats"]["rows"])
    stats_headers = plotData["stats"]["columns"]

    # remove values from data for serializing
    plotData.pop("values", None)
    plotData.pop("stats", None)

    # get basic data string
    plot_data_str = json.dumps(plotData)

    # get data array as string
    vals_str = plot_vals.to_json(orient="values")
    stats_vals_str = stats_vals.to_json(orient="values")

    stats_sub_str = '"stats": {"rows":' + stats_vals_str + ',"columns":' + json.dumps(stats_headers) + '}'

    # splice the values into the return string
    json_str = plot_data_str[:-1] + ',"values":' + vals_str +  ',' + stats_sub_str + plot_data_str[-1:]

    logging.info(f"dumped data to json: {pytime.time() - p_start_time} seconds")

    return json_str
