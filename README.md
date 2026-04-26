# 🍂 Autumn-xxt

- 超星学习通自动化完成任务点(跨端命令行 + WebUI)
- 支持刷课、收录题库、Web 任务日志查看

**💥 警告: 本项目仅供学习测试使用，请在 24 小时内删除所有数据**

# :warning: 免责声明

- 本代码遵循 GPL-3.0 License 协议
- 本代码仅用于**学习测试**，禁止**用于盈利等**
- 他人或组织使用本代码进行的任何**违法行为**与本人无关

## :speech_balloon: 更新通知

- Autumn-xxt WebUI：
  - 支持账号密码输入
  - 支持课程列表获取
  - 支持选择课程刷课
  - 支持收录题库
  - 支持任务状态与日志查看

---

### 已实现功能

- ✅ 手机+密码登录
- ✅ cookie 缓存，重登
- ✅ 插件加载，执行
- ✅ WebUI 后端 API
- ✅ WebUI 课程选择、刷课、收录题库、日志查看
- ✅ WebUI 题库 Provider 下拉选择
- ✅ 第三方题库 Token 输入

---

## :books: 使用方法

### [1] CLI 运行

安装依赖：

    pip install -r requirements.txt

Windows 可使用：

    pip install -r requirements_win.txt

启动 CLI：

    python main.py

### [2] WebUI 运行

启动 WebUI：

    python webui.py

或直接使用 uvicorn：

    uvicorn server.app:app --host 127.0.0.1 --port 8000

浏览器打开：

    http://127.0.0.1:8000/

WebUI 当前支持：

- 输入账号密码
- 获取课程列表
- 选择课程
- 选择模式：刷课 / 收录题库
- 设置倍速
- 设置题库 URL
- 下拉选择题库 Provider / use
- 选择第三方题库接口时填写 Token
- 启动后台任务
- 查看任务状态与运行日志

---

## :books: 题库使用方法(lib.rs注意修改)

    cargo run --release

## :hammer_and_wrench: 当前重构状态

当前主入口仍保持不变：[`main.py`](main.py:8)。

也就是说，外部使用方式仍然是：
- 初始化 [`ice_study`](core/ice.py:21)
- 登录与 Cookie 处理走 [`User`](model/user.py:1)
- 课程选择走 [`Courses`](model/courses.py:1)
- 课程执行走 [`Course`](model/course.py:1)

但内部已经逐步从“单文件大类”拆成了分层结构，便于继续维护、测试和优化。

### 已完成的分层

- 运行时上下文
  - [`app/runtime.py`](app/runtime.py:1)
- HTTP / 会话层
  - [`clients/session.py`](clients/session.py:1)
  - [`clients/auth_client.py`](clients/auth_client.py:1)
  - [`clients/course_client.py`](clients/course_client.py:1)
  - [`clients/task_client.py`](clients/task_client.py:1)
- 认证与 Cookie
  - [`auth/input_provider.py`](auth/input_provider.py:1)
  - [`auth/auth_service.py`](auth/auth_service.py:1)
  - [`auth/cookie_store.py`](auth/cookie_store.py:1)
- 课程列表与选择
  - [`courses/course_repository.py`](courses/course_repository.py:1)
  - [`courses/course_selector.py`](courses/course_selector.py:1)
  - [`workflow/course_workflow.py`](workflow/course_workflow.py:1)
- 课程任务解析与调度
  - [`parsers/course_task_parser.py`](parsers/course_task_parser.py:1)
  - [`workflow/job_dispatcher.py`](workflow/job_dispatcher.py:1)
  - [`workflow/course_study_workflow.py`](workflow/course_study_workflow.py:1)
- 任务处理器
  - [`handlers/read_handler.py`](handlers/read_handler.py:1)
  - [`handlers/document_handler.py`](handlers/document_handler.py:1)
  - [`handlers/work_handler.py`](handlers/work_handler.py:1)
  - [`handlers/media_handler.py`](handlers/media_handler.py:1)
- 题库分层
  - [`repositories/tiku_repository.py`](repositories/tiku_repository.py:1)
  - [`adapters/tiku_adapter_client.py`](adapters/tiku_adapter_client.py:1)
  - [`services/tiku_service.py`](services/tiku_service.py:1)
  - [`model/tiku.py`](model/tiku.py:1) 作为兼容壳保留
- WebUI 分层
  - [`server/app.py`](server/app.py:1)
  - [`server/course_service.py`](server/course_service.py:1)
  - [`server/task_runner.py`](server/task_runner.py:1)
  - [`server/task_manager.py`](server/task_manager.py:1)
  - [`server/log_buffer.py`](server/log_buffer.py:1)
  - [`server/schemas.py`](server/schemas.py:1)
  - [`web/index.html`](web/index.html:1)

### 当前目录职责建议

- `model/`
  - 保留兼容入口与高层协调对象
  - 尽量不要再把新的细节逻辑塞回 `model/`
- `clients/`
  - 负责 HTTP 请求和共享 `httpx.Client` 生命周期
- `repositories/`
  - 负责数据库/持久化访问
- `adapters/`
  - 负责外部服务适配，如远程题库接口
- `services/`
  - 负责业务组合逻辑，如题库匹配与融合
- `parsers/`
  - 负责 HTML / JSON / 题面解析
- `handlers/`
  - 负责单一任务类型处理
- `workflow/`
  - 负责跨 handler / repository 的编排流程
- `auth/`
  - 负责输入、认证、Cookie 管理
- `app/`
  - 放运行时上下文与后续应用级配置
- `server/`
  - 放 Web API、任务管理、Web 运行服务
- `web/`
  - 放 WebUI 静态页面

### 当前兼容策略

为了不破坏现有使用方式，目前仍保留这些兼容入口：
- [`model/user.py`](model/user.py:1)
- [`model/courses.py`](model/courses.py:1)
- [`model/course.py`](model/course.py:1)
- [`model/tiku.py`](model/tiku.py:1)

它们现在的目标不是继续增长，而是：
- 保持旧入口可用
- 把请求转发到新模块
- 逐步瘦身

### 当前运行方式

CLI：

    python main.py

WebUI：

    python webui.py

如果只做题库工具：

    cargo run --release

---

## 🔗Project

- 本项目仓库：Autumn-xxt
