# 录制任务清单（第二批，20 条）

配合 `docs/recording.md`。已录的 3 条（case1/2/3）不在此列。每条任务一个 pi 会话，prompt 原样粘贴；带「第二个 prompt」的等 agent 答完再发（run 间的思考间隔是负载的一部分）。**任务不需要做对**，要的是轨迹形状。

## 启动方式（昨天用的参数）

```bash
# 推荐：开独立 worktree，不碰你的工作树；extension / 模型 / thinking 固定
bash /Users/mant1ssa/Projects/ClawEval/scripts/record.sh ~/Projects/minimind t01

# 等价的手动命令（昨天你是这样直接在仓库里跑的）
cd ~/Projects/minimind
pi -e /Users/mant1ssa/Projects/ClawEval/extension/src/index.ts --model zai/glm-5.2:off
#   trace 落到 /Users/mant1ssa/Projects/ClawEval/traces/（extension 按自身路径推导）
#   可选：--trace-dir <dir> 改目录；--name <名字> 给会话起名
```

前提：`~/.pi/agent/models.json` 里 glm-5.2 的 contextWindow 已覆盖为 65536（`pi --list-models | grep glm-5.2` 显示 `65.5K`）。结束会话用 Ctrl-D 或 `/quit`。

任务 id 即 `record.sh` 的第二个参数。四个仓库：`minimind`（Python，训练代码）、`Learn-OpenClaw`（Python，小 agent 框架，能跑 pytest）、`reactive-resume`（TS monorepo，**没装依赖：不 install、不 build、不跑测试**）、`ClawEval`（本项目 Python 侧，`uv sync` 后能跑 pytest）。

形状配比（对照 recording.md 的表）：读代码 5 · 小修 bug 5 · 新增功能 4 · 重构 3 · 跑命令/排错 3。

---

## 第一批（t01–t05）：读代码 ×3、跑/排错 ×2

### t01 · minimind · 读代码 · MoE 路由

```bash
bash scripts/record.sh ~/Projects/minimind t01
```

> 我想搞清楚这个仓库的 MoE 是怎么实现的。请读 model/model_minimind.py 里的 MOEFeedForward、MiniMindBlock 和 MiniMindConfig，回答：(1) 每个 token 怎么选专家，top-k 和 gating 的公式在哪几行；(2) 负载均衡的辅助损失怎么算、在哪里加进总 loss（去 trainer/ 目录找）；(3) 推理时和训练时的专家计算路径有没有区别。给文件名和行号，不要改代码。

第二个 prompt：

> 如果我想把 num_experts_per_tok 从 2 改成 1，除了 config 之外还有哪些地方隐含地假设了 k=2？只列位置，不要改。

预期：8–14 轮，read/grep 为主，输出中等。

### t02 · minimind · 读代码 · 数据集流水线

```bash
bash scripts/record.sh ~/Projects/minimind t02
```

> 请读 dataset/lm_dataset.py 和 dataset/dataset.md，解释预训练、SFT、DPO 三种数据集类各自怎么把原始样本变成 input_ids 和 loss mask：(1) SFT 是怎么只对 assistant 部分算 loss 的，mask 在哪几行生成；(2) 超过 max_length 的样本是截断还是丢弃；(3) DPO 的 chosen/rejected 是怎么配对成一个 batch 的。给行号。不要改代码。

第二个 prompt：

> trainer/train_full_sft.py 里 DataLoader 的 collate 是用默认的还是自定义的？如果我要加 packing（多条短样本拼一条），最少动哪两个文件？

预期：6–12 轮。

### t03 · Learn-OpenClaw · 读代码 · Node / Flow 执行模型

```bash
bash scripts/record.sh ~/Projects/Learn-OpenClaw t03
```

