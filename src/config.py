import os

from misc_util import str_to_bool


def bool_env(env_str):
    return str_to_bool(os.getenv(env_str, "False"))


APP_CONFIG = {
    "S3_BUCKET": os.getenv("APP_S3_BUCKET", "tos2ca-dev1"),
    "CACHE_DIR": os.path.abspath("/app_data_cache"),
    "MAX_CACHE": int(os.getenv("APP_CACHE_ITEM_MAX", 15)),  # number of items
    "CACHE_FILES": bool_env("APP_CACHE_DATA"),
    "AVAILABLE_FORMATS": {"json": "application/json"},
    "DEFAULT_FORMAT": "application/json",
    "LOG_LEVEL": int(os.getenv("APP_LOG_LEVEL", 30)),
    "APP_PORT": int(os.getenv("APP_PORT", 8100)),
    "APP_LOCAL_ONLY": bool_env("APP_LOCAL_ONLY"),
}
