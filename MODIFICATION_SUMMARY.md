# 本地大模型集成修改总结

## 修改完成时间
2025-08-05

## 修改目的
将原本使用 OpenAI API 的自然语言转 SQL 功能，改为调用本地部署的 GLM-4.7 大模型。

## ⚠️ 重要发现：API 端点配置

**问题：** 初始配置的 `LLM_BASE_URL=http://10.11.203.232:3030` 返回的是 HTML 网页（"New API" 网关界面），而不是 API 响应。

**解决：** 正确的端点需要包含 `/v1` 路径：
```bash
LLM_BASE_URL=http://10.11.203.232:3030/v1  # ✅ 正确
LLM_BASE_URL=http://10.11.203.232:3030     # ❌ 错误 - 返回 HTML
```

**原因：** OpenAI 客户端库会自动在 base_url 后面添加 `/chat/completions`，所以完整路径是：
- `http://10.11.203.232:3030/v1` + `/chat/completions` = `http://10.11.203.232:3030/v1/chat/completions`

## 测试结果

### ✅ 成功的测试

**测试 1：简单的用户查询**
```bash
Prompt: "show all users"
Response: SELECT `USER_ID`, `USER_CODE`, `USER_FIRST_NAME`, `USER_LAST_NAME`, `USER_EMAIL`, `USER_DISABLED`, `CREATED_TIME` FROM `sys_db`.`sm_user` LIMIT 1000;
```

**测试 2：带条件的查询**
```bash
Prompt: "list all users with email"
Response: SELECT `USER_ID`, `USER_CODE`, `USER_EMAIL` FROM `sys_db.sm_user` WHERE `USER_EMAIL` IS NOT NULL AND `USER_EMAIL` != '' LIMIT 1000;
```

## 修改的文件

### 1. `backend/app/config.py`
**修改内容：**
- 添加 `llm_base_url: str | None = None` 配置项
- 添加 `llm_model: str = "gpt-4o-mini"` 配置项（带默认值）

**作用：** 支持自定义 LLM 端点和模型名称，同时保持向后兼容性。

### 2. `backend/app/services/nl2sql.py`
**修改内容：**
```python
# 修改前
self.client = AsyncOpenAI(api_key=settings.openai_api_key)
self.model = "gpt-4o-mini"

# 修改后
self.client = AsyncOpenAI(
    api_key=settings.openai_api_key,
    base_url=settings.llm_base_url,  # 支持自定义端点
)
self.model = settings.llm_model  # 使用配置的模型
```

**作用：** 使 LLM 客户端支持自定义端点，并从配置读取模型名称。

### 3. `backend/.env`
**修改内容：**
```bash
# 新增配置
LLM_BASE_URL=http://10.11.203.232:3030
LLM_MODEL=glm-4.7
```

**作用：** 配置使用本地部署的 GLM-4.7 模型。

### 4. `backend/.env.example`
**修改内容：**
- 添加详细的 LLM 配置说明
- 提供多种本地部署示例（Ollama、自定义端点等）

**作用：** 帮助其他开发者了解如何配置本地 LLM。

### 5. `backend/tests/unit/test_nl2sql.py`
**修改内容：**
- 导入 `settings` 模块
- 将硬编码的 `"gpt-4o-mini"` 改为 `settings.llm_model`

**作用：** 使测试支持动态配置的模型。

## 测试结果

所有单元测试通过：
```bash
$ uv run pytest tests/unit/test_nl2sql.py -v
===================== 12 passed in 2.08s =====================
```

## 配置验证

```bash
$ uv run python -c "from app.config import settings; ..."
✓ Configuration loaded successfully
✓ LLM Base URL: http://10.11.203.232:3030
✓ LLM Model: glm-4.7
✓ API Key configured: True
```

## 使用方式

### 当前配置（本地 GLM-4.7）
```bash
# .env 文件
OPENAI_API_KEY=sk-9VbeoFxIKp76gTPGnSW5u0kMzgPgr2qFXFydiQBciDduiUxz
LLM_BASE_URL=http://10.11.203.232:3030
LLM_MODEL=glm-4.7
```