> 请读 core/node.py 和 examples/workflow/main.py，解释这个小框架的执行模型：(1) `>>` 和 `-` 两个运算符分别构造了什么，Flow.run 是怎么沿着 action 字符串选下一节点的；(2) max_retries 和 wait 在 _exec 里的重试逻辑，异常最终会怎样冒出来；(3) examples/workflow 里的节点链是怎么拼起来的，画一个文字流程图。给行号，不要改代码。

第二个 prompt：

> 只给我代码不要写文件：一个三节点的分支流程示例，第一个节点根据输入长度返回 "short" 或 "long" 两种 action，分别走到不同节点。

预期：6–10 轮，输出较长（含代码）。

### t04 · Learn-OpenClaw · 跑/排错 · ToolExecutor demo → pytest

```bash
bash scripts/record.sh ~/Projects/Learn-OpenClaw t04
```

> 这个 worktree 里没有 .venv，先 uv sync。然后把 tools/executor.py 里的 demo() 跑起来看看输出。跑通之后把它改写成 tests/test_executor.py 的 pytest 用例：覆盖 parse_tool_calls 对正常调用、参数不是合法 JSON、缺少 function 字段三种情况，以及 execute 遇到未注册工具名时的返回。用 uv run pytest 跑到全部通过。

第二个 prompt：

> 再加一个用例：execute_all 在其中一个工具抛异常时，其余工具的结果还能正常返回吗？如果现在不能，修一下。

第三个 prompt：

> git diff 给我看一遍，然后 commit，message 用英文。

预期：15–25 轮，bash 密集（uv sync 几十秒、pytest 数秒），三个 run。

### t05 · Learn-OpenClaw · 跑/排错 · MCP client/server 联调

```bash
bash scripts/record.sh ~/Projects/Learn-OpenClaw t05
```

> 先 uv sync。tools/mcp/ 下有 server.py 和 client.py，我想确认它们能联调：把 server 在后台起起来，用 client 调一次工具，把实际输出贴给我。中间遇到端口、导入路径、缺依赖之类的问题自己修。最后把「怎么启动、怎么调用、怎么停」写成 tools/mcp/README.md。

第二个 prompt：

> server 进程还在跑吗？确认清理干净，然后告诉我 fastmcp 这个版本的 tool 注册方式和 example.py 里写的一不一样。

预期：12–20 轮，bash 多且有长耗时（后台进程、等待），可能有报错→修复循环。

### 复核 · 第一批

- 形状：读 ×3（t01/t02/t03，覆盖两个仓库）、跑/排错 ×2（t04/t05），符合配比；t03 的第二个 prompt 让输出变长，补了「读代码任务输出短」之外的一种形状。
- 路径核对：`model/model_minimind.py`（MOEFeedForward L147、MiniMindBlock L177、MiniMindConfig L10）、`dataset/lm_dataset.py`、`dataset/dataset.md`、`core/node.py`（`__rshift__` L30、`__sub__` L35、Flow L42）、`examples/workflow/main.py`、`tools/executor.py`（demo L122、parse_tool_calls L64、execute_all L102）、`tools/mcp/{server,client,example}.py` 均存在（脚本核对见文末）。
- 依赖风险：t04/t05 需要 `uv sync` 拉 ddgs/fastmcp/openai，几十秒，正是要的工具耗时；不需要 API key（executor demo 与 MCP 都不调 LLM——若 client 需要 key 会报错，那也是真实的排错轮次）。minimind 的两条明确写了「不要改代码」，避免 agent 去装 torch。
- 安全：t04 的 commit 落在 worktree 分离的 HEAD 上，不影响主分支；t05 明确要求清理后台进程。
- 调整：t02 原本想让 agent 跑 dataset 单测，minimind 本地没有 torch 环境，改成纯阅读；t04 原第三 prompt 只写「commit」，补了「英文 message」使其与 case2 一致。

---

## 第二批（t06–t10）：小修 bug ×5

### t06 · minimind · 修 bug · get_lr 越界

```bash
bash scripts/record.sh ~/Projects/minimind t06
```

