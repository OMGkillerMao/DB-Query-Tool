# 🚀 本地大模型集成 - 快速参考

## ✅ 配置成功

您的系统已成功配置为使用本地 GLM-4.7 模型进行自然语言转 SQL。

## 当前配置

```bash
# .env 文件
OPENAI_API_KEY=sk-9VbeoFxIKp76gTPGnSW5u0kMzgPgr2qFXFydiQBciDduiUxz
LLM_BASE_URL=http://10.11.203.232:3030/v1  # ⚠️ 注意：必须包含 /v1
LLM_MODEL=glm-4.7
```

## 测试示例

### 英文查询
```bash
curl -X POST http://localhost:8000/api/v1/dbs/sys_db/query/natural \
  -H "Content-Type: application/json" \
  -d '{"prompt": "show all users"}'
```

**结果：**
```json
{
  "sql": "SELECT `USER_ID`, `USER_CODE`, `USER_FIRST_NAME`, `USER_LAST_NAME`, `USER_EMAIL`, `USER_DISABLED`, `CREATED_TIME` FROM `sys_db`.`sm_user` LIMIT 1000;",
  "explanation": "Generated SQL from: show all users"
}
```

### 中文查询
```bash
curl -X POST http://localhost:8000/api/v1/dbs/sys_db/query/natural \
  -H "Content-Type: application/json" \
  -d '{"prompt": "查询所有用户的邮箱"}'
```

**结果：**
```json
{
  "sql": "SELECT `USER_EMAIL` FROM `sys_db.sm_user` LIMIT 1000",
  "explanation": "Generated SQL from: 查询所有用户的邮箱"
}
```

### 复杂查询
```bash
curl -X POST http://localhost:8000/api/v1/dbs/sys_db/query/natural \
  -H "Content-Type: application/json" \
  -d '{"prompt": "list all users with email"}'
```

**结果：**
```json
{
  "sql": "SELECT `USER_ID`, `USER_CODE`, `USER_EMAIL` FROM `sys_db.sm_user` WHERE `USER_EMAIL` IS NOT NULL AND `USER_EMAIL` != '' LIMIT 1000;",
  "explanation": "Generated SQL from: list all users with email"
}
```

## ⚠️ 重要提示

### API 端点格式
**必须**在 `LLM_BASE_URL` 中包含 `/v1` 路径：

```bash
# ✅ 正确
LLM_BASE_URL=http://10.11.203.232:3030/v1

# ❌ 错误 - 会返回 HTML 页面
LLM_BASE_URL=http://10.11.203.232:3030
```

### 原因说明
OpenAI 客户端库会自动在 `base_url` 后面添加 `/chat/completions`：
- 配置：`http://10.11.203.232:3030/v1`
- 实际调用：`http://10.11.203.232:3030/v1/chat/completions` ✅

如果配置成：
- 配置：`http://10.11.203.232:3030`
- 实际调用：`http://10.11.203.232:3030/chat/completions` ❌ (返回 HTML)

## 启动服务

```bash
# 启动后端
make dev-backend

# 或手动启动
cd backend && uv run uvicorn app.main:app --reload --port 8000
```

## 验证配置

```bash
cd backend
uv run python -c "from app.config import settings; print('✓ LLM Base URL:', settings.llm_base_url); print('✓ LLM Model:', settings.llm_model)"
```

**预期输出：**
```
✓ LLM Base URL: http://10.11.203.232:3030/v1
✓ LLM Model: glm-4.7
```

## 切换回 OpenAI

如需切换回 OpenAI，编辑 `.env` 文件：

```bash
# 注释掉或删除本地配置
OPENAI_API_KEY=sk-your-openai-key
# LLM_BASE_URL=http://10.11.203.232:3030/v1
# LLM_MODEL=glm-4.7
```

## 故障排除

### 问题：返回 HTML 而不是 JSON
**解决：** 检查 `LLM_BASE_URL` 是否包含 `/v1`

### 问题：连接超时
**解决：**
1. 确认本地 GLM 服务正在运行
2. 测试端点：`curl http://10.11.203.232:3030/v1/chat/completions`

### 问题：API 密钥错误
**解决：** 确保 `OPENAI_API_KEY` 设置正确

## 修改的文件

1. ✅ `backend/app/config.py` - 添加 LLM 配置选项
2. ✅ `backend/app/services/nl2sql.py` - 支持自定义端点
3. ✅ `backend/.env` - 配置本地 GLM 服务
4. ✅ `backend/.env.example` - 更新文档
5. ✅ `backend/tests/unit/test_nl2sql.py` - 更新测试

## 测试结果

- ✅ 所有单元测试通过 (12/12)
- ✅ 英文自然语言查询成功
- ✅ 中文自然语言查询成功
- ✅ 复杂查询（带条件）成功

## 详细文档

完整的修改说明和技术细节请参阅：
- `MODIFICATION_SUMMARY.md` - 完整修改总结
- `CLAUDE.md` - 项目架构和代码规范

---

**状态：** 🟢 完全正常运行
**模型：** GLM-4.7
**端点：** http://10.11.203.232:3030/v1
**最后测试：** 2025-08-05
