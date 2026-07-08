# 制冷站能耗模拟平台

## 运行方式

1. 安装 Python 3.11+。
2. 在项目根目录执行：

```powershell
python -m pip install -r backend\requirements.txt
backend\run_server.bat
```

3. 浏览器访问：

```text
http://服务器IP:8000
```

默认管理员：

```text
账号：admin
密码：admin123456
```

生产部署前必须设置环境变量：

```powershell
$env:APP_SECRET="替换为足够长的随机字符串"
$env:ADMIN_USERNAME="admin"
$env:ADMIN_PASSWORD="替换为强密码"
```

## 已实现范围

- 真实账号密码登录，管理员可创建账号。
- 项目管理：新建、编辑、删除、引用城市气象参数。
- 参数库：城市气象参数新建、编辑、删除、Excel 导入、表格预览。
- 项目内系统管理：新建、编辑、删除。
- 系统参数录入：系统配置、修正系数、基础配置、负载率、变水温报告。
- 变水温报告支持模板下载、Excel 上传、多报告维护、冷机容量 RT 和台数维护。
- 后台异步模拟任务：用户离开页面后任务继续运行。
- 模拟结果：月汇总、逐时预览、图表展示、Excel 下载。

## 数据文件要求

气象参数 Excel 需要包含：

```text
times, month, day, hour, dry, rh, wb
```

变水温报告 Excel 每个 sheet 对应一个冷机型号，需要包含：

```text
CondEWT
```

其他横向列为负载率，例如：

```text
1, 0.85, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.15
```

如果 sheet 名不包含 `2800RT` 这类容量信息，需要在页面中手动填写冷机容量 RT。

## 目录说明

- `backend/app/main.py`：API、鉴权、项目/系统/参数库、任务接口。
- `backend/app/simulation/engine.py`：服务化后的能耗模拟计算。
- `backend/app/simulation/io.py`：数据库参数到模拟输入 Excel 的转换。
- `backend/app/static/`：前端页面。
- `backend/data/app.db`：SQLite 数据库，首次启动自动创建。
- `backend/storage/runs/`：每次模拟任务的输入文件和结果文件。

## 注意事项

当前任务队列使用 FastAPI 后台任务，适合单机或中小规模服务器部署。若后续需要多进程、多服务器部署，应把任务队列替换为 Celery/RQ，并把 SQLite 换成 PostgreSQL。
