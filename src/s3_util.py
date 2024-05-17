import os
from concurrent.futures import ThreadPoolExecutor
from functools import partial
import boto3
import datetime
import logging

from config import APP_CONFIG


def _set_file_last_modified(file_path, dt):
    dt_epoch = dt.timestamp()
    os.utime(file_path, (dt_epoch, dt_epoch))


# adapted from https://emasquil.github.io/posts/multithreading-boto3/
def _download_one_file(bucket: str, output: str, client: boto3.client, s3_file: str):
    """
    Download a single file from S3
    Args:
        bucket (str): S3 bucket where images are hosted
        output (str): Dir to store the images
        client (boto3.client): S3 client
        s3_file (str): S3 object name
    """
    logging.info(f"Downloading file: {s3_file}")
    
    local_name = os.path.join(output, s3_file)

    # shortcut from cache
    logging.info(f"Looking for file: {local_name}")
    if os.path.isfile(local_name):
        logging.info(f"Cached file found: {local_name}")
        _set_file_last_modified(local_name, datetime.datetime.now())
        return local_name

    client.download_file(Bucket=bucket, Key=s3_file, Filename=local_name)
    return local_name


def download_files(file_list: list):
    """
    Use multiple threads to download a list of files in parallel
    AWS bucket and output directory specified by APP_CONFIG.S3_BUCKET and APP_CONFIG.CACHE_DIR respectively
    Args:
        file_list (list): list of file names
    """
    # Creating only one session and one client
    client = None
    if not APP_CONFIG["APP_LOCAL_ONLY"]:
        session = boto3.Session()
        client = session.client("s3")

    # The client is shared between threads
    output_dir = APP_CONFIG["CACHE_DIR"]
    func = partial(_download_one_file, APP_CONFIG["S3_BUCKET"], output_dir, client)

    # download all the files in parallel
    saved_files = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        for i in executor.map(func, file_list):
            saved_files.append(i)

    return saved_files
