# 批量构建 API 契约（3.0 MVP）

## 适用范围

本说明面向 Skill 3.0 MVP，描述本地批量构建接口的最小使用方式。

当前本地示例地址：

```text
http://127.0.0.1:1128
```

## 核心原则

- Skill 只传自然语言需求，不传字段级设计
- Skill 通过脚本调用 API，不在对话中手写最终请求体
- Skill 以 `request_id` 作为流中断后的状态补查依据

## 提交接口

```http
POST /api/bitable/build/batch
Content-Type: application/json
Accept: text/event-stream
```

## 请求体结构

```json
{
  "client_batch_id": "batch-20260423-001",
  "items": [
    {
      "client_item_id": "req-001",
      "user_requirement": "我需要一个招聘管理应用，用于统一管理职位需求、候选人、面试安排和 offer 审批。"
    }
  ],
  "defaults": {
    "language": "zh",
    "with_generate_flowchart": false,
    "extra": {
      "prompt_variant": "current"
    }
  },
  "max_concurrency": 1,
  "continue_on_error": true
}
```

## 关键字段说明

- `client_batch_id`
  - 每次提交必须唯一
  - 由脚本生成

- `items[].client_item_id`
  - 同一批次内必须唯一
  - 由脚本生成

- `items[].user_requirement`
  - 来自确认后的中间表清单
  - 必须是自然语言业务需求

- `defaults.with_generate_flowchart`
  - 默认是否生成流程图
  - 可根据澄清阶段结果决定

## SSE 事件

接口返回 `text/event-stream`，Skill 侧需要持续读取，直到收到最终事件或连接异常中断。

### `batch_accepted`

表示批次已接收。

关键字段：

- `client_batch_id`
- `total_items`
- `request_id`

要求：

- 一旦收到 `request_id`，立即保存到本地轻量运行态

### `job_progress`

表示单个 item 的阶段或子阶段进度更新。

关键字段：

- `client_item_id`
- `stage`
- `sub_stage`（可选）
- `status`
- `message`

规则：

- `message` 可以直接展示给用户
- 不需要在 Skill 侧硬编码 stage 到中文文案的复杂映射

### `job_complete`

表示某个 item 到达终态。

成功时：

- `status = success`
- 包含 `result.url`
- 包含 `result.metadata`

失败时：

- `status = failed`
- 包含 `error.code`
- 包含 `error.message`

### `batch_complete`

表示整个批次到达终态。

关键字段：

- `request_id`
- `status`
- `summary.total`
- `summary.success`
- `summary.failed`
- `items`

## 状态查询接口

```http
GET /api/bitable/build/batch/{request_id}/status
```

用途：

- SSE 在 `batch_accepted` 之后中断时补查状态
- 获取当前运行中状态或最终状态

返回体结构与 `batch_complete` 事件兼容，可能出现：

- `status = running`
- `status = success`
- `status = failed`
- `status = partial_success`

## Skill 侧最小使用流程

1. 调用脚本拼装最终 batch payload
2. 提交 `POST /api/bitable/build/batch`
3. 持续消费 SSE
4. 收到 `batch_accepted` 后保存 `request_id`
5. 若流中断且已知 `request_id`，调用状态查询接口
6. 将当前或最终状态反馈给用户

## 不要这样做

- 不要让模型直接构造最终 API payload
- 不要把字段级 schema 当作 `user_requirement` 传入
- 不要因为 SSE 一段时间安静，就立刻判断任务失败
- 不要在 MVP 阶段实现失败 item 自动重试
