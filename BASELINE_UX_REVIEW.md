# DataGate baseline 复核与 UX 交付

日期：2026-10-17（America/Los_Angeles）。本地分支：`feature`；审查基点：`21f5abc`（Datagate baseline）。本次改动尚未提交。保留了开始任务前就存在的 `frontend/package-lock.json` 修改，没有编辑该文件，也没有切换分支。

## 结论

核心 baseline 路径已经实现，现有 43 项后端测试、前端 lint/build 均通过。本次 Chrome 实测了授权账户、预览、额外隐藏、明确批准、本地发送、收据、禁止用途，以及更改表单后清除旧预览。390px 手机布局未发现横向溢出，技术详情展开后页面宽度仍为 390px。

但目前不应宣称“完全符合所有 baseline 要求”：发现一项现有测试未覆盖的 CSV 校验缺口（下文 B1），且第二位队员的人工作业验收和 accepted baseline commit 仍无记录。助手复核不替代团队的人工作业验收。

## 阅读范围与产品理解

已阅读仓库现有的 12 份 Markdown：AGENTS.md、PROJECT_CONTEXT.md、API_CONTRACT.md、TEAM_WORKFLOW.md、README.md、IMPLEMENTATION_GUIDE.md、TROJANHACKS_TEAM_ROADMAP.md、RECOMMENDED_PROJECT_SCOPE.md、MENTOR_BRIEF_AND_TEAM_PLAN.md，以及 prompts 下的三份任务提示。范围以 PROJECT_CONTEXT 为准，接口以 API_CONTRACT v1 为准。

DataGate 的用户是支持分析员：选择已获授权的公司反馈来源，为指定任务准备最少必要的消息，检查强制脱敏后的内容并允许进一步隐藏，批准后由后端再次检查权限和版本，再向本地测试接收器发送。它当前不产生 AI 总结，也不提供生产身份认证。SQLite 用来保存规则、请求状态和元数据；用户选的 dataset 实际是后台预置的反馈集合，不是在操作数据库。

工作流是先完成一个 baseline，经第二位队员复现与接受后，再分配有边界的后续任务。本次由当前用户明确授权检查 baseline 和优化前端 UX，范围为前端组件、标签、相关状态处理和交付文档；后端实现仅审查，没有修改。

## Baseline 证据

| 要求 | 本次证据与结论 |
| --- | --- |
| 冻结技术栈、两份合成数据、两个 demo 身份 | React/TypeScript/Vite、FastAPI/Pydantic、sqlite3、标准库转换；两份种子 fixture 与独立账户存在 |
| 令牌确定身份及权限隔离 | 后端从 session token 取 account；现有测试覆盖 dataset、draft/review/send、receipt 的跨账户拒绝与请求体身份伪造 |
| Owner 规则优先、禁止用途/接收方/共享模式零调用 | policy/workflow 检查与现有对应测试通过；浏览器禁止 training 用途显示 Blocked 与接收器未被调用 |
| 后端只保留 message，再处理 email/phone | transform 实现与内容/未知列/Unicode 测试通过 |
| 精确预览与额外整条隐藏 | 后端 canonical JSON/hash，浏览器隐藏后 review 1→2；接收器收到 placeholder，非原消息 |
| 审核绑定 source/policy/review/payload，拒绝陈旧批准 | 版本、source hash、policy fingerprint、review/hash 校验及对应测试通过 |
| Preview、Review、Send 的当前授权检查 | workflow 每个受保护步骤读取当前规则；撤权与禁共享测试通过 |
| 原子 dispatch、唯一 adapter、无自动重试 | 条件 UPDATE 争抢发送权；六线程并发测试只产生一次实际调用；调用仅位于 Workflow.send |
| 真实本地接收与失败记录 | capturing/failing adapter 测试通过；浏览器成功后显示 local demo 与一次调用，没有外部模型结果 |
| 收据仅元数据、仅创建者读取、撤权后仍可读 | 隐私、归属、撤权后的收据测试通过 |
| 数据校验、不静默修复记录 | 必填/空值/列数测试通过；**B1：未闭合 CSV 引号被接受，仍不完全满足要求** |
| 可运行、隔离测试、构建、团队验收 | 43 tests + lint/build；本机 Chrome 冒烟通过；团队第二人验收待完成 |

本次未新增回归测试；43 项为原有测试，不能据此声称覆盖了 B1。`git ls-files backend/var backend/.venv frontend/node_modules frontend/dist .env` 没有输出，检查的运行时目录/文件未被 Git 跟踪。

## B1 — 未闭合 CSV 引号会合并记录（P2，未修复）

位置：`backend/app/transform.py:75`，`read_source()` 创建 `csv.reader` 的位置。默认解析未启用严格引号检查。

以下纯合成输入中，第一条消息的引号没有闭合：

```csv
ticket_id,message
T1,"Unclosed message
T2,Another message
```

期望：源数据无效，preview 返回 `422 DATASET_INVALID`，接收器调用为 0。

实际：以独立临时 Store、TestClient 和 mock 的合成源字节请求 preview，得到 `200`、`status=ready`，仅有一个消息 `Unclosed message\nT2,Another message\n`；调用为 0（探针没有执行 Send）。这说明第二条记录被并入第一条消息，预览可能继续进入可发送状态。

