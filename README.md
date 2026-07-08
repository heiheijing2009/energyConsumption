# 制冷站能耗模拟平台

本仓库包含制冷站能耗模拟平台的后端服务、前端页面和已导入城市气象参数库。

## 快速启动

```powershell
python -m pip install -r backend\requirements.txt
backend\run_server.bat
```

访问：

```text
http://服务器IP:8000
```

默认管理员：

```text
账号：admin
密码：admin123456
```

生产部署前请设置环境变量：

```powershell
$env:APP_SECRET="替换为足够长的随机字符串"
$env:ADMIN_USERNAME="admin"
$env:ADMIN_PASSWORD="替换为强密码"
```

## 目录

- `backend/app/`：FastAPI 后端、仿真引擎、静态前端页面。
- `backend/data/app.db`：SQLite 数据库，已包含城市气象参数库。
- `backend/storage/`：运行时上传文件和模拟结果目录，不纳入版本库。

## 数据库说明

随仓库提交的 `backend/data/app.db` 保留：

- 默认管理员账号。
- 城市气象参数库。

不包含：

- 测试项目。
- 测试系统。
- 历史模拟任务和结果。
