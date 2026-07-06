# WildIdea Web API 文档

版本：Web v1.4  
线上地址：`https://wildidea.wenyuli.site`  
OpenAPI：`https://wildidea.wenyuli.site/openapi.json`  
Swagger UI：`https://wildidea.wenyuli.site/docs`

## 1. 基本约定

所有 JSON 请求建议带：

```http
Content-Type: application/json
```

需要登录的接口带：

```http
Authorization: Bearer <access_token>
```

常见错误格式：

```json
{
  "detail": {
    "error": "AUTH_REQUIRED",
    "message": "请先登录"
  }
}
```

## 2. 登录注册

### 发送注册验证码

`POST /api/auth/email-code`

```json
{
  "email": "user@example.com"
}
```

返回：

```json
{
  "ok": true,
  "expires_in_seconds": 600
}
```

### 注册

`POST /api/auth/register`

新用户注册赠送 30 张灵感卡。`opt_in_improvement` 必须为 `true`。

```json
{
  "email": "user@example.com",
  "password": "secret12",
  "verification_code": "123456",
  "invite_code": "OPTIONAL_CODE",
  "opt_in_improvement": true
}
```

返回：

```json
{
  "access_token": "...",
  "user": {
    "id": "...",
    "email": "user@example.com",
    "role": "user",
    "status": "active",
    "credit_balance": 30,
    "improvement_consent": true,
    "created_at": "2026-07-03T..."
  }
}
```

### 登录

`POST /api/auth/login`

```json
{
  "email": "user@example.com",
  "password": "secret12"
}
```

返回同注册：`access_token` + `user`。

## 3. 当前用户

### 获取当前用户

`GET /api/me`

返回：

```json
{
  "user": {
    "id": "...",
    "email": "user@example.com",
    "role": "user",
    "credit_balance": 30
  }
}
```

### 兑换邀请码

`POST /api/me/invite-code/redeem`

```json
{
  "code": "MORE20"
}
```

返回：

```json
{
  "bonus_credits": 20,
  "credit_balance": 50
}
```

### 查看积分流水

`GET /api/me/credits`

返回：

```json
{
  "credit_balance": 50,
  "transactions": [
    {
      "id": 1,
      "amount": 30,
      "reason": "signup_bonus",
      "run_id": null,
      "invite_code_id": null,
      "metadata": {},
      "created_at": "2026-07-03T..."
    }
  ]
}
```

## 4. 生成任务

### 创建生成任务

`POST /api/runs`

线上普通用户单次最多 9 张卡。每张卡消耗 1 积分；管理员不消耗积分。

`pool_mode` 可选：

- `default`：默认分布
- `social_policy`：纯社会政策
- `algorithm`：纯算法
- `product`：纯产品

```json
{
  "problem": "如何做一个新鲜的相册 APP",
  "slot_count": 9,
  "pool_mode": "default",
  "forbid_terms": ["时间线", "AI相册"],
  "search_enabled": false
}
```

返回：

```json
{
  "run": {
    "id": "...",
    "problem": "如何做一个新鲜的相册 APP",
    "status": "queued",
    "config_snapshot": {
      "slot_count": 9,
      "pool_mode": "default",
      "credit_cost": 9
    },
    "created_at": "2026-07-03T..."
  },
  "credit_balance": 21
}
```

### 查看历史任务

`GET /api/runs`

返回当前用户最近任务：

```json
{
  "runs": [
    {
      "id": "...",
      "problem": "如何做一个新鲜的相册 APP",
      "status": "succeeded",
      "created_at": "2026-07-03T..."
    }
  ]
}
```

### 查看单个任务详情

`GET /api/runs/{run_id}`

返回任务、候选卡、事件流历史：

```json
{
  "run": {
    "id": "...",
    "status": "succeeded",
    "candidates": [
      {
        "id": "...",
        "index": 1,
        "name": "可撤回灵感缓冲器",
        "slot": "D4",
        "source_phenomenon": "Undo Send 给用户短暂撤回窗口",
        "source": "可撤回缓冲窗口",
        "proto": "高风险动作先进入短暂缓冲期...",
        "advantage": "这种方案的优势在于...",
        "desc": "在相册 app 中给每次批量删除...",
        "scores": {
          "structural_depth": 8,
          "domain_distance": 9,
          "novelty": 8,
          "applicability": 9
        },
        "quality_status": "passed",
        "refund_credit": false,
        "reroll_count": 0,
        "feedback": null
      }
    ],
    "events": []
  }
}
```

### 监听任务事件

`GET /api/runs/{run_id}/events`

这是 Server-Sent Events。浏览器 EventSource 不方便加 header 时，可以用 query token：