> trainer/trainer_utils.py 里的 get_lr(current_step, total_steps, lr) 在 current_step > total_steps 或 total_steps == 0 时会返回什么？我怀疑有问题。请：(1) 读代码给出结论；(2) 写一个纯 Python 的最小复现（不要 import torch，把函数复制到测试里或者用 importlib 单独加载），放在 tests/test_get_lr.py；(3) 如果确实不合理就修 get_lr，让测试通过。这台机器没有 torch，不要装。

第二个 prompt：

> 修完后 train_pretrain.py 和 train_full_sft.py 调用 get_lr 的地方需要跟着改吗？grep 一下告诉我。

预期：8–14 轮。

### t07 · minimind · 修 bug · rope_scaling 缺键

```bash
bash scripts/record.sh ~/Projects/minimind t07
```

> model/model_minimind.py 的 precompute_freqs_cis 接受一个 rope_scaling 字典。请检查：传入的字典缺少某个键（比如只有 factor 没有 original_max_position_embeddings）时是否会 KeyError；MiniMindConfig 里 rope_scaling 的默认值和校验在哪。写一个不依赖 torch 的复现说明（可以只描述，不必跑），然后给这个函数加防御性处理并保持原有行为不变。不要装依赖，不要运行训练。

第二个 prompt：

> 把你改动的部分用 git diff 给我，再说说 rope_base 的默认值 1e6 是从哪来的，README 里有提吗？

预期：6–12 轮，edit 少而精。

### t08 · Learn-OpenClaw · 修 bug · grep 工具读大文件

```bash
bash scripts/record.sh ~/Projects/Learn-OpenClaw t08
```

> 先 uv sync。tools/builtins/grep.py 和 read.py 对二进制文件和超大文件（比如几百 MB 的日志）是怎么处理的？我怀疑会整个读进内存或者把二进制内容原样返回给模型。请：(1) 读代码确认；(2) 在 tests/ 下用 tmp_path 造一个 20MB 的文本文件和一个二进制文件写测试复现；(3) 加上大小上限和二进制检测，返回截断提示而不是崩溃；(4) uv run pytest 全过。

第二个 prompt：

> ls.py 和 find.py 有没有类似的问题（目录里几万个文件）？有的话一起修，没有就说明为什么不会。

预期：12–20 轮，bash + edit 循环。

### t09 · reactive-resume · 修 bug · 日期解析边界

```bash
bash scripts/record.sh ~/Projects/reactive-resume t09
```

> packages/import/src/date.ts 和 date.test.ts：请读一遍，找出测试没覆盖的边界输入，比如 "2024-13"（非法月份）、"Present"/"present"/"PRESENT"、"2024/03"、空字符串、只有年份。对每一种说明现在的行为，判断哪些是 bug。然后补测试用例到 date.test.ts，并修 date.ts。注意：这台机器没装 node_modules，不要 pnpm install，不要跑测试或 build；改完把 diff 和你预期的测试结果告诉我。

第二个 prompt：

> level.ts 也有类似的模糊输入转换（技能等级），用同样的方式过一遍。

预期：8–14 轮，read → edit，输出中等。

### t10 · ClawEval · 修 bug · percentile 边界

```bash
bash scripts/record.sh ~/Projects/ClawEval t10
```

> 先 uv sync --group dev。analysis/stats.py 的 percentile 用的是 nearest-rank：请检查 n=1、p=0、p=100、以及 values 里混有 None 和 NaN 时 pct() 的行为，写测试到 analysis/tests/test_stats.py 覆盖这些边界，不合理的地方修掉（NaN 应该被当成缺失值排除，并在返回里能看出来）。uv run pytest 和 uv run ruff check 都要过。

第二个 prompt：

> fmt_pct 对 digits=3 且值为 0.0 的显示是 "0.000" 吗？顺手也加个测试。然后 git diff 给我看，不用 commit。

预期：8–14 轮，pytest 快，轮次多而短。

### 复核 · 第二批

