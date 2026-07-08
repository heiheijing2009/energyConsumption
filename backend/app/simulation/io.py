from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_input_files(work_folder: Path, params: dict, weather_rows: list[dict]) -> None:
    basic_dir = work_folder / "1_基本数据"
    basic_dir.mkdir(parents=True, exist_ok=True)

    simu = pd.DataFrame(
        [
            {
                "num": row["key"],
                "分组": row.get("group", ""),
                "含义": row["name"],
                "lv1": row["value"],
                "单位": row.get("unit", ""),
            }
            for row in params["simu_values"]
        ]
    )
    with pd.ExcelWriter(basic_dir / "01_simu_value.xlsx", engine="openpyxl") as writer:
        simu.to_excel(writer, sheet_name="Scale_factor", index=False)

    month = pd.DataFrame(params["load_ratio_month"])
    hour = pd.DataFrame(params["load_ratio_hour"])
    with pd.ExcelWriter(basic_dir / "load_ratio.xlsx", engine="openpyxl") as writer:
        month.to_excel(writer, sheet_name="month", index=False)
        hour.to_excel(writer, sheet_name="hour", index=False)

    weather = pd.DataFrame(weather_rows)
    weather[["times", "month", "day", "hour", "dry", "rh", "wb"]].to_excel(basic_dir / "whether.xlsx", index=False)

    prepared_reports = []
    for report in params["chiller_reports"]:
        rows = pd.DataFrame(report["rows"])
        if "CondEWT" not in rows.columns:
            raise ValueError(f"变水温报告 {report['name']} 缺少 CondEWT")
        prepared_reports.append((report["name"][:31] or "chiller", rows))
    if not prepared_reports:
        raise ValueError("至少需要一份变水温报告")

    with pd.ExcelWriter(basic_dir / "chiller.xlsx", engine="openpyxl") as writer:
        for sheet, rows in prepared_reports:
            rows.to_excel(writer, sheet_name=sheet, index=False)


def read_excel_records(path: Path, required: list[str]) -> list[dict]:
    df = pd.read_excel(path)
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"缺少列：{', '.join(missing)}")
    return df[required].dropna(how="all").to_dict(orient="records")


def read_chiller_workbook(path: Path) -> list[dict]:
    xl = pd.ExcelFile(path)
    reports = []
    for sheet in xl.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet)
        if "CondEWT" not in df.columns:
            raise ValueError(f"{sheet} 缺少 CondEWT 列")
        reports.append({"name": sheet, "rows": df.to_dict(orient="records")})
    return reports
