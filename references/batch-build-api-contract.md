# 批量构建 API 契约（3.0 MVP）

## 适用范围

本说明面向 Skill 3.0 MVP，描述通过 `basebuilder-cli` 调用本地批量构建接口的最小使用方式。

当前本地示例地址：

```text
http://127.0.0.1:1128
```

## 核心原则

- Skill 只传自然语言需求，不传字段级设计
- Skill 通过 `build_batch_payload.py` 生成最终请求体，不在对话中手写最终请求体
- Skill 通过 `npx basebuilder-cli` 提交请求、消费 SSE 和查询状态
- Skill 以 `request_id` 作为构建命令中断后的状态补查依据

## CLI 调用方式

提交批量构建：

```bash
npx basebuilder-cli build --input "<batch payload 路径>" --json --base-url "http://127.0.0.1:1128"
```

状态补查：

```bash
npx basebuilder-cli status "<request_id>" --json --base-url "http://127.0.0.1:1128"
```

说明：

- `--input` 接收 `build_batch_payload.py` 生成的完整 batch payload JSON
- `--json` 会输出 JSON Lines，便于智能体逐行解析事件
- `--base-url` 可省略；默认读取 `BASEBUILD_BASE_URL`，没有环境变量时使用 `http://127.0.0.1:1128`

## 底层提交接口

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

接口返回 `text/event-stream`。Skill 侧不直接解析 HTTP SSE，由 `basebuilder-cli` 读取并转换为 JSON Lines 输出，直到收到最终事件或连接异常中断。

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
2. 运行 `npx basebuilder-cli build --input <payload> --json --base-url <url>`
3. 逐行读取 CLI 输出的 JSON Lines 事件
4. 收到 `batch_accepted` 后记录 `request_id`
5. 若构建命令中断且已知 `request_id`，运行 `npx basebuilder-cli status <request_id> --json --base-url <url>`
6. 将当前或最终状态反馈给用户

## 不要这样做

- 不要让模型直接构造最终 API payload
- 不要把字段级 schema 当作 `user_requirement` 传入
- 不要绕过 `basebuilder-cli` 在对话中手写 HTTP/SSE 逻辑
- 不要因为 CLI 一段时间只输出 keepalive 或暂时安静，就立刻判断任务失败
- 不要在 MVP 阶段实现失败 item 自动重试
