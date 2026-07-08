DEFAULT_SYSTEM_PARAMETERS = {
    "config": {
        "PumpFormChwPri": 1,
        "PumpFormCwPri": 1,
        "PumpFormChwSec": 0,
        "model_num_dict": [
            {"冷机型号": "2800RT低温定频", "冷机台数": "1"},
            {"冷机型号": "2800RT低温变频", "冷机台数": "2"},
        ],
        "chwp_pump_config_list": [
            {"name": "冷冻一次泵1", "flow": 605, "head": 55, "power": 132},
            {"name": "冷冻一次泵2", "flow": 906, "head": 55, "power": 185},
        ],
        "cwp_pump_config_list": [
            {"name": "冷却泵1", "flow": 905, "head": 55, "power": 185},
            {"name": "冷却泵2", "flow": 905, "head": 55, "power": 185},
        ],
        "chwp_sec_pump_config_list": [
            {"name": "冷冻二次泵1", "flow": 1160, "head": 38, "power": 200},
        ],
    },
    "simu_values": [
        {"key": "en_min", "group": "冷机", "name": "冷机功率放大", "value": 1.04, "unit": ""},
        {"key": "CwSupplyMinTemp", "group": "", "name": "冷却水最低进水温度", "value": 18, "unit": "℃"},
        {"key": "pump_chw", "group": "冷冻泵", "name": "冷冻泵放大", "value": 1.15, "unit": ""},
        {"key": "pump_chw_min_freq", "group": "", "name": "冷冻泵最低频率", "value": 0.6, "unit": "Hz"},
        {"key": "pump_cw", "group": "冷却泵", "name": "冷却泵功率放大", "value": 1.15, "unit": ""},
        {"key": "pump_cw_min_freq", "group": "", "name": "冷却泵最低频率", "value": 0.6, "unit": "Hz"},
        {"key": "tower", "group": "冷却塔", "name": "冷却塔功率放大", "value": 1.2, "unit": ""},
        {"key": "wbRatio", "group": "", "name": "湿球温度放大系数", "value": 1.05, "unit": ""},
        {"key": "TempApproximate", "group": "", "name": "冷却塔逼近度修正系数", "value": 1.1, "unit": ""},
        {"key": "pump_chw_sec", "group": "二次泵", "name": "冷冻二次泵放大", "value": 1, "unit": ""},
    ],
    "basic_config": [
        {"key": "ChwTempSupply", "name": "冷冻水供水温度", "value": 4, "unit": "℃", "remark": ""},
        {"key": "ChwTempReturn", "name": "冷冻水回水温度", "value": 10, "unit": "℃", "remark": ""},
        {"key": "CwTempReturn", "name": "冷却水回水温度", "value": 38, "unit": "℃", "remark": ""},
        {"key": "CwTempSupply", "name": "冷却水供水温度", "value": 32, "unit": "℃", "remark": ""},
        {"key": "Ctpower", "name": "冷却塔功率", "value": 45, "unit": "kW", "remark": ""},
        {"key": "Ctflow", "name": "冷却塔额定流量", "value": 1000, "unit": "m3/h", "remark": ""},
        {"key": "TempOutdoorWb", "name": "冷却塔室外湿球温度", "value": 28.4, "unit": "℃", "remark": ""},
        {"key": "ProjectMaxLoad", "name": "项目最大负荷", "value": 29542.8, "unit": "kW", "remark": "系统下所有冷机制冷量之和"},
    ],
    "load_ratio_month": [{"month": i, "load1": 0.2} for i in range(1, 13)],
    "load_ratio_hour": [{"hour": i, "CL_hour": 1} for i in range(1, 25)],
    "chiller_reports": [],
}


CHILLER_LOAD_COLUMNS = ["1", "0.85", "0.8", "0.7", "0.6", "0.5", "0.4", "0.3", "0.2", "0.15"]
CHILLER_TEMPLATE_ROWS = [
    {"CondEWT": temp, **{col: "" for col in CHILLER_LOAD_COLUMNS}}
    for temp in range(32, 17, -1)
]
