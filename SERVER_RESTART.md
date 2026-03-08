# AI素养评测平台 — 服务器冷启动与功能验证手册

> **适用场景**：将 Dell Pro Max（NVIDIA DGX Spark GB10）服务器搬到新的客户网络环境后，从零冷启动并恢复平台全部功能。
>
> **适用人员**：现场运维工作人员（无需开发背景）。
>
> **预计耗时**：首次操作约 20-30 分钟。

---

## 目录

1. [你需要准备什么](#1-你需要准备什么)
2. [认识这台服务器](#2-认识这台服务器)
3. [第一步：物理连接与开机](#3-第一步物理连接与开机)
4. [第二步：连接网络并获取 IP 地址](#4-第二步连接网络并获取-ip-地址)
5. [第三步：启动大模型服务 (vLLM)](#5-第三步启动大模型服务-vllm)
6. [第四步：启动平台所有服务 (Docker)](#6-第四步启动平台所有服务-docker)
7. [第五步：逐项功能验证](#7-第五步逐项功能验证)
8. [关机与停止服务](#8-关机与停止服务)
9. [常见问题排查](#9-常见问题排查)
10. [附录：服务端口一览](#10-附录服务端口一览)

---

## 1. 你需要准备什么

| 物品 | 说明 |
|------|------|
| Dell Pro Max 服务器 | 就是要搬运的这台黑色机器 |
| 电源线 | 服务器自带，确保客户现场有匹配的电源插座 |
| 网线 | 一根以太网线（Cat5e 或以上），连接服务器到客户交换机/路由器 |
| 显示器 + HDMI/DP 线 | 用于首次配置（配置完成后可拔掉） |
| 键盘 | USB 键盘，用于在服务器上输入命令 |
| 一台客户网络中的电脑 | 用于验证平台是否正常工作（有浏览器即可） |

---

## 2. 认识这台服务器

这台 **Dell Pro Max**（内部代号 NVIDIA DGX Spark GB10）是一台带 GPU 的小型AI服务器。它上面运行了两套东西：

```
┌─────────────────────────────────────────────────────────┐
│                   Dell Pro Max 服务器                      │
│                                                         │
│  ┌───────────────────┐  ┌────────────────────────────┐  │
│  │   vLLM 大模型服务   │  │    Docker 容器群             │  │
│  │   (AI 大脑)        │  │  ┌──────┐ ┌──────┐ ┌────┐ │  │
│  │                   │  │  │前端   │ │后端   │ │数据 │ │  │
│  │ Qwen3.5-35B 模型  │  │  │Nginx │ │FastAPI│ │ 库  │ │  │
│  │ 端口: 8100        │  │  │:80   │ │:8000 │ │群  │ │  │
│  └───────────────────┘  └────────────────────────────┘  │
│                                                         │
│  对外只暴露 80 端口 ← 用户用浏览器访问这个端口              │
└─────────────────────────────────────────────────────────┘
```

**简单理解**：
- **vLLM** = AI 大脑，负责所有智能功能（出题、评分、对话等）
- **Docker 容器群** = 平台本体，包括网站前端、后端 API、数据库等 10 个服务
- 用户只需要用浏览器访问 `http://服务器IP` 即可使用平台

---

## 3. 第一步：物理连接与开机

### 3.1 连接硬件

1. 将**电源线**插入服务器背面的电源接口，另一端插入电源插座
2. 将**网线**插入服务器背面的以太网口（RJ45 口），另一端插入客户的**交换机**或**路由器**
3. 将**显示器**通过 HDMI 或 DisplayPort 线连接到服务器
4. 将 **USB 键盘**插入服务器 USB 口

### 3.2 开机

1. 按下服务器前面板的**电源按钮**
2. 等待系统启动，直到显示器上出现**登录界面**（约 1-2 分钟）
3. 登录服务器：

```
用户名: dell
密码:   （向管理员获取密码）
```

> **登录成功**后会看到命令行终端（黑色背景，显示类似 `dell@dell-dgx:~$` 的提示符）。

---

## 4. 第二步：连接网络并获取 IP 地址

### 4.1 查看服务器获得的 IP 地址

登录后，输入以下命令并按回车：

```bash
hostname -I
```

**正常结果**（示例）：

```
192.168.1.100 172.17.0.1
```

> 第一个 IP 地址（如 `192.168.1.100`）就是服务器在客户网络中的地址。
> **请把这个 IP 记下来**，后面所有步骤都要用到。

如果显示的只有 `127.0.0.1` 或者没有显示任何地址，说明网络没有连通，请检查：
- 网线是否插紧
- 交换机/路由器是否开启
- 是否需要联系客户网络管理员分配 IP

### 4.2 验证网络连通性

在服务器上测试是否能连通网关：

```bash
ping -c 3 $(ip route | grep default | awk '{print $3}')
```

**正常结果**：

```
PING 192.168.1.1 ... 64 bytes from 192.168.1.1: icmp_seq=1 ttl=64 time=0.5 ms
...
3 packets transmitted, 3 received, 0% packet loss
```

> 看到 `0% packet loss`（0%丢包）就说明网络正常。

### 4.3 确认防火墙放行 80 端口

```bash
sudo ufw status
```

如果显示 `Status: active`（防火墙已开启），需要放行 80 端口：

```bash
sudo ufw allow 80/tcp
```

如果显示 `Status: inactive`（防火墙未开启），则无需操作。

### 4.4 从客户电脑验证连通

在客户网络中的**任意一台电脑**上，打开命令提示符（Windows 按 `Win+R` 输入 `cmd`）：

```
ping 192.168.1.100
```

> 将 `192.168.1.100` 替换为你在 4.1 步记下的实际 IP。
> 能收到回复就说明客户电脑能访问到服务器。

---

## 5. 第三步：启动大模型服务 (vLLM)

> vLLM 是 AI 大脑，必须**先于平台启动**。它负责驱动平台的所有智能功能。

### 5.1 检查 vLLM 是否已经在运行

```bash
curl -s http://localhost:8100/v1/models | python3 -m json.tool
```

**如果 vLLM 已在运行**，会显示类似：

```json
{
    "data": [
        {
            "id": "Qwen/Qwen3.5-35B-A3B",
            "object": "model",
            ...
        }
    ]
}
```

> 如果看到上面的输出，**跳过 5.2，直接进入第四步**。

**如果 vLLM 未运行**，会显示：

```
curl: (7) Failed to connect to localhost port 8100
```

> 继续执行 5.2 来启动 vLLM。

### 5.2 启动 vLLM

输入以下命令（完整复制粘贴，一次性执行）：

```bash
export HF_ENDPOINT=https://hf-mirror.com

nohup ~/vllm-env/bin/python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3.5-35B-A3B-GPTQ-Int4 \
  --served-model-name Qwen/Qwen3.5-35B-A3B \
  --host 0.0.0.0 \
  --port 8100 \
  --trust-remote-code \
  > ~/vllm-server.log 2>&1 &
```

> 按回车后，屏幕会显示一个数字（进程号），类似 `[1] 12345`，这是正常的。

### 5.3 等待模型加载

模型加载需要 **1-3 分钟**，期间可以查看加载进度：

```bash
tail -f ~/vllm-server.log
```

**正在加载时**会看到类似：

```
INFO:     Loading model weights...
Loading safetensors checkpoint shards: 50% ...
```

**加载完成时**会看到：

```
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8100
```

> 看到 `Uvicorn running` 就表示加载完成。按 `Ctrl+C` 退出日志查看（不会关闭 vLLM）。

### 5.4 验证 vLLM 正常工作

```bash
curl -s http://localhost:8100/v1/models | python3 -m json.tool
```

**正常结果**：应显示包含 `"id": "Qwen/Qwen3.5-35B-A3B"` 的 JSON。

再做一次**实际对话测试**，确认模型能正确回答问题：

```bash
curl -s http://localhost:8100/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3.5-35B-A3B",
    "messages": [{"role": "user", "content": "用一句话解释什么是人工智能"}],
    "max_tokens": 100
  }' | python3 -m json.tool
```

**正常结果**：返回的 JSON 中 `choices[0].message.content` 应包含一段关于人工智能的回答。

> **验证通过标志**：模型列表能正常返回 + 对话测试能收到回答 = vLLM 启动成功。

---

## 6. 第四步：启动平台所有服务 (Docker)

### 6.1 进入项目目录

```bash
cd ~/ai-literacy-platform
```

### 6.2 检查 Docker 服务是否正常

```bash
sudo systemctl status docker --no-pager
```

**正常结果**：看到 `Active: active (running)` 字样。

如果 Docker 未运行，启动它：

```bash
sudo systemctl start docker
```

### 6.3 启动所有平台容器

```bash
docker compose up -d
```

**正常结果**（首次可能需要 1-2 分钟）：

```
[+] Running 10/10
 ✔ Container ai-literacy-redis          Started
 ✔ Container ai-literacy-postgres       Started
 ✔ Container ai-literacy-elasticsearch  Started
 ✔ Container ai-literacy-minio          Started
 ✔ Container ai-literacy-etcd           Started
 ✔ Container ai-literacy-rabbitmq       Started
 ✔ Container ai-literacy-milvus-minio   Started
 ✔ Container ai-literacy-milvus         Started
 ✔ Container ai-literacy-app            Started
 ✔ Container ai-literacy-frontend       Started
```

### 6.4 等待所有服务变为健康状态

启动后需要等待约 **1-2 分钟**让数据库等服务完成初始化。反复运行以下命令检查：

```bash
docker compose ps
```

**逐一检查以下 10 个容器**：

| 容器名称 | 作用 | 正常状态 |
|----------|------|---------|
| ai-literacy-postgres | 主数据库 | `Up ... (healthy)` |
| ai-literacy-elasticsearch | 全文搜索引擎 | `Up ... (healthy)` |
| ai-literacy-redis | 缓存 | `Up ... (healthy)` |
| ai-literacy-minio | 文件存储 | `Up ... (healthy)` |
| ai-literacy-rabbitmq | 消息队列 | `Up ... (healthy)` |
| ai-literacy-etcd | Milvus 元数据 | `Up ... (healthy)` |
| ai-literacy-milvus-minio | Milvus 存储 | `Up ... (healthy)` |
| ai-literacy-milvus | 向量数据库 | `Up ... (healthy)` |
| ai-literacy-app | 后端 API | `Up` |
| ai-literacy-frontend | 前端网站 | `Up` |

> 如果某个容器显示 `starting` 或 `unhealthy`，再等 30 秒后重新检查。
> 如果超过 5 分钟仍然 `unhealthy`，请参考 [第9章 常见问题排查](#9-常见问题排查)。

### 6.5 验证后端 API 运行正常

```bash
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
```

**正常结果**：

```json
{
    "status": "healthy",
    "service": "AI素养评测平台",
    "version": "0.1.0",
    "llm_model": "Qwen/Qwen3.5-35B-A3B"
}
```

> **关键检查**：`status` 为 `healthy`，`llm_model` 显示了模型名称。

### 6.6 验证前端网站可访问

在**服务器上**测试：

```bash
curl -s -o /dev/null -w "HTTP状态码: %{http_code}\n" http://localhost
```

**正常结果**：

```
HTTP状态码: 200
```

---

## 7. 第五步：逐项功能验证

> 以下所有操作都在**客户网络中的电脑浏览器**上进行。
> 将下文中的 `<IP>` 替换为你在第 4.1 步记下的服务器实际 IP 地址。

### 7.1 基础功能验证

#### 检查 1：平台首页加载

1. 打开浏览器，访问 `http://<IP>`
2. **预期结果**：看到 AI 素养评测平台的**登录页面**

> 如果页面无法加载（白屏或无法连接），请先检查：
> - 服务器 IP 是否正确
> - 网线是否连接
> - 是否所有 Docker 容器都在运行（回到 6.4 检查）

#### 检查 2：登录系统

1. 在登录页输入：
   - 用户名：`admin`
   - 密码：`admin123`
2. 点击"登录"
3. **预期结果**：成功进入管理后台，看到**仪表盘（Dashboard）**页面

#### 检查 3：API 健康检查

1. 在浏览器新标签页访问 `http://<IP>/api/v1/health`
2. **预期结果**：页面显示 JSON 数据，其中：
   - `"status": "healthy"` — 平台健康
   - `"llm_model": "Qwen/Qwen3.5-35B-A3B"` — 大模型已连接

#### 检查 4：API 文档可访问

1. 访问 `http://<IP>/docs`
2. **预期结果**：看到 Swagger API 文档页面，列出了所有 API 接口

---

### 7.2 AI 智能功能验证（vLLM 驱动）

> 以下功能全部依赖 vLLM 大模型服务。如果以下测试通过，说明大模型和所有 AI 智能体均工作正常。

#### 检查 5：AI 智能出题（出题智能体 question_agent）

这是最核心的 AI 功能，验证大模型是否能正确生成题目。

1. 在平台左侧菜单点击"**题库管理**"（或"**题库建设**"）
2. 点击"**新建题库**"或"**AI 生成题目**"
3. 填写：
   - 主题/内容：`人工智能的基本概念和应用`（或任意主题）
   - 题型：选择"单选题"
   - 数量：`3`
   - 难度：`中等`
4. 点击"生成"按钮
5. **预期结果**：
   - 出现加载动画（大模型正在思考）
   - 等待 10-30 秒后，显示 3 道 AI 生成的单选题
   - 每道题包含：题干、4 个选项（A/B/C/D）、正确答案、解析
   - 题目内容与主题相关，选项合理，不是模板化的固定文字

> **判断 AI 是否真正工作**：如果生成的题目内容丰富、有具体场景、选项各不相同，说明 AI 大模型在正常工作。如果题目看起来非常简单、模板化（如"以下哪个是正确的？A.正确 B.错误"），可能大模型未连接，系统在使用降级模式。

#### 检查 6：预览审阅流程

1. 在上一步生成题目后，应进入**预览页面**
2. 检查以下功能：
   - 能看到所有生成的候选题目
   - 可以勾选/取消勾选要保留的题目
   - 可以点击编辑某道题的题干或选项
   - 点击"确认保存"后，题目保存成功
3. **预期结果**：选中的题目成功保存到题库

#### 检查 7：AI 质量检查（审核智能体 review_agent）

1. 在"题库管理"中，找到刚才保存的题目
2. 选择一道题，点击"**AI 质量检查**"（或"AI 审核"）
3. **预期结果**：
   - 显示五维度评分（每项 1-5 分）：
     - 题干清晰度
     - 选项质量
     - 答案正确性
     - 知识对齐度
     - 难度校准
   - 显示综合评分（10 分制）
   - 给出审核建议（通过/修订/拒绝）

#### 检查 8：批量审核

1. 在"题库管理"中，勾选多道题目
2. 点击"**批量审核**"→"批量通过"
3. **预期结果**：所选题目状态变为"已通过"

---

### 7.3 素材管理功能验证

#### 检查 9：素材上传与解析（标注智能体 annotation_agent）

1. 在左侧菜单点击"**素材管理**"
2. 点击"**上传素材**"
3. 选择一个 PDF 或 DOCX 文件上传（内容与 AI 相关为佳）
4. **预期结果**：
   - 文件上传成功
   - 系统自动解析文件内容为知识单元
   - AI 自动标注每个知识单元的：
     - 所属维度（如"AI基础知识""AI技术应用"等）
     - 难度等级（1-5）
     - 知识点标签

#### 检查 10：基于素材 AI 出题

1. 在"素材管理"中，选择刚上传的素材
2. 点击"**基于素材生成题目**"
3. 设置题型和数量
4. **预期结果**：AI 根据素材内容生成相关的题目，题目内容紧扣素材主题

---

### 7.4 考试组卷功能验证

#### 检查 11：自然语言组卷（意图解析智能体 intent_agent）

1. 在左侧菜单点击"**考试管理**"
2. 选择"**智能组卷**"或"**自然语言组卷**"
3. 在输入框中输入自然语言描述，例如：

   ```
   出一套10道题的AI入门测试，包含8道单选和2道判断，难度简单
   ```

4. **预期结果**：
   - 系统（意图解析智能体）将自然语言转化为组卷参数
   - 显示解析结果：题目数量 10、单选 8 + 判断 2、难度 简单
   - 自动从题库中抽取符合条件的题目组成试卷

---

### 7.5 评分功能验证

#### 检查 12：主观题 AI 评分（评分智能体 scoring_agent）

> 此功能需要有已提交的含主观题（简答题）的答卷。如暂无答卷可跳过。

1. 在"**成绩管理**"中，找到一份含简答题的答卷
2. 点击"**AI 评分**"或"**批阅**"
3. **预期结果**：
   - AI 对每道主观题给出评分（按满分比例）
   - 给出评分反馈说明（如"概念基本正确，但缺少具体案例"）

---

### 7.6 互动问答功能验证

#### 检查 13：情景互动测试（互动智能体 interactive_agent）

> 如果平台已启用情景互动模块：

1. 在左侧菜单点击"**情景互动**"（或"互动问答"）
2. 选择一个场景开始互动（如"AI 产品经理决策场景"）
3. 与 AI 进行多轮对话，回答场景中的问题
4. **预期结果**：
   - AI 扮演特定角色与你对话
   - 根据你的回答动态调整难度
   - 对话结束后给出三维度评分：
     - 提示工程能力
     - 批判性思维
     - 伦理决策能力

---

### 7.7 验证结果汇总

完成以上所有检查后，填写以下表格确认：

| 序号 | 检查项 | 涉及的 AI 智能体 | 结果 |
|------|--------|-----------------|------|
| 1 | 平台首页加载 | — | ✅ / ❌ |
| 2 | 管理员登录 | — | ✅ / ❌ |
| 3 | API 健康检查 | — | ✅ / ❌ |
| 4 | API 文档访问 | — | ✅ / ❌ |
| 5 | AI 智能出题 | 出题智能体 (question_agent) | ✅ / ❌ |
| 6 | 预览审阅流程 | — | ✅ / ❌ |
| 7 | AI 质量检查 | 审核智能体 (review_agent) | ✅ / ❌ |
| 8 | 批量审核 | — | ✅ / ❌ |
| 9 | 素材上传与解析 | 标注智能体 (annotation_agent) | ✅ / ❌ |
| 10 | 基于素材 AI 出题 | 出题智能体 (question_agent) | ✅ / ❌ |
| 11 | 自然语言组卷 | 意图解析智能体 (intent_agent) | ✅ / ❌ |
| 12 | 主观题 AI 评分 | 评分智能体 (scoring_agent) | ✅ / ❌ |
| 13 | 情景互动测试 | 互动智能体 (interactive_agent) | ✅ / ❌ |

> **全部 ✅** = 平台所有功能（含 AI 智能体）已完全恢复。
>
> **检查 5-13 中有 ❌** = AI 功能异常，请先回到[第 5 章](#5-第三步启动大模型服务-vllm)检查 vLLM 是否正常运行。
>
> **检查 1-4 中有 ❌** = 基础服务异常，请回到[第 6 章](#6-第四步启动平台所有服务-docker)检查 Docker 容器状态。

---

## 8. 关机与停止服务

### 8.1 正常停止（不关机，只停服务）

```bash
# 1. 停止平台容器（数据不丢失）
cd ~/ai-literacy-platform
docker compose down

# 2. 停止 vLLM
pkill -f "vllm.entrypoints"
```

### 8.2 完全关机

```bash
# 1. 先停止平台容器
cd ~/ai-literacy-platform
docker compose down

# 2. 停止 vLLM
pkill -f "vllm.entrypoints"

# 3. 关机
sudo shutdown now
```

### 8.3 再次开机后的启动顺序

服务器重新开机后，需要按顺序重新启动服务：

```bash
# 1. 确认 Docker 服务已自启动
sudo systemctl status docker --no-pager

# 2. 启动 vLLM（等待模型加载 1-3 分钟）
export HF_ENDPOINT=https://hf-mirror.com
nohup ~/vllm-env/bin/python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen3.5-35B-A3B-GPTQ-Int4 \
  --served-model-name Qwen/Qwen3.5-35B-A3B \
  --host 0.0.0.0 --port 8100 \
  --trust-remote-code \
  > ~/vllm-server.log 2>&1 &

# 3. 等待 vLLM 加载完成（观察日志）
tail -f ~/vllm-server.log
# 看到 "Uvicorn running" 后按 Ctrl+C

# 4. 启动平台
cd ~/ai-literacy-platform
docker compose up -d

# 5. 等待 1-2 分钟后验证
docker compose ps
curl -s http://localhost:8000/api/v1/health | python3 -m json.tool
```

---

## 9. 常见问题排查

### 问题 1：浏览器访问 `http://<IP>` 无法打开页面

**排查步骤**：

```bash
# 1. 检查前端容器是否运行
docker compose ps | grep frontend

# 2. 检查 80 端口是否被占用
ss -tlnp | grep :80

# 3. 检查防火墙
sudo ufw status
```

| 现象 | 原因 | 解决方法 |
|------|------|---------|
| frontend 容器未运行 | 容器启动失败 | `docker compose up -d frontend` |
| 80 端口无监听 | 前端容器没启动 | `docker compose restart frontend` |
| 防火墙阻止 | 80 端口未放行 | `sudo ufw allow 80/tcp` |
| 客户电脑 ping 不通 | 网络不通 | 检查网线、交换机、IP 是否同一网段 |

### 问题 2：能打开登录页，但登录失败（401 错误）

```bash
# 查看后端日志
docker compose logs --tail=50 app
```

| 现象 | 原因 | 解决方法 |
|------|------|---------|
| 密码错误 | 默认密码已修改 | 联系管理员获取新密码 |
| 数据库未就绪 | postgres 容器不健康 | `docker compose restart postgres` 后等待 30 秒 |
| 后端报错 | 配置问题 | 查看 `docker compose logs app` 的错误信息 |

### 问题 3：AI 出题功能不工作（返回模板化简单题目）

这通常说明 vLLM 大模型没有正常运行。

```bash
# 1. 检查 vLLM 进程
ps aux | grep vllm

# 2. 检查 vLLM 端口
curl -s http://localhost:8100/v1/models

# 3. 查看 vLLM 日志
tail -30 ~/vllm-server.log
```

| 现象 | 原因 | 解决方法 |
|------|------|---------|
| vLLM 进程不存在 | 未启动或已崩溃 | 回到 [5.2 启动 vLLM](#52-启动-vllm) |
| `curl` 连接失败 | vLLM 未监听 8100 端口 | 查看日志 `tail ~/vllm-server.log`，可能模型还在加载 |
| 日志中有 `CUDA error` | GPU 相关问题 | 运行 `nvidia-smi` 检查 GPU 状态 |
| 日志中有 `OOM` | 显存不足 | 等待其他 GPU 进程结束后重启 vLLM |

### 问题 4：vLLM 启动报错 `cutlass_scaled_mm` 或 `CUTLASS`

这是因为 FP8 量化模型不兼容此 GPU（Blackwell 架构）。当前已使用 GPTQ-Int4 版本，正常不会遇到此问题。如果遇到，确认启动命令中的模型是：

```
--model Qwen/Qwen3.5-35B-A3B-GPTQ-Int4
```

**不要**使用带 `FP8` 字样的模型。

### 问题 5：某个 Docker 容器一直 `unhealthy`

```bash
# 查看具体哪个容器有问题
docker compose ps

# 查看该容器的日志（将 <容器名> 替换为实际名称）
docker compose logs --tail=50 <容器名>
```

常见容器问题：

| 容器 | 常见原因 | 解决方法 |
|------|---------|---------|
| postgres | 磁盘空间不足 | `df -h` 检查磁盘，清理空间 |
| elasticsearch | 内存不足 | 重启容器 `docker compose restart elasticsearch` |
| milvus | etcd 未就绪 | 先重启 etcd：`docker compose restart etcd`，再重启 milvus |
| minio | 数据卷损坏 | `docker compose restart minio` |

### 问题 6：vLLM 进程存在但 8100 端口没有响应

```bash
# 可能模型仍在加载中，查看日志确认
tail -5 ~/vllm-server.log
```

如果日志中还在显示 `Loading model weights` 或 `Loading safetensors`，说明模型还在加载，耐心等待即可。

### 问题 7：需要完全重置（谨慎使用）

> ⚠️ **以下操作会清除所有数据**（题库、用户、考试记录全部丢失），仅在万不得已时使用：

```bash
cd ~/ai-literacy-platform

# 停止并删除所有容器和数据卷
docker compose down -v

# 重新启动（会重新初始化空数据库）
docker compose up -d
```

---

## 10. 附录：服务端口一览

| 服务 | 端口 | 对外暴露 | 说明 |
|------|------|---------|------|
| Nginx（前端网站） | **80** | **是** | 用户唯一访问入口 |
| FastAPI（后端 API） | 8000 | 否 | 由 Nginx 反向代理 |
| vLLM（大模型推理） | 8100 | 否 | AI 智能体的大脑 |
| PostgreSQL（主数据库） | 5432 | 否 | 存储用户、题目、考试等数据 |
| Elasticsearch（搜索引擎） | 9200 | 否 | 题目全文搜索 |
| Milvus（向量数据库） | 19530 | 否 | 语义检索、题目查重 |
| MinIO（文件存储） | 9000/9001 | 否 | 素材文件存储 |
| RabbitMQ（消息队列） | 5672/15672 | 否 | 异步任务处理 |
| Redis（缓存） | 6379 | 否 | 数据缓存 |

> 客户只需要知道一个地址：`http://<服务器IP>`，通过 80 端口访问。其余端口全部是内部使用，无需对外开放。

---

## 快速参考卡片（可打印）

```
┌─────────────────────────────────────────────────┐
│          AI素养评测平台 — 快速启动卡片             │
├─────────────────────────────────────────────────┤
│                                                 │
│  服务器用户名: dell                               │
│  平台管理员:   admin / admin123                   │
│  项目路径:     ~/ai-literacy-platform             │
│                                                 │
│  ❶ 查看 IP:                                     │
│     hostname -I                                 │
│                                                 │
│  ❷ 启动 vLLM（AI 大脑）:                         │
│     export HF_ENDPOINT=https://hf-mirror.com    │
│     nohup ~/vllm-env/bin/python \               │
│       -m vllm.entrypoints.openai.api_server \   │
│       --model Qwen/Qwen3.5-35B-A3B-GPTQ-Int4 \ │
│       --served-model-name Qwen/Qwen3.5-35B-A3B \│
│       --host 0.0.0.0 --port 8100 \              │
│       --trust-remote-code \                     │
│       > ~/vllm-server.log 2>&1 &                │
│     （等 1-3 分钟加载模型）                        │
│                                                 │
│  ❸ 启动平台:                                     │
│     cd ~/ai-literacy-platform                   │
│     docker compose up -d                        │
│     （等 1-2 分钟启动容器）                        │
│                                                 │
│  ❹ 验证:                                        │
│     浏览器访问 http://<服务器IP>                   │
│     用 admin / admin123 登录                     │
│                                                 │
│  停止: docker compose down                      │
│  停止 vLLM: pkill -f "vllm.entrypoints"         │
│                                                 │
└─────────────────────────────────────────────────┘
```