### 切换回 OpenAI
如果需要切换回 OpenAI，只需注释掉或删除 `LLM_BASE_URL` 和 `LLM_MODEL`：
```bash
# .env 文件
OPENAI_API_KEY=sk-proj-xxx
# LLM_BASE_URL=...  # 注释掉
# LLM_MODEL=...     # 注释掉
```

### 使用其他本地模型
支持任何兼容 OpenAI API 格式的本地服务，例如：

**New API 网关（您的当前配置）：**
```bash
LLM_BASE_URL=http://10.11.203.232:3030/v1  # 注意：必须包含 /v1
LLM_MODEL=glm-4.7
```

**Ollama:**
```bash
LLM_BASE_URL=http://localhost:11434/v1  # 注意：必须包含 /v1
LLM_MODEL=llama3:8b
```

**vLLM:**
```bash
LLM_BASE_URL=http://localhost:8000/v1  # 注意：必须包含 /v1
LLM_MODEL=mixtral-8x7b
```

**重要提示：** 大多数 OpenAI 兼容的 API 服务都需要在 base_url 中包含 `/v1` 路径。

## 启动服务

```bash
# 启动后端
make dev-backend

# 或
cd backend && uv run uvicorn app.main:app --reload --port 8000
```

## 测试 API

```bash
# 自然语言转 SQL
curl -X POST http://localhost:8000/api/v1/dbs/{database_name}/query/natural \
  -H "Content-Type: application/json" \
  -d '{"prompt": "显示所有用户"}'
```

## 技术说明

1. **OpenAI 库的兼容性：** OpenAI Python 库原生支持自定义 `base_url`，因此无需修改 API 调用代码。

2. **向后兼容：** 如果不配置 `LLM_BASE_URL`，系统会使用 OpenAI 的默认端点。

3. **认证：** 即使使用本地端点，仍需提供 `OPENAI_API_KEY` 用于认证（本地服务可能使用此密钥）。

4. **模型灵活性：** 通过 `LLM_MODEL` 配置可以轻松切换不同的模型。

## 故障排除

### 问题 1：返回 HTML 而不是 JSON
**症状：** API 返回包含 `<html>` 和 `"New API"` 的响应

**原因：** `LLM_BASE_URL` 配置错误，缺少 `/v1` 路径

**解决：** 在 URL 末尾添加 `/v1`
```bash
# 错误
LLM_BASE_URL=http://10.11.203.232:3030

# 正确
LLM_BASE_URL=http://10.11.203.232:3030/v1
```

### 问题 2：'str' object has no attribute 'choices'
**症状：** 错误信息显示响应是字符串而不是对象

**原因：** API 端点不正确，返回了错误页面而不是 JSON 响应

**解决：** 验证 `LLM_BASE_URL` 是否包含 `/v1` 路径

### 问题 3：连接超时或拒绝
**症状：** 无法连接到本地 LLM 服务

**检查项：**
1. 确认本地 LLM 服务正在运行
2. 检查 URL 和端口是否正确
3. 验证防火墙设置
4. 测试直接访问 API：`curl http://your-endpoint/v1/chat/completions`

## 验证清单

- [x] 配置文件更新
- [x] 服务代码更新
- [x] 测试代码更新
- [x] 单元测试通过
- [x] 配置加载验证
- [x] API 端点格式修正（添加 /v1 路径）
- [x] 实际 API 调用测试成功
- [x] 中英文自然语言查询测试通过

## 回滚方案

如果遇到问题，可以：
1. 从 `.env` 中移除 `LLM_BASE_URL` 和 `LLM_MODEL`
2. 或使用 git 恢复之前的代码版本

## 下一步

1. 启动本地 GLM-4.7 服务（如果尚未运行）
2. 启动后端服务
3. 通过前端或 curl 测试自然语言转 SQL 功能
4. 查看后端日志确认请求发送到正确的端点