- 形状：5 条都是「读 → 定位 → 改 → 验证」，但验证方式不同：t06/t08/t10 能跑测试（bash 循环），t07/t09 不能跑（纯 read/edit，输出偏长）——两种子形状都有。
- 路径核对：`trainer/trainer_utils.py`（get_lr L40）、`trainer/train_pretrain.py`、`trainer/train_full_sft.py`、`model/model_minimind.py`（precompute_freqs_cis L62，参数 rope_scaling）、`tools/builtins/{grep,read,ls,find}.py`、`packages/import/src/{date,date.test,level}.ts`、`analysis/stats.py`（percentile/pct/fmt_pct）均存在。
- 真实性：t06 的怀疑点是真的可疑（cosine 调度越界通常不设防）；t07/t08/t09 都是常见的防御性缺口；t10 的 NaN 问题在现有代码里确实存在（`sorted()` 遇 NaN 排序不稳定）。agent 会真的找到东西，不会空转。
- 依赖：t06/t07 明确禁止装 torch；t09 明确禁止 install/build；t10 的 `uv sync` 在本机秒级（缓存）。
- 调整：t08 原本只写 grep.py，加了 read.py 和第二 prompt 的 ls/find，让它多读几个文件、上下文长一些；t10 原本要求 commit，改为只看 diff，避免在本项目 worktree 里产生分离的提交。

---

## 第三批（t11–t15）：新增功能 ×4、重构 ×1

### t11 · Learn-OpenClaw · 新增功能 · Memory 持久化

```bash
bash scripts/record.sh ~/Projects/Learn-OpenClaw t11
```

> 先 uv sync。给 core/memory.py 的 Memory 加持久化：save(path) 把消息历史和必要的状态写成 JSON，load(path) 类方法读回来得到等价的 Memory；要处理文件不存在和 JSON 损坏两种错误。写 tests/test_memory_persist.py 覆盖往返、损坏文件、空历史三种情况，uv run pytest 全过。已有的 tests/test_memory.py 不要改坏。

第二个 prompt：

> 再加一个 max_messages 上限：超过时从最老的非 system 消息开始丢，和 compress 的逻辑要兼容。补测试。

第三个 prompt：

> 把 examples/chatbot_with_memory 改成退出时自动 save、启动时自动 load，路径用环境变量 MEMORY_PATH，默认 ~/.poipoi/memory.json。不用跑 chatbot（需要 API key），改完说明怎么验证。

预期：20–30 轮，三个 run，edit/write/bash 混合，上下文会长到 25k+。

### t12 · reactive-resume · 新增功能 · GitHub 用户名字段（长会话）

```bash
bash scripts/record.sh ~/Projects/reactive-resume t12
```

> 我要给简历的 basics 加一个「GitHub 用户名」字段（githubUsername，字符串，可选，展示时渲染成 github.com/<用户名> 的链接）。请从 packages/schema/src/resume/data.ts 的 schema 开始，贯通到：apps/web 里 basics 那一节的编辑表单、packages/pdf 的渲染（至少让默认模板显示出来）、packages/import 的三个 JSON 导入器的字段映射、packages/docx 导出。先用 grep 把所有需要改的位置列成清单给我确认，再动手。这台机器没装依赖：不要 pnpm install，不要 build，不要跑测试。改完列出每个文件改了什么。

它列完清单后回复：

> 可以，全部改。

改完再发：

> 检查 i18n：这个字段的 label 需要在 lingui 的翻译目录里加条目吗？需要的话把 zh-CN 和 en 加上。另外 packages/schema/src/resume/sample.ts 的示例数据也补上这个字段。

预期：30–45 轮，grep/read 结果巨大，**应触发 compaction**（没触发就继续追加：「ATS 抽取那边也要认这个字段吗？」）。

### t13 · minimind · 新增功能 · OpenAI 兼容服务加 /v1/models 与 usage

```bash
bash scripts/record.sh ~/Projects/minimind t13
```

