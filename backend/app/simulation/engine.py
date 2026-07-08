from __future__ import annotations

import math
import os
import random
import re
import time
from pathlib import Path

import numpy as np
import pandas as pd
from pandas import DataFrame
from sklearn import linear_model
from sklearn.metrics import r2_score
from sklearn.preprocessing import PolynomialFeatures
from tqdm import tqdm

from . import util


class PumpParameter:
    def __init__(self, flow, head, power, min_freq):
        self.flow = flow
        self.head = head
        self.power = power
        self.min_freq = min_freq


class CoolingTower:
    def __init__(self, flow, power, T_S, T_R, T_wb):
        self.flow = flow
        self.power = power
        self.T_S = T_S
        self.T_R = T_R
        self.T_wb = T_wb

    def get_temp_diff(self):
        return abs(self.T_S - self.T_R), self.power / self.flow, self.T_wb


def run_simulation(work_folder: str | Path, config: dict, output_name: str = "simulation_result.xlsx") -> Path:
    work_folder = Path(work_folder)
    work_folder.mkdir(parents=True, exist_ok=True)
    basic_dir = work_folder / "1_基本数据"
    result_dir = work_folder / "2_模拟结果"
    result_dir.mkdir(parents=True, exist_ok=True)

    PumpFormChwPri = int(config["PumpFormChwPri"])
    PumpFormCwPri = int(config["PumpFormCwPri"])
    PumpFormChwSec = int(config["PumpFormChwSec"])
    model_num_dict = config["model_num_dict"]
    chwp_pump_config_list = config["chwp_pump_config_list"]
    cwp_pump_config_list = config["cwp_pump_config_list"]
    chwp_sec_pump_config_list = config.get("chwp_sec_pump_config_list", [])
    ChwTempSupply = float(config["ChwTempSupply"])
    ChwTempReturn = float(config["ChwTempReturn"])
    CwTempReturn = float(config["CwTempReturn"])
    CwTempSupply = float(config["CwTempSupply"])
    Ctpower = float(config["Ctpower"])
    Ctflow = float(config["Ctflow"])
    TempOutdoorWb = float(config["TempOutdoorWb"])
    ProjectMaxLoad = float(config["ProjectMaxLoad"])

    lv_excel = pd.read_excel(basic_dir / "01_simu_value.xlsx", index_col=0)
    load_ratio_path = basic_dir / "load_ratio.xlsx"
    chiller_path = basic_dir / "chiller.xlsx"
    weather_path = basic_dir / "whether.xlsx"
    input_lv_value_list = ["lv1"]

    def caculate_result(lv_excel: pd.DataFrame, input_lv_value_list: list) -> tuple[DataFrame, DataFrame]:
        chiller_form = 1
        LoadRangeCL_real = [0.996, 1.08]
        sum_result_df = pd.DataFrame()
        hourly_result_df = pd.DataFrame()
        for input_lv_value in input_lv_value_list:
            smallValue = 0.0001
            minLoadRatio = 0.10
            para = util.generate_chiller_para(model_num_dict, smallValue)
            wbRatio = float(lv_excel.loc["wbRatio", input_lv_value])
            CwSupplyMinTemp = float(lv_excel.loc["CwSupplyMinTemp", input_lv_value])
            TempApproximate = float(lv_excel.loc["TempApproximate", input_lv_value])
            ChwTempDiff = abs(ChwTempReturn - ChwTempSupply)
            CwTempDiff = abs(CwTempReturn - CwTempSupply)

            chwp_list = []
            cwp_list = []
            if PumpFormChwPri == 1:
                chwp_list = util.generate_pump_list(
                    PumpParameter, chwp_pump_config_list, lv_excel, input_lv_value, "pump_chw_min_freq"
                )
            if PumpFormCwPri == 1:
                cwp_list = util.generate_pump_list(
                    PumpParameter, cwp_pump_config_list, lv_excel, input_lv_value, "pump_cw_min_freq"
                )
            if PumpFormChwPri == 2:
                ChwpPriParal = PumpParameter(180, 50, 37, 0.6)
            if PumpFormCwPri == 2:
                CwpPriParal = PumpParameter(230, 22, 22, 0.6)
            if PumpFormChwSec == 2:
                sec_cfg = (chwp_sec_pump_config_list or [{"flow": 1160, "head": 38, "power": 200}])[0]
                ChwpSecParal = PumpParameter(float(sec_cfg["flow"]), float(sec_cfg["head"]), float(sec_cfg["power"]), 0.6)

            ct_1 = CoolingTower(flow=Ctflow, power=Ctpower, T_S=CwTempSupply, T_R=CwTempReturn, T_wb=TempOutdoorWb)
            ct_diff_1, ct_per_watt_1, ct_wb_1 = ct_1.get_temp_diff()

            if chiller_form != 1:
                raise ValueError("当前版本只支持标准变水温报告矩阵格式")
            workbook = pd.ExcelFile(chiller_path)
            get_sheets = workbook.sheet_names
            if len(get_sheets) != len(model_num_dict):
                raise ValueError("冷机报告数量必须与冷机型号数量一致")

            raw_df = [pd.DataFrame] * len(get_sheets)
            ChillerCapacityList = []
            for n, sheet_name in enumerate(get_sheets):
                match = re.match(r".*?(\d+(?:\.\d+)?)\s*RT", sheet_name, flags=re.IGNORECASE)
                if not match:
                    capacity = float(model_num_dict[n].get("冷机容量RT", 0))
                    if capacity <= 0:
                        raise ValueError(f"冷机报告 '{sheet_name}' 缺少冷机容量 RT")
                else:
                    capacity = float(match.group(1))
                ChillerCapacityList.append(capacity * 3.517)
                raw_df[n] = pd.read_excel(chiller_path, sheet_name=sheet_name)
                list_L = [str(x) for x in raw_df[n].columns.values.tolist()]
                raw_df[n].columns = list_L
                list_L.remove("CondEWT")
                list_w = sorted(list(set(raw_df[n]["CondEWT"].astype("float"))), reverse=True)
                raw_df[n].set_index("CondEWT", inplace=True)
                df_dinner = raw_df[n]
                rows = []
                for i in list_w:
                    for j in list_L:
                        rows.append({"Load": float(j), "Tcws": i, "Eff": 1 / float(df_dinner.loc[i, j])})
                raw_df[n] = pd.DataFrame(rows)

            def fit(df):
                df = df.copy()
                df["1/Load"] = 1 / df["Load"]
                x = np.array(df[["Load", "Tcws", "1/Load"]].values)
                y = np.array(df["Eff"].values)
                poly_reg = PolynomialFeatures(degree=2)
                X_ploy = poly_reg.fit_transform(x)
                X_ploy = np.delete(X_ploy, [4, 6, 9], axis=1)
                X_ploy = np.insert(X_ploy, 7, X_ploy[:, 5] * X_ploy[:, 1], axis=1)
                X_ploy = np.insert(X_ploy, 8, X_ploy[:, 5] * X_ploy[:, 3], axis=1)
                lin_reg_2 = linear_model.LinearRegression()
                lin_reg_2.fit(X_ploy, y)
                _ = r2_score(lin_reg_2.predict(X_ploy), y)
                return [lin_reg_2.intercept_] + list(lin_reg_2.coef_)

            df_para = pd.DataFrame(columns=get_sheets)
            for n, name in enumerate(get_sheets):
                df_para[name] = list(fit(raw_df[n]))
            df_para.drop(labels=1, axis=0, inplace=True)
            df_para.reset_index(drop=True, inplace=True)

            def en_cal(name, plr, t):
                list_para = list(df_para[name])
                if plr <= 0:
                    return 0
                plr_1 = 1 / plr
                return (
                    list_para[0]
                    + list_para[1] * plr
                    + list_para[2] * t
                    + list_para[3] * plr_1
                    + list_para[4] * plr * t
                    + list_para[5] * t**2
                    + list_para[6] * plr_1 * t
                    + list_para[7] * t**2 * plr
                    + list_para[8] * t**2 * plr_1
                )

            def plan_generate(CL):
                res = pd.DataFrame({"sup": [1]})
                for i in para:
                    d_i = pd.DataFrame(i)
                    d_i["sup"] = 1
                    res = pd.merge(res, d_i, how="outer", on=["sup"], suffixes=(f"_{len(res.columns)}", "_x"))
                res = res.drop(columns=["sup"])
                res["CL_real"] = 0.0
                for num in range(int(len(para) / 2)):
                    res["CL_real"] += res.iloc[:, 2 * num] * ChillerCapacityList[num] * res.iloc[:, 2 * num + 1]
                res["ratio"] = res["CL_real"] / CL
                return res[(res["ratio"] > LoadRangeCL_real[0]) & (res["ratio"] < LoadRangeCL_real[1])].drop(
                    columns=["CL_real", "ratio"]
                ).values.tolist()

            def convert_t(wb):
                Tcws = (
                    (9.802e-06 * wb**3 + 0.0007092 * wb**2 - 0.1349 * wb + 4.003)
                    * 2.75
                    * (ct_1.T_S - ct_1.T_wb)
                    / 4
                    * TempApproximate
                    + wb
                )
                return max(Tcws, CwSupplyMinTemp)

            def cal(CL, wb):
                plans = plan_generate(CL)
                if not plans:
                    return [], 0
                Tcws = convert_t(wb)
                en_min = np.inf
                plan_best = []
                for plan in plans:
                    en = 0
                    for i in range(len(get_sheets)):
                        en += en_cal(get_sheets[i], plan[2 * i + 1], Tcws) * ChillerCapacityList[i] * plan[2 * i + 1] * plan[2 * i]
                    if en < en_min:
                        en_min = en
                        plan_best = plan
                return plan_best, en_min

            def pump_cal(x, F, H, P, MinFreq):
                if x == 0:
                    return 0
                x = max(x, MinFreq)
                y = F * H / (P * 367) / (0.94187 * (1 - math.exp(-9.04))) / (0.5067 + 1.283 - 1.42 + 0.5872)
                H1 = x**2 * H
                if H1 < 0.5 * H:
                    H1 = (0.5 + (random.randrange(-50, 50, 1) / 1000) ** 2) * H
                P1 = F * x * H1 / 367 / y
                P1 = P1 / (0.94187 * (1 - math.exp(-9.04 * x))) / (0.5067 + 1.283 * x - 1.42 * x**2 + 0.5872 * x**3)
                if P1 < 0.3 * P:
                    P1 = (0.3 + (random.randrange(-50, 50, 1) / 100) ** 2) * P
                return P1

            def ParalPump(CL_real, pump, TempDiff):
                F_chw = CL_real / TempDiff / 1.1667
                n_pump = max(math.ceil(F_chw / pump.flow), 1)
                return n_pump * pump_cal(F_chw / n_pump / pump.flow, pump.flow, pump.head, pump.power, pump.min_freq)

            def zhileng_cal(CL, wb):
                plan_best, en_min = cal(CL, wb)
                if len(plan_best) != len(ChillerCapacityList) * 2:
                    raise ValueError(
                        f"当前负荷 {CL:.2f} kW 无可行冷机组合，请检查冷机台数、冷机容量RT、项目最大负荷和负载率"
                    )
                n_list, p_list = [], []
                for index, num_load in enumerate(plan_best):
                    (n_list if index % 2 == 0 else p_list).append(num_load)
                CL_real = pump_chw = pump_cw = pump_chw_sec = 0
                for index, _ in enumerate(ChillerCapacityList):
                    CL_real += ChillerCapacityList[index] * n_list[index] * p_list[index]
                    if PumpFormChwPri == 1:
                        pump_chw += n_list[index] * pump_cal(
                            p_list[index], chwp_list[index].flow, chwp_list[index].head, chwp_list[index].power, chwp_list[index].min_freq
                        )
                    if PumpFormCwPri == 1:
                        pump_cw += n_list[index] * pump_cal(
                            p_list[index], cwp_list[index].flow, cwp_list[index].head, cwp_list[index].power, cwp_list[index].min_freq
                        )
                if PumpFormChwPri == 2:
                    pump_chw = ParalPump(CL_real, ChwpPriParal, ChwTempDiff)
                if PumpFormCwPri == 2:
                    pump_cw = ParalPump(CL_real, CwpPriParal, CwTempDiff)
                if PumpFormChwSec == 2:
                    pump_chw_sec = ParalPump(CL_real, ChwpSecParal, ChwTempDiff)
                F_cw_2 = (CL_real + en_min) / ct_diff_1 / 1.1667
                tower = ct_per_watt_1 * F_cw_2 * max(wb, CwSupplyMinTemp) / ct_wb_1
                return plan_best, en_min, n_list, p_list, CL_real, pump_cw, pump_chw, pump_chw_sec, tower

            CL_month = pd.read_excel(load_ratio_path, sheet_name="month")
            CL_hour = pd.read_excel(load_ratio_path, sheet_name="hour")

            def gen_CL(month, hour):
                CL = float(CL_month[CL_month["month"] == month]["load1"].iloc[0])
                return CL * float(CL_hour[CL_hour["hour"] == hour]["CL_hour"].iloc[0])

            weather_df = pd.read_excel(weather_path)
            data = pd.DataFrame(weather_df[["times", "month", "day", "hour", "dry", "wb"]])
            data["wb"] = data["wb"] * wbRatio
            data["CL"] = data.apply(lambda raw: gen_CL(raw["month"], raw["hour"]), axis=1) * ProjectMaxLoad
            data = data.assign(
                HL=np.nan,
                CL_real=np.nan,
                chiller=np.nan,
                pump_chw=np.nan,
                pump_chw_sec=np.nan,
                pump_cw=np.nan,
                pump=np.nan,
                tower=np.nan,
                tcws=np.nan,
                dt_approach=np.nan,
                power=np.nan,
                price=np.nan,
                money=np.nan,
                COP=np.nan,
                EER=np.nan,
                CL_free=np.nan,
            )
            for index in range(len(ChillerCapacityList)):
                data[f"n{index + 1}"] = np.nan
                data[f"p{index + 1}"] = np.nan
            data["chp_sec_total"] = np.nan
            data["max_capacity"] = ProjectMaxLoad
            data["lv等级"] = input_lv_value

            for i in tqdm(range(len(data)), disable=True):
                durationTimeRatio = 1
                CL = float(data.loc[i, "CL"])
                wb = float(data.loc[i, "wb"])
                data.loc[i, "单时负载率"] = CL / ProjectMaxLoad
                if CL == 0:
                    en_min = CL_real = pump_cw = pump_chw = pump_chw_sec = tower = 0
                    n_list, p_list = [0] * len(ChillerCapacityList), [0] * len(ChillerCapacityList)
                else:
                    CL_min = minLoadRatio * ChillerCapacityList[0]
                    if CL <= CL_min:
                        durationTimeRatio = CL / CL_min
                        CL = CL_min
                    _, en_min, n_list, p_list, CL_real, pump_cw, pump_chw, pump_chw_sec, tower = zhileng_cal(CL, wb)
                    for index, _ in enumerate(n_list):
                        data.loc[i, f"n{index + 1}"] = n_list[index]
                        data.loc[i, f"p{index + 1}"] = p_list[index]
                data.loc[i, "tcws"] = convert_t(wb)
                data.loc[i, "dt_approach"] = data.loc[i, "tcws"] - wb
                data.loc[i, "chp_sec_total"] = 0
                data.loc[i, "CL_real"] = CL_real * durationTimeRatio
                data.loc[i, "pump_cw"] = pump_cw * float(lv_excel.loc["pump_cw", input_lv_value]) * min(durationTimeRatio * 1.3, 1)
                data.loc[i, "pump_chw"] = pump_chw * float(lv_excel.loc["pump_chw", input_lv_value])
                data.loc[i, "pump_chw_sec"] = pump_chw_sec * float(lv_excel.loc["pump_chw_sec", input_lv_value])
                data.loc[i, "pump"] = data.loc[i, "pump_cw"] + data.loc[i, "pump_chw"] + data.loc[i, "pump_chw_sec"]
                data.loc[i, "tower"] = tower * float(lv_excel.loc["tower", input_lv_value]) * min(durationTimeRatio * 1.3, 1)
                data.loc[i, "chiller"] = en_min * float(lv_excel.loc["en_min", input_lv_value]) * min(durationTimeRatio * 1.3, 1) * 1.05
                data.loc[i, "power"] = data.loc[i, "pump"] + data.loc[i, "tower"] + data.loc[i, "chiller"]
                data.loc[i, "EER"] = 0 if data.loc[i, "power"] == 0 else data.loc[i, "CL_real"] / data.loc[i, "power"]
                data.loc[i, "COP"] = 0 if data.loc[i, "chiller"] == 0 else data.loc[i, "CL_real"] / data.loc[i, "chiller"]
                data.loc[i, "money"] = 0

            MonthPivot = data.pivot_table(
                index=["month"],
                aggfunc="sum",
                values=["CL_real", "chiller", "pump_cw", "pump_chw", "pump_chw_sec", "chp_sec_total", "pump", "tower", "power", "money", "max_capacity"],
            )
            MonthPivot.rename(
                columns={
                    "CL_real": "冷负荷",
                    "max_capacity": "最大能力",
                    "pump_cw": "冷却泵",
                    "pump_chw": "冷冻泵",
                    "pump_chw_sec": "大二次泵",
                    "chp_sec_total": "二次泵汇总",
                    "pump": "泵总功率",
                    "chiller": "冷机",
                    "tower": "冷塔",
                    "power": "总耗电量",
                    "money": "电费",
                },
                inplace=True,
            )
            MonthPivot = MonthPivot[["冷负荷", "总耗电量", "冷机", "泵总功率", "冷塔", "最大能力", "冷却泵", "冷冻泵", "大二次泵", "二次泵汇总", "电费"]]
            MonthPivot["EER"] = MonthPivot["冷负荷"] / MonthPivot["总耗电量"].replace(0, np.nan)
            MonthPivot["lv等级"] = input_lv_value
            sum_result_df = pd.concat([sum_result_df, MonthPivot])
            hourly_result_df = pd.concat([hourly_result_df, data])
        return sum_result_df, hourly_result_df

    sum_result_df, hourly_result_df = caculate_result(lv_excel, input_lv_value_list)
    sum_result_df["load"] = "模拟"
    sum_result_df["方案"] = "模拟"
    sum_result_df["免费制冷"] = "无"
    hourly_result_df["load"] = "模拟"
    hourly_result_df["方案"] = "模拟"
    hourly_result_df["免费制冷"] = "无"

    excel_path = result_dir / output_name
    with pd.ExcelWriter(excel_path) as writer:
        sum_result_df.to_excel(writer, sheet_name="月汇总值", index=True)
        hourly_result_df.to_excel(writer, sheet_name="逐时值", index=True)
    return excel_path
