import numpy as np


def generate_chiller_para(model_num_dict, small_value=0.0001):
    para = []
    for item in model_num_dict:
        num_str = str(item.get("冷机台数", "")).strip()
        if not num_str.isdigit():
            raise ValueError(f"冷机台数 '{num_str}' 不是有效数字")
        num = int(num_str)
        para.append([0] + list(np.arange(1, num + 1, 1)))
        para.append([0] + list(np.arange(0.2, 1 + small_value, 0.03)))
    return para


def generate_pump_list(PumpParameter, pump_config_list, lv_excel, input_lv_value, min_freq_key):
    pumps = []
    for cfg in pump_config_list:
        pumps.append(
            PumpParameter(
                flow=float(cfg["flow"]),
                head=float(cfg["head"]),
                power=float(cfg["power"]),
                min_freq=float(lv_excel.loc[min_freq_key, input_lv_value]),
            )
        )
    return pumps
