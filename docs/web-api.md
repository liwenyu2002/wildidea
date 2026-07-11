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

请求体本身不满足 schema（比如密码太短、缺字段）时，返回 422，形状不一样，`error`/`message` 直接在顶层，没有 `detail` 包裹：

```json
{
  "error": "VALIDATION_ERROR",
  "message": "String should have at least 6 characters"
}
```

## 2. 登录注册

### 发送验证码

`POST /api/auth/email-code`

`purpose` 可选，默认 `register`：

- `register`：注册验证码，邮箱已注册会返回 409 `EMAIL_EXISTS`
- `reset`：找回密码验证码，邮箱不存在会返回 404 `USER_NOT_FOUND`

```json
{
  "email": "user@example.com",
  "purpose": "register"
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

### 修改密码

`POST /api/auth/change-password`（需要登录）

```json
{
  "old_password": "secret12",
  "new_password": "newsecret12"
}
```

旧密码错误返回 400 `INVALID_PASSWORD`。成功后旧 token（以及其他设备上的旧 token）全部失效，返回一个新 token：

```json
{
  "access_token": "..."
}
```

### 忘记密码

先用 `purpose=reset` 调 `POST /api/auth/email-code` 拿验证码，再调：

`POST /api/auth/reset-password`

```json
{
  "email": "user@example.com",
  "code": "123456",
  "new_password": "newsecret12"
}
```

成功后自动登录，返回新 token，此前签发的 token 全部失效：

```json
{
  "access_token": "..."
}
```

### 退出所有设备

`POST /api/auth/logout-all`（需要登录）

使当前账号所有已签发的 token 失效。

```json
{
  "ok": true
}
```

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

`risk_profile` 可选，默认 `pragmatic`：

- `pragmatic`：现状阈值（默认，SD>=校准线 且 NV>=7 且 AP>=9）
- `explore`：更宽松的远域/高风险探索阈值（SD>=校准线 且 NV>=7 且 AP>=7 且 (DD>=7 或 UNX>=8)）

```json
{
  "problem": "如何做一个新鲜的相册 APP",
  "slot_count": 9,
  "pool_mode": "default",
  "risk_profile": "pragmatic",
  "forbid_terms": ["时间线", "AI相册"]
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

### 深化候选方案

`POST /api/runs/{run_id}/candidates/{candidate_id}/deepen`

免积分；按用户限流 10 次/10 分钟。基于候选卡的 name/source/proto/desc/fail 和任务的 `problem`，让模型生成一份「最小可证伪实验方案 + fail 前提验证步骤」的深化材料，落盘为 `Artifact(kind="deepen")`。

同一张候选卡重复调用是幂等的：直接返回已落盘的内容，既不重新调用模型也不占用限流额度。

```json
{
  "content": "## 最小可证伪实验方案\n...\n\n## fail 前提验证步骤\n...",
  "artifact_id": "..."
}
```

候选不存在或不属于该任务返回 404 `CANDIDATE_NOT_FOUND`；模型调用失败返回 502：

```json
{
  "detail": {
    "error": "DEEPEN_FAILED",
    "message": "..."
  }
}
```

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

## 6. 社区卡片

### 列表

`GET /api/community/cards?page=1&page_size=20`

需要登录。返回按分享时间倒序的社区卡片，`page_size` 最大 40。

```json
{
  "items": [
    {
      "id": "...",
      "candidate_id": "...",
      "note": "分享者留言",
      "status": "active",
      "shared_by": "us***r@example.com",
      "problem": "如何做一个新鲜的相册 APP",
      "candidate": { "...": "同 /api/runs/{run_id} 里的候选卡结构" },
      "counts": { "useful": 3, "weak": 1, "total": 4 },
      "viewer_feedback": null
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1,
  "total_pages": 1
}
```

### 分享一张卡到社区

`POST /api/community/cards`

```json
{
  "candidate_id": "...",
  "note": "可选留言"
}
```

已退款卡片不可分享，返回 422 `REFUNDED_CANDIDATE_NOT_SHAREABLE`。同一张卡重复分享返回 `already_shared: true`，不会重复建帖。

```json
{
  "ok": true,
  "already_shared": false,
  "post": { "...": "同上面列表里的单条结构" }
}
```

### 对社区卡片反馈

`POST /api/community/cards/{post_id}/feedback`

`label` 取值同卡片反馈（见第 5 节）。同一用户对同一帖子的反馈是 upsert。

```json
{
  "label": "useful",
  "rating": 5
}
```

```json
{
  "ok": true,
  "feedback": { "id": "...", "rating": 5, "label": "useful", "comment": null, "created_at": "2026-07-03T..." },
  "post": { "...": "包含更新后的 counts" }
}
```

## 7. 文件下载

### 下载生成产物

`GET /api/artifacts/{artifact_id}`

需要登录；只能下载自己任务下的文件。

## 8. 管理员接口

管理员接口需要 `role = admin` 的账号。

### 用户、任务、指标、队列

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/admin/users` | 最近 200 个用户 |
| GET | `/api/admin/runs` | 最近 200 个任务 |
| GET | `/api/admin/metrics` | 用户数、任务状态数、反馈数、积分总余额 |
| GET | `/api/admin/queue` | 队列、worker、容量和最近日志 |
| GET | `/api/admin/audit-logs` | 最近 200 条管理员审计日志 |
| GET | `/api/admin/credit-reconciliation` | 找出 `credit_balance` 和流水求和对不上的用户 |
| POST | `/api/admin/anchor-stats/refresh` | 聚合反馈生成锚点 weak/strong 统计并落盘 |

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

### 刷新锚点统计

`POST /api/admin/anchor-stats/refresh`

聚合 `Feedback` + `CommunityFeedback`，按 anchor_id（如 `D1-05`）生成 `{"weak", "strong"}` 计数，写入 `anchor_stats.json`（路径由 `WILDIDEA_ANCHOR_STATS_PATH` 环境变量控制，未设置时默认在 `output_dir` 同级的 `data/anchor_stats.json`）。核心包的 `domain_pool.sample_pool(..., stats_path=...)` 之后会读取这份文件，按历史表现加权抽样；文件不存在时退回均匀抽样。

```json
{
  "anchors": 12,
  "path": "/.../outputs/data/anchor_stats.json"
}
```

### 积分对账

`GET /api/admin/credit-reconciliation`

返回 `credit_balance` 与该用户 `credit_transactions.amount` 求和不一致的账号，正常情况下应为空列表。

```json
{
  "mismatches": [
    {
      "id": "...",
      "email": "user@example.com",
      "balance": 35,
      "ledger_sum": 30
    }
  ]
}
```

## 9. 最小调用示例

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