低层复现命令（从 backend 目录运行，不改文件）：

```bash
.venv/bin/python -c 'from pathlib import Path
from unittest.mock import patch
from app.transform import read_source
malformed = b"ticket_id,message\nT1,\"Unclosed message\nT2,Another message\n"
with patch.object(Path, "read_bytes", return_value=malformed):
    source = read_source(Path("synthetic-malformed.csv"))
    print({"accepted": True, "rows": len(source.rows), "message": source.rows[0]["message"]})'
```

建议由后端负责人领取有边界的修复：拒绝这类引号损坏，将 CSV 解析异常映射为不泄露源内容的 `DATASET_INVALID`，增加 isolated preview 测试验证 `422` 和零调用，同时保留合法的引号、逗号和多行字段。此项不需要扩展 API contract。该建议尚未实施。

## 已实现的 UX 改动

| 原显示/问题 | 现在的行为 |
| --- | --- |
| Dataset、内部 message/列名 | Customer feedback source；解释原记录留在 DataGate；列名显示为业务用语 |
| Purpose、destination 机器标识 | 任务问句与可读用途/接收器名称；收据不再显示 `feedback_summary → demo_receiver` |
| Request ID、版本与长 hash 占据主要位置 | 主视图展示业务结果；参考 ID、规则版本和 fingerprint 放在默认折叠的 Technical verification details 中 |
| Owner passport 不易理解 | Company sharing rules，并说明规则由数据所有者设置 |
| Demo 身份页暴露 session token 术语 | 用 sample analyst 描述体验，同时保留模拟认证提示 |
| 任务/接收器更改后仍显示旧预览和批准 | 更改来源、任务或接收器会清除旧预览/批准；请求处理中禁用相关选择 |
| 隐藏后的 9 条消息与接收器 10 条条目看似冲突 | 接收器条目数明确包括 hidden-message placeholders |
| 失败后预览声称未发送 | 使用“调用过但未确认送达，不会自动重试”，与收据含义一致 |
| 阻止前未扫描却显示 Nothing detected | 明确显示 Not scanned — blocked before preview |

保留了现有三栏/响应式结构、颜色、字体、redaction bars 和结果印章。仅为新增折叠信息补充了现有风格的样式，没有提出或实施整体视觉改版；因此本轮没有需要先审批的视觉 redesign prototype。

改动文件：

- `frontend/src/App.tsx`：来源名称传递、表单更改清除旧审核、失败结果语义。
- `frontend/src/labels.ts`：人类可读的字段/接收器/脱敏计数标签。
- `frontend/src/components/AccountGate.tsx`：demo 身份文案。
- `frontend/src/components/RequestForm.tsx`：反馈来源说明、公司规则、任务/接收器帮助。
- `frontend/src/components/ManifestReview.tsx`：列名、检测范围、placeholder 与失败提示。
- `frontend/src/components/ApprovalPanel.tsx`：审核信息层级与折叠验证信息。
- `frontend/src/components/OutcomePanel.tsx`：易读收据与折叠技术信息。
- `frontend/src/index.css`：帮助文本与折叠详情样式，复用原样式变量。
- `README.md`、`TEAM_WORKFLOW.md`、本报告：状态、演示步骤、审查交付。

没有修改 API、shared wire types、后端、数据库 schema、依赖声明/锁文件或启动命令。

## 实际验证与限制

最终检查：

| 目录 | 精确命令 | 结果 |
| --- | --- | --- |
| backend | `.venv/bin/python -m pytest -q` | 43 passed in 0.74s |
| frontend | `npm run lint` | exit 0 |
| frontend | `npm run build` | exit 0；Vite 6.4.4 构建成功 |
| repository root | `git diff --check` | exit 0，无空白错误 |

环境准备时最初没有 backend/.venv，系统 Python 缺少 pytest；执行 `python3 -m venv .venv`，随后 `.venv/bin/pip install -r requirements.txt` 成功。受限网络中的首次安装失败后，在获准联网的命令中完成安装。没有修改安装清单。

浏览器使用已经运行的 `127.0.0.1:5173` / `8000` 服务和一个新的独立 Chrome 标签页，仅操作合成 demo 数据。未重启或停止已有服务，未撤销或修改共享 demo 权限/规则。之前尝试启动隔离后端受本机端口权限阻止，不能把该尝试记为启动成功。

浏览器验证：MapleCo 来源与规则、preview、隐藏一条消息、审核版本/指纹可展开、批准前 Send 不可用、成功发送与本地回执、两个指纹一致、表单更改清除旧批准、training 被阻止且零调用、390px 布局及展开后的技术详情。浏览器没有重演撤权、过期 source/policy 或 receiver failure；这些路径由上述后端现有测试验证。未做 Safari/Firefox、真实用户可用性研究、外部模型调用或另一台电脑启动验收。

启动沿用 README：后端 `cd backend` 后激活 `.venv`，运行 `uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000`；另一终端 `cd frontend` 后运行 `npm run dev`，打开 `http://127.0.0.1:5173`。

下一步：后端负责人修复 B1 并补测试；第二位队员按 README 复现并记录接受的 commit。本次 UX 更改仍待用户审阅。现有检测范围仅 email 与支持的电话号码，用户批准不等于客户同意，fingerprint/收据不证明完整隐私保障。