```text
/api/runs/{run_id}/events?token=<access_token>
```

事件格式：

```text
data: {"id":1,"event_type":"candidate_ok","payload":{...},"created_at":"..."}
```

### 删除历史任务

`DELETE /api/runs/{run_id}`

只从用户历史中隐藏，数据库保留。

```json
{
  "ok": true
}
```

### 获取任务 HTML

`GET /api/runs/{run_id}/html`

如果任务生成了 HTML 结果文件，会返回文件；否则返回 `RUN_HTML_NOT_FOUND`。

## 5. 卡片反馈

### 提交卡片反馈

`POST /api/candidates/{candidate_id}/feedback`

`label` 可选：

- `useful`：有用
- `weak_obscure`：晦涩难懂
- `weak_off_topic`：不够相关
- `weak_too_common`：太常规
- `weak_unusable`：不可落地
- `weak_other`：其他，必须带 `comment`

```json
{
  "label": "weak_off_topic",
  "rating": 2,
  "comment": "和我的问题不太相关"
}
```

返回：

```json
{
  "ok": true,
  "feedback_id": "...",
  "feedback": {
    "id": "...",
    "rating": 2,
    "label": "weak_off_topic",
    "comment": "和我的问题不太相关",
    "adopted": false,
    "created_at": "2026-07-03T..."
  }
}
```

### 记录交互事件

`POST /api/interaction-events`

用于记录点击、复制、展开等交互。

```json
{
  "run_id": "...",
  "candidate_id": "...",
  "event_type": "copy_section",
  "payload": {
    "section": "idea"
  }
}
```

返回：

```json
{
  "ok": true,
  "event_id": 123
}
```

## 6. 文件下载

### 下载生成产物

`GET /api/artifacts/{artifact_id}`

需要登录；只能下载自己任务下的文件。

## 7. 管理员接口

管理员接口需要 `role = admin` 的账号。

### 用户、任务、指标、队列

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/admin/users` | 最近 200 个用户 |
| GET | `/api/admin/runs` | 最近 200 个任务 |
| GET | `/api/admin/metrics` | 用户数、任务状态数、反馈数、积分总余额 |
| GET | `/api/admin/queue` | 队列、worker、容量和最近日志 |
| GET | `/api/admin/audit-logs` | 最近 200 条管理员审计日志 |

### 反馈和卡片日志

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/admin/feedback` | 最近反馈，包含用户、问题、卡片、评分和反馈原因 |
| GET | `/api/admin/card-logs?page=1&page_size=20` | 最近卡片日志，每页最多 20 条 |
| GET | `/api/admin/feedback.xlsx` | 导出 Excel，全量任务、卡片、反馈和无反馈数据 |

### 邀请码

#### 列表

`GET /api/admin/invite-codes`

```json
{
  "invite_codes": [
    {
      "id": "...",
      "code": "MORE20",
      "bonus_credits": 20,
      "max_redemptions": 10,
      "redeemed_count": 2,
      "status": "active",
      "created_at": "2026-07-03T..."
    }
  ]
}
```

#### 创建

`POST /api/admin/invite-codes`

```json
{
  "code": "MORE20",
  "bonus_credits": 20,
  "max_redemptions": 10,
  "expires_at": null
}
```

#### 禁用

`POST /api/admin/invite-codes/{invite_code_id}/disable`

```json
{
  "ok": true
}
```

#### 删除

`DELETE /api/admin/invite-codes/{invite_code_id}`

未兑换过的邀请码会硬删除；已兑换过的邀请码会标记为 `deleted`，后台不再展示，也不能继续兑换，但保留历史记录。

```json
{
  "ok": true,
  "mode": "hard"
}
```

或：

```json
{
  "ok": true,
  "mode": "soft"
}
```

### 调整用户积分

`POST /api/admin/users/{user_id}/credits`

```json
{
  "amount": 100,
  "reason": "manual_bonus"
}
```

`amount` 可以为正数或负数。

## 8. 最小调用示例

### 登录并创建任务

```bash
BASE="https://wildidea.wenyuli.site"

TOKEN=$(curl -sS "$BASE/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"secret12"}' \
  | jq -r .access_token)

curl -sS "$BASE/api/runs" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "problem": "如何做一个新鲜的相册 APP",
    "slot_count": 9,
    "pool_mode": "default",
    "forbid_terms": ["时间线"]
  }'
```

### 监听生成进度

```bash
curl -N "$BASE/api/runs/<run_id>/events?token=$TOKEN"
```

### 提交反馈

```bash
curl -sS "$BASE/api/candidates/<candidate_id>/feedback" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"label":"useful","rating":5}'
```
