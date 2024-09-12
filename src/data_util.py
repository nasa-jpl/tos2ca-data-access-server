import os
import json
import time as pytime
from collections import OrderedDict
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


def get_data_from_file(filename):
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
                        summ_stats = {
                            "min": float(variable.Min),
                            "max": float(variable.Max),
                            "mean": float(variable.Mean),
                            "std_dev": float(variable.Std_dev),
                            "percentile_10": float(variable.percentile_10),
                            "percentile_25": float(variable.percentile_25),
                            "percentile_50": float(variable.percentile_50),
                            "percentile_75": float(variable.percentile_75),
                            "percentile_90": float(variable.percentile_90),
                        }

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

    # multi-thread the data collection
    datasets = []
    with mp_pool.Pool() as process_pool:
        for result in process_pool.map(get_data_from_file, file_list):
            datasets.append(result)

    # collapse all the file contents into a single dict for ease
    varset = OrderedDict()
    for dataset in datasets:
        (vset, sset) = dataset
        for varname in vset:
            varset[varname] = vset[varname]
            varset[varname]["stats"] = sset[varname]

    # stack all the variable values together into a single nD array
    # TODO - restack stats so its time:id:var:stats
    plotset = {}
    for var_name in varset:
        vals = varset[var_name]["values"][:, 2]  # grab the value column
        if "values" not in plotset:
            plotset["title"] = to_title(var_name)
            plotset["values"] = vals
            plotset["axis_labels"] = [f'{var_name} ({varset[var_name]["units"]})']
            plotset["stats"] = [
                {"time": time, "stats": varset[var_name]["stats"][time]}
                for time in varset[var_name]["stats"]
            ]
        else:
            plotset["title"] = f'{plotset["title"]} x {to_title(var_name)}'
            plotset["values"] = np.c_[plotset["values"], vals]
            plotset["axis_labels"].append(f'{var_name} ({varset[var_name]["units"]})')
            for idx, time in enumerate(varset[var_name]["stats"]):
                if plotset["stats"][idx]["time"] == time:
                    plotset["stats"][idx]["stats"] = always_merger.merge(
                        plotset["stats"][idx]["stats"], varset[var_name]["stats"][time]
                    )
                else:
                    logging.error("mismatch in time order, stats not collected")

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

    # filter out specific fields
    # anomaly IDs are implicitly an 'include' set
    if anomaly_ids:
        # index from the right because the number of value columns is variable
        anom_ind = -1
        if not isinstance(anomaly_ids, list):
            anomaly_ids = [anomaly_ids]
        # update the mask
        mask[:, anom_ind] = np.isin(plotset["values"][:, anom_ind], anomaly_ids)

    # times are are an inclusive window int(YYYYMMDDhhmm)
    if times:
        # index from the right because the number of value columns is variable
        time_ind = -2
        if not isinstance(times, list):
            times = [times]
        # if only one time is given, assume its the min time
        if len(times) < 2:
            times.append(999999999999)  # impossible but large 12 char "date"
        # update the mask
        mask[:, time_ind] = np.ma.masked_inside(
            plotset["values"][:, time_ind], times[0], times[1]
        ).mask

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
            logging.warn(f"Improper bounding box format: {area}")

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

    # remove values from data for serializing
    plotData.pop("values", None)

    # get basic data string
    plot_data_str = json.dumps(plotData)

    # get data array as string
    vals_str = plot_vals.to_json(orient="values")

    # splice the values into the return string
    json_str = plot_data_str[:-1] + ',"values":' + vals_str + plot_data_str[-1:]

    logging.info(f"dumped data to json: {pytime.time() - p_start_time} seconds")

    return json_str
