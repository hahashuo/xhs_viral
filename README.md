# xhs_viral：小红书内容 harness

在你自己的 Windows 电脑上，用 Claude Code 驱动的小红书笔记工作流：

**idea → 三个模型各写一版（Claude、DeepSeek、豆包）→ 你挑选定稿 → 自动生成文字卡片和拍摄建议 → 风控检查 → 发布**

发布有两种模式，都必须经过你：

| 模式 | 做法 | 什么时候用 |
| --- | --- | --- |
| B（默认） | 导出发布包，你用手机发 | 新号起步期，风险最低 |
| A | 你确认后由 xiaohongshu-mcp 自动发 | 账号稳定后 |

设计方案和风控思路见 [设计文档](https://claude.ai/artifact/UyafKNdH3n9JiiihC8SkBL)。

## 一次性安装（Windows）

1. 安装 [Python 3.11+](https://www.python.org/downloads/windows/)（安装时勾选「Add python.exe to PATH」）、[Git](https://git-scm.com/download/win) 和 [Claude Code](https://docs.claude.com/en/docs/claude-code/setup)。
2. 在 PowerShell 里：

   ```powershell
   git clone https://github.com/hahashuo/xhs_viral.git
   cd xhs_viral
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   python -m playwright install chromium
   copy .env.example .env
   ```

3. 用记事本打开 `.env`，填入 DeepSeek 和豆包的 API key（没有的话也能用，只是少了对应那一版）：
   - DeepSeek：<https://platform.deepseek.com> → API keys
   - 豆包：<https://console.volcengine.com/ark> → API Key 管理；在「在线推理」里开通一个豆包模型，把模型名或接入点 ID（`ep-` 开头）填进 `DOUBAO_MODEL`
4. 在仓库目录里运行 `claude`，就可以用下面的指令了。

## 指令

| 指令 | 作用 |
| --- | --- |
| `/idea <想法>` | 生成一篇笔记：策划、三版初稿、定稿、卡片、风控检查 |
| `/publish` | 发布最新定稿（模式 B 导出发布包；模式 A 确认后自动发） |
| `/published [链接]` | 手动发完后记一笔 |
| `/niche [领域]` | 查看或切换专精领域 |
| `/new-niche <领域>` | 新建领域 |
| `/persona <信息>` | 更新人设 |
| `/mode A\|B` | 切换发布模式 |
| `/eval [step]` | 跑 agent 能力评测 |

例子：`/idea 被裁员后第一周应该做的事`

## 模式 A 设置（可选，账号稳定后再开）

1. 从 [xiaohongshu-mcp Releases](https://github.com/xpzouying/xiaohongshu-mcp/releases) 下载 `xiaohongshu-login-windows-amd64.exe` 和 `xiaohongshu-mcp-windows-amd64.exe`。
2. 先运行登录工具，用小红书 App 扫码登录**测试小号**。
3. 运行 `xiaohongshu-mcp-windows-amd64.exe`，保持窗口开着。
4. 在仓库目录运行：`claude mcp add --transport http xiaohongshu-mcp http://localhost:18060/mcp`
5. 在 Claude Code 里 `/mode A`。

注意：同一账号不能同时在电脑网页端登录，否则自动发布会掉线。

## 测试

```powershell
python -m unittest discover -s tests -t . -v
```

- 单元测试不需要任何 API key，不联网，在临时目录里运行，不会动你的 `drafts/` 和 `state/`。
- 卡片渲染测试需要 `python -m playwright install chromium`，没装会自动跳过。
- 真实接口测试默认跳过。要跑的话，先在 `.env` 填好 key，再执行：

  ```powershell
  $env:RUN_LIVE_TESTS = "1"
  python -m unittest tests.test_live_llm -v
  ```

  会各调用 DeepSeek 和豆包一次，产生少量费用。
- GitHub Actions 会在 Ubuntu 和 Windows 上自动跑单元测试。

### agent 能力评测

单元测试检查代码；`python -m evals` 检查 agent 在每一步（初稿、挑选、卡片、风控、发布决策）做得好不好。风控引擎那组不需要 key：`python -m evals --step risk_engine`。其余需要在 `.env` 填 `ANTHROPIC_API_KEY`（或用 `--agent deepseek`）。详见 [evals/README.md](evals/README.md)，Claude Code 里可以用 `/eval`。

## 目录

```
harness.toml        当前领域、发布模式、频率上限
niches/<领域>/      领域配置包：persona、topics、style、tags、banned、insights
risk/               风控资料库：规则来源、敏感词、发布清单、限流记录
harness/            Python 工具（python -m harness --help）
drafts/             每篇笔记的草稿（不提交到 git）
```

## 路线

- [x] 第 2 步：idea → 定稿 → 风控 → 发布（本版本）
- [ ] 第 3 步：第三方数据 API 抓取同领域爆款，`/trends`
- [ ] 第 4 步：每周 `/review`，用笔记数据 + 爆款 + 风控资料提出配置修改 PR