> scripts/serve_openai_api.py 是一个 OpenAI 兼容的推理服务。请：(1) 读一遍现有的路由和请求/响应结构；(2) 加一个 GET /v1/models 端点，返回当前加载的模型 id；(3) 让 /v1/chat/completions 的响应（流式和非流式都要）带上 usage 字段：prompt_tokens、completion_tokens、total_tokens，用 tokenizer 数出来。不要运行服务、不要装依赖（这台机器没有 torch），改完把 diff 给我，并说明流式模式下 usage 是在哪个 chunk 里返回的。

第二个 prompt：

> scripts/chat_api.py 是这个服务的客户端吗？如果是，让它打印 usage；不是的话告诉我它是干什么的。

预期：10–16 轮。

### t14 · ClawEval · 新增功能 · profile 加 --json 与每 trace 工具表

```bash
bash scripts/record.sh ~/Projects/ClawEval t14
```

> 先 uv sync --group dev。analysis/profile.py 现在输出 profile.md 和 summary.json。请加两个东西：(1) 命令行选项 --json，把 summary 直接打印到 stdout（和写文件二选一）；(2) profile.md 的「每条 trace」表后面加一张「每条 trace 的工具混合」表：每行一个 trace，列是各工具的调用次数和错误数。数据全部来自已有的 ToolRow，不要新算指标。补测试到 analysis/tests/test_profile.py，uv run pytest、ruff check、mypy 都要过。

第二个 prompt：

> 用 traces/ 目录里的真实 trace 跑一遍 python -m analysis.profile traces --out /tmp/p，把新表贴给我看看格式对不对。

预期：12–20 轮，mypy 报错→修复的循环很典型。

### t15 · Learn-OpenClaw · 重构 · builtins 公共逻辑抽取

```bash
bash scripts/record.sh ~/Projects/Learn-OpenClaw t15
```

> 先 uv sync。tools/builtins/ 下 read.py、write.py、edit.py、ls.py、find.py、grep.py 里有重复的路径解析、越界/不存在检查和错误信息拼装。请先逐个文件列出重复的片段（引用行号），再抽到 tools/builtins/_common.py，各工具改为调用它。要求行为逐字节不变：改之前先用现有测试（没有就先为这几个工具补最小的行为快照测试）锁住输出，改完 uv run pytest 全过。tool_def.py 的工具描述不要动。

第二个 prompt：

> 抽完之后每个文件少了多少行？用 git diff --stat 给我，再说说有没有哪个工具的行为你不确定是不是变了。

预期：15–25 轮，read 多、edit 多、pytest 循环。

### 复核 · 第三批

- 形状：功能 ×4（t11/t12/t13/t14）、重构 ×1（t15）；t11 三个 run 制造两次人类思考间隔；t12 是本批的 compaction 触发器（与 case3 同类但字段不同，避免完全重复的轨迹）。
- 路径核对：`core/memory.py`、`tests/test_memory.py`（case2 时 agent 已提交）、`examples/chatbot_with_memory/`、`packages/schema/src/resume/{data,sample}.ts`、`packages/import/src/*.tsx`、`packages/docx/src/`、`packages/pdf/src/document.tsx`、`scripts/{serve_openai_api,chat_api}.py`、`analysis/profile.py`、`analysis/tests/test_profile.py`、`tools/builtins/{read,write,edit,ls,find,grep,tool_def}.py` 均存在。
- 真实性：t13 的 usage 字段是 OpenAI 兼容服务的常见缺口；t15 的重复确实存在（六个工具各自做路径处理）。t14 让 agent 在本项目上干活，产生的轨迹里会有本项目自己的 mypy strict 报错循环，是很典型的形状。
- 依赖：t13 禁止运行；t12 禁止 install/build；t14 在本机 `uv sync` 秒级。
- 调整：t11 原本第三 prompt 要求跑 chatbot，需要 API key，改为「改完说明怎么验证」；t14 加了第二 prompt 用真实 trace 跑一遍，让轨迹里出现大段真实输出（profile.md 内容进 tool result）。

