from __future__ import annotations

import copy
import json
import shutil
import tempfile
import threading
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import RUNS_DIR, STATIC_DIR, UPLOADS_DIR
from .db import get_db, init_db, now, row_to_dict, rows_to_list
from .defaults import CHILLER_TEMPLATE_ROWS, DEFAULT_SYSTEM_PARAMETERS
from .security import create_token, hash_password, verify_password, decode_token
from .simulation.engine import run_simulation
from .simulation.io import read_chiller_workbook, read_excel_records, write_input_files


app = FastAPI(title="制冷站能耗模拟平台")
auth_scheme = HTTPBearer(auto_error=False)
job_lock = threading.Lock()


class LoginPayload(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"


class ProjectPayload(BaseModel):
    name: str
    weather_library_id: int
    remark: str | None = ""


class SystemPayload(BaseModel):
    name: str
    remark: str | None = ""


class ParamsPayload(BaseModel):
    parameters: dict[str, Any]


class WeatherPayload(BaseModel):
    city: str
    year: int = 2025
    remark: str | None = ""


@app.on_event("startup")
def startup() -> None:
    init_db()


def require_user(credentials: HTTPAuthorizationCredentials | None = Depends(auth_scheme)) -> dict:
    if not credentials:
        raise HTTPException(status_code=401, detail="未登录")
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="登录已过期")
    with get_db() as db:
        user = row_to_dict(db.execute("SELECT id, username, role FROM users WHERE id=?", (payload["sub"],)).fetchone())
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def require_admin(user: dict = Depends(require_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def load_params(system_id: int) -> dict:
    with get_db() as db:
        row = db.execute("SELECT parameters_json FROM systems WHERE id=?", (system_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="系统不存在")
    return json.loads(row["parameters_json"])


def save_params(system_id: int, params: dict) -> None:
    with get_db() as db:
        db.execute(
            "UPDATE systems SET parameters_json=?, updated_at=? WHERE id=?",
            (json.dumps(params, ensure_ascii=False), now(), system_id),
        )


def clear_system_results(db, system_id: int) -> None:
    jobs = db.execute("SELECT id FROM simulation_jobs WHERE system_id=?", (system_id,)).fetchall()
    for job in jobs:
        run_dir = RUNS_DIR / str(job["id"])
        if run_dir.exists():
            shutil.rmtree(run_dir, ignore_errors=True)
    db.execute("DELETE FROM simulation_jobs WHERE system_id=?", (system_id,))


def same_json(left: dict, right: dict) -> bool:
    return json.dumps(left, ensure_ascii=False, sort_keys=True) == json.dumps(right, ensure_ascii=False, sort_keys=True)


def chiller_report_name(model: dict) -> str:
    name = str(model.get("冷机型号", "")).strip() or "冷机型号"
    capacity = model.get("冷机容量RT", "")
    if capacity not in ("", None):
        cap_text = str(capacity).strip()
        if cap_text and f"{cap_text}RT" not in name.upper().replace(" ", ""):
            return f"{name} {cap_text}RT"
    return name


def sync_chiller_reports(params: dict) -> dict:
    params = copy.deepcopy(params)
    config = params.setdefault("config", {})
    models = config.get("model_num_dict") or []
    existing = {str(report.get("name", "")): report for report in params.get("chiller_reports", [])}
    reports = []
    for model in models:
        report_name = chiller_report_name(model)
        report = copy.deepcopy(existing.get(report_name, {}))
        report["name"] = report_name
        report["capacity_rt"] = model.get("冷机容量RT", "")
        report["count"] = model.get("冷机台数", 1)
        if not report.get("rows"):
            report["rows"] = copy.deepcopy(CHILLER_TEMPLATE_ROWS)
        reports.append(report)
    params["chiller_reports"] = reports
    return params


def sanitize_pump_configs(config: dict) -> dict:
    config = copy.deepcopy(config)

    def clean_list(key: str, default_name: str, default_values: dict) -> None:
        rows = config.get(key) or []
        cleaned = []
        last_valid = dict(default_values)
        for index, row in enumerate(rows):
            item = dict(row or {})
            item["name"] = item.get("name") or f"{default_name}{index + 1}"
            for field in ("flow", "head", "power"):
                value = item.get(field)
                if value in ("", None):
                    item[field] = last_valid[field]
                else:
                    item[field] = float(value)
            last_valid = {field: item[field] for field in ("flow", "head", "power")}
            cleaned.append(item)
        if not cleaned and int(config.get("PumpFormChwSec", 0)) == 2:
            cleaned.append({"name": f"{default_name}1", **default_values})
        config[key] = cleaned

    clean_list("chwp_pump_config_list", "冷冻一次泵", {"flow": 605, "head": 55, "power": 132})
    clean_list("cwp_pump_config_list", "冷却泵", {"flow": 905, "head": 55, "power": 185})
    clean_list("chwp_sec_pump_config_list", "冷冻二次泵", {"flow": 1160, "head": 38, "power": 200})
    return config


def require_system(system_id: int) -> dict:
    with get_db() as db:
        row = db.execute(
            """
            SELECT s.*, p.weather_library_id, p.name AS project_name
            FROM systems s JOIN projects p ON p.id=s.project_id
            WHERE s.id=?
            """,
            (system_id,),
        ).fetchone()
    data = row_to_dict(row)
    if not data:
        raise HTTPException(status_code=404, detail="系统不存在")
    return data


def weather_datetime_text(year: int, month: int, day: int, hour: int) -> str:
    hour_offset = hour - 1 if hour >= 1 else hour
    dt = datetime(year, month, day) + timedelta(hours=hour_offset)
    return f"{dt.year}/{dt.month}/{dt.day} {dt.hour}:00:00"


def read_weather_workbook(path: Path, year: int) -> list[dict]:
    xl = pd.ExcelFile(path)
    source = None
    for sheet in xl.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet)
        if {"times", "month", "day", "hour", "dry", "rh", "wb"}.issubset(set(df.columns)):
            source = df
            break
    if source is None:
        raise ValueError("Excel 缺少 times/month/day/hour/dry/rh/wb 字段")

    date_col = None
    for col in source.columns:
        if str(col) in ("日期", "date", "datetime", "time") or pd.api.types.is_datetime64_any_dtype(source[col]):
            parsed = pd.to_datetime(source[col], errors="coerce")
            if parsed.notna().any():
                date_col = parsed
                break
    rows = []
    for idx, row in source[["times", "month", "day", "hour", "dry", "rh", "wb"]].dropna(how="all").iterrows():
        month = int(row["month"])
        day = int(row["day"])
        hour = int(row["hour"])
        date_text = None
        if date_col is not None and idx in date_col.index and pd.notna(date_col.loc[idx]):
            dt = date_col.loc[idx].to_pydatetime()
            date_text = f"{dt.year}/{dt.month}/{dt.day} {dt.hour}:00:00"
        if not date_text:
            date_text = weather_datetime_text(year, month, day, hour)
        rows.append(
            {
                "times": int(row["times"]),
                "month": month,
                "day": day,
                "hour": hour,
                "date": date_text,
                "dry": float(row["dry"]),
                "rh": float(row["rh"]),
                "wb": float(row["wb"]),
            }
        )
    return rows


@app.post("/api/auth/login")
def login(payload: LoginPayload):
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE username=?", (payload.username,)).fetchone()
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    token = create_token({"sub": user["id"], "username": user["username"], "role": user["role"]})
    return {"token": token, "user": {"id": user["id"], "username": user["username"], "role": user["role"]}}


@app.get("/api/me")
def me(user: dict = Depends(require_user)):
    return user


@app.get("/api/users")
def list_users(_: dict = Depends(require_admin)):
    with get_db() as db:
        rows = db.execute("SELECT id, username, role, created_at FROM users ORDER BY id").fetchall()
    return rows_to_list(rows)


@app.post("/api/users")
def create_user(payload: UserCreate, _: dict = Depends(require_admin)):
    if not payload.username or not payload.password:
        raise HTTPException(status_code=400, detail="账号和密码不能为空")
    with get_db() as db:
        try:
            db.execute(
                "INSERT INTO users(username,password_hash,role,created_at) VALUES(?,?,?,?)",
                (payload.username, hash_password(payload.password), payload.role, now()),
            )
        except Exception:
            raise HTTPException(status_code=400, detail="账号已存在")
    return {"ok": True}


@app.get("/api/weather")
def list_weather(_: dict = Depends(require_user)):
    with get_db() as db:
        rows = db.execute(
            """
            SELECT w.*, COUNT(r.id) AS row_count
            FROM weather_libraries w
            LEFT JOIN weather_rows r ON r.library_id=w.id
            GROUP BY w.id
            ORDER BY w.city, w.year DESC
            """
        ).fetchall()
    return rows_to_list(rows)


@app.get("/api/weather/cities")
def weather_cities(_: dict = Depends(require_user)):
    with get_db() as db:
        rows = db.execute(
            """
            SELECT id, city, year
            FROM weather_libraries
            ORDER BY city, year DESC
            """
        ).fetchall()
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["city"], []).append({"id": row["id"], "year": row["year"]})
    return [{"city": city, "years": years} for city, years in grouped.items()]


@app.post("/api/weather")
def create_weather(payload: WeatherPayload, _: dict = Depends(require_user)):
    t = now()
    with get_db() as db:
        try:
            cur = db.execute(
                "INSERT INTO weather_libraries(city,year,remark,created_at,updated_at) VALUES(?,?,?,?,?)",
                (payload.city, payload.year, payload.remark or "", t, t),
            )
        except Exception:
            raise HTTPException(status_code=400, detail="该城市和年份的气象数据已存在")
    return {"id": cur.lastrowid}


@app.put("/api/weather/{library_id}")
def update_weather(library_id: int, payload: WeatherPayload, _: dict = Depends(require_user)):
    with get_db() as db:
        try:
            db.execute(
                "UPDATE weather_libraries SET city=?, year=?, remark=?, updated_at=? WHERE id=?",
                (payload.city, payload.year, payload.remark or "", now(), library_id),
            )
        except Exception:
            raise HTTPException(status_code=400, detail="该城市和年份的气象数据已存在")
    return {"ok": True}


@app.delete("/api/weather/{library_id}")
def delete_weather(library_id: int, _: dict = Depends(require_user)):
    with get_db() as db:
        db.execute("DELETE FROM weather_libraries WHERE id=?", (library_id,))
    return {"ok": True}


@app.get("/api/weather/{library_id}/rows")
def weather_rows(library_id: int, _: dict = Depends(require_user)):
    with get_db() as db:
        library = db.execute("SELECT year FROM weather_libraries WHERE id=?", (library_id,)).fetchone()
        if not library:
            raise HTTPException(status_code=404, detail="气象数据不存在")
        rows = db.execute(
            """
            SELECT times,month,day,hour,date_text,dry,rh,wb
            FROM weather_rows
            WHERE library_id=?
            ORDER BY times
            LIMIT 500
            """,
            (library_id,),
        ).fetchall()
        total = db.execute("SELECT COUNT(*) AS c FROM weather_rows WHERE library_id=?", (library_id,)).fetchone()["c"]
    result = []
    for row in rows:
        date = row["date_text"] or weather_datetime_text(library["year"], row["month"], row["day"], row["hour"])
        result.append(
            {
                "times": row["times"],
                "日期": date,
                "平均温度（℃）": row["dry"],
                "平均湿度（%）": row["rh"],
                "湿球温度（℃）": row["wb"],
            }
        )
    return {"total": total, "rows": result}


@app.post("/api/weather/{library_id}/upload")
async def upload_weather(library_id: int, file: UploadFile = File(...), _: dict = Depends(require_user)):
    suffix = Path(file.filename or "weather.xlsx").suffix
    tmp = UPLOADS_DIR / f"weather_{library_id}_{now().replace(':','')}{suffix}"
    with tmp.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    with get_db() as db:
        library = db.execute("SELECT year FROM weather_libraries WHERE id=?", (library_id,)).fetchone()
    if not library:
        raise HTTPException(status_code=404, detail="气象数据不存在")
    rows = read_weather_workbook(tmp, library["year"])
    with get_db() as db:
        db.execute("DELETE FROM weather_rows WHERE library_id=?", (library_id,))
        db.executemany(
            """
            INSERT INTO weather_rows(library_id,times,month,day,hour,date_text,dry,rh,wb)
            VALUES(?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    library_id,
                    int(r["times"]),
                    int(r["month"]),
                    int(r["day"]),
                    int(r["hour"]),
                    r["date"],
                    float(r["dry"]),
                    float(r["rh"]),
                    float(r["wb"]),
                )
                for r in rows
            ],
        )
        db.execute("UPDATE weather_libraries SET updated_at=? WHERE id=?", (now(), library_id))
    return {"count": len(rows)}


@app.get("/api/projects")
def list_projects(_: dict = Depends(require_user)):
    with get_db() as db:
        rows = db.execute(
            """
            SELECT p.*, w.city AS weather_city, w.year AS weather_year, COUNT(s.id) AS system_count
            FROM projects p
            JOIN weather_libraries w ON w.id=p.weather_library_id
            LEFT JOIN systems s ON s.project_id=p.id
            GROUP BY p.id
            ORDER BY p.updated_at DESC
            """
        ).fetchall()
    return rows_to_list(rows)


@app.post("/api/projects")
def create_project(payload: ProjectPayload, _: dict = Depends(require_user)):
    t = now()
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO projects(name,weather_library_id,remark,created_at,updated_at) VALUES(?,?,?,?,?)",
            (payload.name, payload.weather_library_id, payload.remark or "", t, t),
        )
    return {"id": cur.lastrowid}


@app.post("/api/projects/{project_id}/copy")
def copy_project(project_id: int, _: dict = Depends(require_user)):
    t = now()
    with get_db() as db:
        project = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")
        cur = db.execute(
            "INSERT INTO projects(name,weather_library_id,remark,created_at,updated_at) VALUES(?,?,?,?,?)",
            (f"{project['name']} - 副本", project["weather_library_id"], project["remark"] or "", t, t),
        )
        new_project_id = cur.lastrowid
        systems = db.execute("SELECT * FROM systems WHERE project_id=? ORDER BY id", (project_id,)).fetchall()
        for system in systems:
            db.execute(
                "INSERT INTO systems(project_id,name,remark,parameters_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (new_project_id, system["name"], system["remark"] or "", system["parameters_json"], t, t),
            )
    return {"id": new_project_id}


@app.put("/api/projects/{project_id}")
def update_project(project_id: int, payload: ProjectPayload, _: dict = Depends(require_user)):
    with get_db() as db:
        db.execute(
            "UPDATE projects SET name=?, weather_library_id=?, remark=?, updated_at=? WHERE id=?",
            (payload.name, payload.weather_library_id, payload.remark or "", now(), project_id),
        )
    return {"ok": True}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int, _: dict = Depends(require_user)):
    with get_db() as db:
        db.execute("DELETE FROM projects WHERE id=?", (project_id,))
    return {"ok": True}


@app.get("/api/projects/{project_id}/systems")
def list_systems(project_id: int, _: dict = Depends(require_user)):
    with get_db() as db:
        rows = db.execute("SELECT id, project_id, name, remark, created_at, updated_at FROM systems WHERE project_id=? ORDER BY id", (project_id,)).fetchall()
    return rows_to_list(rows)


@app.post("/api/projects/{project_id}/systems")
def create_system(project_id: int, payload: SystemPayload, _: dict = Depends(require_user)):
    t = now()
    with get_db() as db:
        cur = db.execute(
            "INSERT INTO systems(project_id,name,remark,parameters_json,created_at,updated_at) VALUES(?,?,?,?,?,?)",
            (project_id, payload.name, payload.remark or "", json.dumps(DEFAULT_SYSTEM_PARAMETERS, ensure_ascii=False), t, t),
        )
    return {"id": cur.lastrowid}


@app.put("/api/systems/{system_id}")
def update_system(system_id: int, payload: SystemPayload, _: dict = Depends(require_user)):
    with get_db() as db:
        db.execute("UPDATE systems SET name=?, remark=?, updated_at=? WHERE id=?", (payload.name, payload.remark or "", now(), system_id))
    return {"ok": True}


@app.delete("/api/systems/{system_id}")
def delete_system(system_id: int, _: dict = Depends(require_user)):
    with get_db() as db:
        db.execute("DELETE FROM systems WHERE id=?", (system_id,))
    return {"ok": True}


@app.delete("/api/systems/{system_id}/results")
def delete_system_results(system_id: int, _: dict = Depends(require_user)):
    require_system(system_id)
    with get_db() as db:
        clear_system_results(db, system_id)
    return {"ok": True}


@app.get("/api/systems/{system_id}/parameters")
def get_parameters(system_id: int, _: dict = Depends(require_user)):
    system = require_system(system_id)
    params = sync_chiller_reports(load_params(system_id))
    params["config"] = sanitize_pump_configs(params.get("config", {}))
    save_params(system_id, params)
    return {"system": {k: system[k] for k in ["id", "project_id", "name", "remark", "project_name"]}, "parameters": params}


@app.put("/api/systems/{system_id}/parameters")
def put_parameters(system_id: int, payload: ParamsPayload, _: dict = Depends(require_user)):
    require_system(system_id)
    params = sync_chiller_reports(payload.parameters)
    params["config"] = sanitize_pump_configs(params.get("config", {}))
    with get_db() as db:
        row = db.execute("SELECT parameters_json FROM systems WHERE id=?", (system_id,)).fetchone()
        old_params = json.loads(row["parameters_json"]) if row else {}
        cleared = False
        if not same_json(sync_chiller_reports(old_params), params):
            clear_system_results(db, system_id)
            cleared = True
        db.execute(
            "UPDATE systems SET parameters_json=?, updated_at=? WHERE id=?",
            (json.dumps(params, ensure_ascii=False), now(), system_id),
        )
    return {"ok": True, "results_cleared": cleared}


@app.get("/api/chiller/template")
def chiller_template(_: dict = Depends(require_user)):
    tmp = Path(tempfile.gettempdir()) / "chiller_template.xlsx"
    with pd.ExcelWriter(tmp) as writer:
        pd.DataFrame(CHILLER_TEMPLATE_ROWS).to_excel(writer, sheet_name="2800RT冷机型号", index=False)
    return FileResponse(tmp, filename="变水温报告模板.xlsx")


@app.get("/api/systems/{system_id}/chiller/{report_index}/template")
def chiller_report_template(system_id: int, report_index: int, _: dict = Depends(require_user)):
    params = sync_chiller_reports(load_params(system_id))
    reports = params.get("chiller_reports", [])
    if report_index < 0 or report_index >= len(reports):
        raise HTTPException(status_code=404, detail="变水温报告不存在")
    report = reports[report_index]
    tmp = Path(tempfile.gettempdir()) / f"chiller_template_{system_id}_{report_index}.xlsx"
    with pd.ExcelWriter(tmp) as writer:
        pd.DataFrame(report.get("rows") or CHILLER_TEMPLATE_ROWS).to_excel(writer, sheet_name=report["name"][:31], index=False)
    return FileResponse(tmp, filename=f"{report['name']}_变水温报告模板.xlsx")


@app.post("/api/systems/{system_id}/chiller/{report_index}/upload")
async def upload_chiller_report(system_id: int, report_index: int, file: UploadFile = File(...), _: dict = Depends(require_user)):
    suffix = Path(file.filename or "chiller.xlsx").suffix
    tmp = UPLOADS_DIR / f"chiller_{system_id}_{report_index}_{now().replace(':','')}{suffix}"
    with tmp.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    reports = read_chiller_workbook(tmp)
    if not reports:
        raise HTTPException(status_code=400, detail="文件中没有可用的变水温报告")
    params = sync_chiller_reports(load_params(system_id))
    if report_index < 0 or report_index >= len(params.get("chiller_reports", [])):
        raise HTTPException(status_code=404, detail="变水温报告不存在")
    params["chiller_reports"][report_index]["rows"] = reports[0]["rows"]
    save_params(system_id, params)
    return {"ok": True, "report": params["chiller_reports"][report_index]}


@app.post("/api/systems/{system_id}/chiller/upload")
async def upload_chiller(system_id: int, file: UploadFile = File(...), _: dict = Depends(require_user)):
    suffix = Path(file.filename or "chiller.xlsx").suffix
    tmp = UPLOADS_DIR / f"chiller_{system_id}_{now().replace(':','')}{suffix}"
    with tmp.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    reports = read_chiller_workbook(tmp)
    params = load_params(system_id)
    params["chiller_reports"] = reports
    models = []
    for report in reports:
        name = report["name"]
        capacity = 0
        import re
        match = re.search(r"(\d+(?:\.\d+)?)\s*RT", name, flags=re.IGNORECASE)
        if match:
            capacity = float(match.group(1))
        models.append({"冷机型号": name, "冷机台数": "1", "冷机容量RT": capacity})
    params["config"]["model_num_dict"] = models
    save_params(system_id, params)
    return {"count": len(reports), "reports": reports}


def run_job(job_id: int, system_id: int, user_id: int) -> None:
    try:
        with get_db() as db:
            db.execute("UPDATE simulation_jobs SET status=?, progress=?, message=?, updated_at=? WHERE id=?", ("running", 5, "准备输入文件", now(), job_id))
            system = db.execute(
                """
                SELECT s.parameters_json, p.weather_library_id
                FROM systems s JOIN projects p ON p.id=s.project_id
                WHERE s.id=?
                """,
                (system_id,),
            ).fetchone()
            weather_rows = rows_to_list(
                db.execute("SELECT times,month,day,hour,dry,rh,wb FROM weather_rows WHERE library_id=? ORDER BY times", (system["weather_library_id"],)).fetchall()
            )
        if not weather_rows:
            raise ValueError("项目引用的气象参数为空")
        params = sync_chiller_reports(json.loads(system["parameters_json"]))
        if not params.get("chiller_reports"):
            raise ValueError("请先填写或上传变水温报告")
        values = {row["key"]: row["value"] for row in params["basic_config"]}
        if "CTpower" in values and "Ctpower" not in values:
            values["Ctpower"] = values["CTpower"]
        if "CTflow" in values and "Ctflow" not in values:
            values["Ctflow"] = values["CTflow"]
        config = dict(params["config"])
        config["model_num_dict"] = [
            {
                "冷机型号": report["name"],
                "冷机台数": str(report.get("count", 1)),
                "冷机容量RT": float(report.get("capacity_rt") or 0),
            }
            for report in params["chiller_reports"]
        ]
        config = sanitize_pump_configs(config)
        config.update(values)
        run_dir = RUNS_DIR / str(job_id)
        write_input_files(run_dir, params, weather_rows)
        with get_db() as db:
            db.execute("UPDATE simulation_jobs SET progress=?, message=?, updated_at=? WHERE id=?", (35, "正在模拟计算", now(), job_id))
        result_path = run_simulation(run_dir, config, "result.xlsx")
        with get_db() as db:
            db.execute(
                "UPDATE simulation_jobs SET status=?, progress=?, message=?, result_path=?, updated_at=? WHERE id=?",
                ("success", 100, "计算完成", str(result_path), now(), job_id),
            )
    except Exception as exc:
        with get_db() as db:
            db.execute(
                "UPDATE simulation_jobs SET status=?, message=?, error=?, updated_at=? WHERE id=?",
                ("failed", "计算失败", f"{exc}\n{traceback.format_exc()}", now(), job_id),
            )


@app.post("/api/systems/{system_id}/simulate")
def simulate(system_id: int, background: BackgroundTasks, user: dict = Depends(require_user)):
    require_system(system_id)
    with job_lock, get_db() as db:
        active = db.execute("SELECT id FROM simulation_jobs WHERE system_id=? AND status IN ('pending','running')", (system_id,)).fetchone()
        if active:
            raise HTTPException(status_code=409, detail="该系统已有计算任务进行中")
        t = now()
        cur = db.execute(
            "INSERT INTO simulation_jobs(system_id,status,progress,message,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
            (system_id, "pending", 0, "等待执行", user["id"], t, t),
        )
        job_id = cur.lastrowid
    background.add_task(run_job, job_id, system_id, user["id"])
    return {"id": job_id}


@app.get("/api/systems/{system_id}/jobs")
def list_jobs(system_id: int, _: dict = Depends(require_user)):
    with get_db() as db:
        rows = db.execute("SELECT * FROM simulation_jobs WHERE system_id=? ORDER BY id DESC LIMIT 20", (system_id,)).fetchall()
    return rows_to_list(rows)


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int, _: dict = Depends(require_user)):
    with get_db() as db:
        job = row_to_dict(db.execute("SELECT * FROM simulation_jobs WHERE id=?", (job_id,)).fetchone())
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在")
    return job


@app.get("/api/jobs/{job_id}/result")
def job_result(job_id: int, _: dict = Depends(require_user)):
    with get_db() as db:
        job = row_to_dict(db.execute("SELECT * FROM simulation_jobs WHERE id=?", (job_id,)).fetchone())
    if not job or job["status"] != "success" or not job["result_path"]:
        raise HTTPException(status_code=404, detail="结果不存在")
    path = Path(job["result_path"])
    monthly = pd.read_excel(path, sheet_name="月汇总值").fillna("").to_dict(orient="records")
    hourly = pd.read_excel(path, sheet_name="逐时值", nrows=200).fillna("").to_dict(orient="records")
    return {"monthly": monthly, "hourly": hourly}


@app.get("/api/jobs/{job_id}/download")
def download_job(job_id: int, _: dict = Depends(require_user)):
    with get_db() as db:
        job = row_to_dict(db.execute("SELECT * FROM simulation_jobs WHERE id=?", (job_id,)).fetchone())
    if not job or job["status"] != "success" or not job["result_path"]:
        raise HTTPException(status_code=404, detail="结果不存在")
    return FileResponse(job["result_path"], filename=f"simulation_result_{job_id}.xlsx")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
