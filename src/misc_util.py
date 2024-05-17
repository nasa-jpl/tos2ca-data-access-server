def str_to_bool(str_val="False"):
    return f"{str_val}".lower() in ("true", "1", "t")

def to_title(str_val):
    if str_val:
        return str_val[0].upper() + str_val[1:]
    return str_val