---

## 第四批（t16–t20）：读代码 ×2、重构 ×2、跑/排错 ×1

### t16 · reactive-resume · 读代码 · PDF 渲染管线（长上下文）

```bash
bash scripts/record.sh ~/Projects/reactive-resume t16
```

> 请梳理简历从 schema 到 PDF 的渲染管线：packages/pdf/src 的 document.tsx、context.tsx、semantic/ 目录各负责什么；模板在 packages/schema/src/templates.ts 里怎么注册、在 pdf 包里怎么被选中；section-title / section-icon 是怎么映射的。最后回答：新增一个模板要动哪些文件。给路径和行号，不要改代码，不要 install。

第二个 prompt：

> ATS 抽取（packages/pdf/src/ats-extraction*.tsx 和 packages/resume/src/ats*）和普通渲染共享哪些代码？legacy-parity.ts 是在保什么的兼容？

第三个 prompt：

> 如果我想给所有模板加「页眉显示页码」，是改 document.tsx 一处，还是每个模板都要动？

预期：15–25 轮，read 结果巨大，三个 run，可能触发 compaction。

### t17 · reactive-resume · 读代码 · 服务端三套接口

```bash
bash scripts/record.sh ~/Projects/reactive-resume t17
```

> apps/server/src 下有 rpc、openapi、mcp 三个目录，看起来是三套对外接口。请搞清楚：(1) 它们是怎么共用同一套简历 CRUD 业务逻辑的，调用链从 HTTP 入口到 packages/db 一路给出文件和行号；(2) 认证在哪一层做，三套接口是否一致；(3) packages/api 和 apps/server 的分工。不要改代码，不要 install。

第二个 prompt：

> 如果要给 mcp 接口加一个「导出 PDF」的工具，复用 openapi 那条链的话最少要写哪些代码？只列清单。

预期：12–20 轮。

### t18 · minimind · 重构 · 训练循环去重

```bash
bash scripts/record.sh ~/Projects/minimind t18
```

> trainer/train_full_sft.py 和 trainer/train_lora.py 的训练循环（数据加载、混合精度、梯度累积、日志、保存 checkpoint）重复很多。请：(1) 先把两个文件逐段对照，列出完全相同、仅参数不同、逻辑确实不同的三类片段；(2) 把相同和仅参数不同的部分抽成 trainer/trainer_utils.py 里的一个 train_epoch 通用函数，两个脚本改为调用它，逻辑不同的部分通过回调或参数传入；(3) 不要运行（这台机器没有 torch），改完用 git diff --stat 和文字说明保证行为不变。

第二个 prompt：

> train_dpo.py 能不能也用这个通用函数？看一遍告诉我卡在哪。

预期：15–25 轮，read 长、edit 大块。

### t19 · reactive-resume · 重构 · 三个 JSON 导入器公共 helper

```bash
bash scripts/record.sh ~/Projects/reactive-resume t19
```

> packages/import/src 里 json-resume.tsx、reactive-resume-json.tsx、reactive-resume-v4-json.tsx 三个导入器各自做了日期、技能等级、URL 的规范化，逻辑重复。请先列出重复的片段（文件+行号），再抽到 packages/import/src/normalize.ts，三个导入器改为调用它。现有的 *.test.ts 不要改，改完逐个说明为什么每个测试仍然会过。不要 install、不要跑测试、不要 build。

第二个 prompt：

> html.ts 那个 HTML 导入器也有日期处理吗？有的话一起接进来。

预期：12–20 轮。

### t20 · ClawEval · 跑/排错 · SSE 跨块切分的测试

```bash
bash scripts/record.sh ~/Projects/ClawEval t20
```

> 先 uv sync --group dev，跑一遍 uv run pytest 看现状。replay/client.py 用 httpx 的 aiter_lines 解析 SSE。我担心一种情况：一条 `data: {...}` 被 HTTP 分块切成两半到达时能不能正确拼回。请在 replay/tests/test_client.py 里用 httpx.MockTransport 构造一个把响应体按奇怪边界（比如每 7 个字节）切开发送的流，验证 usage 和 ttft 仍然正确。如果现在的实现有问题就修。pytest、ruff check、mypy 都要过。

第二个 prompt：

> 再加一个用例：服务端在中途断开（流没有 [DONE] 就结束了），RequestResult 应该是什么样？现在的行为合理吗？

第三个 prompt：

> git diff 给我，不要 commit。

预期：12–20 轮，pytest 循环密集，轮次短。

### 复核 · 第四批

- 形状：读 ×2（t16/t17）、重构 ×2（t18/t19）、跑/排错 ×1（t20）。加上前三批，总计读 5 · 修 5 · 功能 4 · 重构 3 · 跑/排错 3 = 20；仓库分布 minimind 6 · Learn-OpenClaw 6 · reactive-resume 5 · ClawEval 3。
- compaction 候选：t12、t16、t11（三个 run 叠加）、t18；加上已录的 case3，≥ 3 条能撑到 49k。
- 路径核对：`packages/pdf/src/{document,context}.tsx`、`packages/pdf/src/semantic/legacy-parity.ts`、`packages/pdf/src/ats-extraction.integration.test.tsx`、`packages/resume/src/ats*`、`packages/schema/src/templates.ts`、`apps/server/src/{rpc,openapi,mcp}`、`packages/api`、`packages/db`、`trainer/{train_full_sft,train_lora,train_dpo}.py`、`packages/import/src/{json-resume,reactive-resume-json,reactive-resume-v4-json}.tsx`、`packages/import/src/html.ts`、`replay/client.py`、`replay/tests/test_client.py` 均存在。
- 真实性：t20 描述的跨块切分问题在 httpx `aiter_lines` 下其实是安全的（它按行缓冲），agent 会得出「现有实现没问题」——这是有价值的负面结果形状；t16 的 legacy-parity.ts 是真实存在的兼容层，问题不是编的。
- 依赖：t16/t17/t19 禁止 install；t18 禁止运行；t20 在本机 `uv sync` 秒级。
- 调整：t17 原本要求画时序图，输出会非常长且不稳定，改为「文件和行号」；t19 原本让 agent 跑 vitest，本机没 node_modules，改为「逐个说明为什么测试仍然会过」。

---

## 第五批（t21–t23）：长会话补充，目标触发 compaction

前 20 条只有最早的 case3 触发了 compaction（t12 34.8k、t16 44.5k、t19 43.5k，都没过 49k）。这三条用 4–5 个 prompt 把单会话推过阈值。

### t21 · reactive-resume · 新增功能（长）· 「推荐信」区块贯通

```bash
bash scripts/record.sh ~/Projects/reactive-resume t21
```

> 我要给简历加一个新的自定义区块「推荐信」（references）：每条包含 name、title、company、email、phone、relationship、可选的 summary。请从 packages/schema/src/resume/data.ts 开始定义 schema，贯通到 apps/web 的编辑表单（新增一个 section）、packages/pdf 的渲染（至少默认模板）、packages/import 三个 JSON 导入器、packages/docx 导出。先 grep 列清单给我确认再动手。不要 pnpm install，不要 build，不要跑测试。

> 可以，全部改。

> 现在处理 i18n：这个区块所有 label 的 lingui 条目，zh-CN 和 en 都要加；sample.ts 的示例数据补两条推荐信。

> ATS 抽取那边（packages/pdf/src/ats-extraction*、packages/resume/src/ats*）需要认这个区块吗？需要的话加上，并说明它对 ATS 评分有什么影响。

> 把所有改动按包分组，用 git diff --stat 给我，然后逐个包写一句「为什么现有测试仍然会过」。

预期：50–80 轮，prompt 应过 49k 触发 compaction。

### t22 · Learn-OpenClaw · 新增功能 + 重构（长）· 工具执行超时与审计日志

```bash
bash scripts/record.sh ~/Projects/Learn-OpenClaw t22
```

> 先 uv sync。给 tools/executor.py 的 ToolExecutor 加两个能力：(1) 每个工具调用的超时（默认 30 s，可在 ToolCall 上覆盖），超时返回一个 ToolResult 错误而不是挂死；(2) 审计日志：每次 execute 把工具名、参数摘要、耗时、成功与否写成 JSON 行到一个可配置路径。两者都要有 pytest 覆盖，uv run pytest 全过。

> 把审计日志接到 examples/chatbot_with_tools 和 examples/agent_with_goal 两个示例里（路径用环境变量 TOOL_AUDIT_LOG），不用真的跑示例（需要 API key），改完说明怎么验证。

> tools/builtins/bash.py 的实现有没有子进程超时？如果没有，用你刚加的超时机制统一它，并补一个「命令 sleep 5 但超时 1 s」的测试。

> 现在整体过一遍 tools/ 目录，把重复的错误信息拼装和路径处理抽成公共函数（tools/builtins/_common.py），保持 pytest 全过；用 git diff --stat 总结。

> 最后写 tools/README.md 的「超时与审计」一节，然后 git diff 给我看，不要 commit。

预期：60–90 轮，bash/edit 密集。

### t23 · minimind · 重构 + 读代码（长）· 训练脚本统一入口

```bash
bash scripts/record.sh ~/Projects/minimind t23
```

> trainer/ 下 train_pretrain.py、train_full_sft.py、train_lora.py、train_dpo.py、train_distillation.py 各自解析参数、初始化模型和分布式、跑训练循环。请先逐个文件读一遍，列出五个脚本在「参数解析、模型初始化、数据加载、训练循环、保存」五个环节各自的差异表（文件+行号）。不要改代码，这台机器没有 torch，不要装。

> 基于差异表，设计一个 trainer/common.py：把参数解析的公共部分、init_distributed、模型初始化、checkpoint 保存抽出来；各脚本保留自己的 loss 计算。先只写 common.py 和改 train_pretrain.py、train_full_sft.py 两个，不运行。

> 再把 train_lora.py 和 train_dpo.py 接上 common.py。LoRA 的参数冻结逻辑和 DPO 的 ref model 加载要保留在各自脚本里。

> train_distillation.py 和 train_grpo.py 能不能接？看一遍，能接的接，不能接的说明原因。

> git diff --stat，再逐个脚本写一句行为是否不变的判断依据。

预期：50–80 轮，read 结果大（五个训练脚本），后半段 edit 密集。

### 复核 · 第五批

- 目的单一：把 prompt 推过 49k。三条都是 4–5 个 prompt、跨多文件、要求列清单再动手（清单本身就是大块 tool 结果）。
- 路径核对：`packages/schema/src/resume/{data,sample}.ts`、`packages/pdf/src/ats-extraction*`、`packages/resume/src/ats*`、`tools/executor.py`、`tools/builtins/bash.py`、`examples/{chatbot_with_tools,agent_with_goal}/`、`trainer/train_{pretrain,full_sft,lora,dpo,distillation,grpo}.py` 均存在（`check-task-paths.sh` 已加）。
- 依赖：t21 禁止 install/build；t23 禁止装 torch；t22 的 `uv sync` 秒级。
- 风险：GLM 可能在第 2–3 个 prompt 后就把上下文用到 40k+，compaction 会在中途触发——这正是要的。若某条仍没触发，不追加了：三条里两条触发即可。

## 录制顺序建议

不按编号。先各仓库各录一条（t03、t06、t09、t10）确认四个仓库的 worktree 都正常，再按形状交替录，避免连续录同类任务时你自己的 prompt 节奏趋同。每录 5 条跑一次 `just profile` 看「每条 trace」表：`reqs (done)` 不为 0、无警告即可。

## 路径核对脚本

```bash
bash scripts/check-task-paths.sh      # 逐条检查上面引用的文件是否存在
```
