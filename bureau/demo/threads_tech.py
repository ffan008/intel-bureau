"""编程与自动化类脚本：Claude Code、Codex、MCP、n8n、飞书多维表格。"""

from bureau.demo.model import L, T

TECH_THREADS: list[T] = [
    # ---------------- Claude Code 实战（持续发酵） ----------------
    T("cc_claudemd", "cc_practice", ("wx_cccamp",), (-5,), (
        L("A", "CLAUDE.md 的写法分享：项目结构、常用命令、代码风格三块就够了，放在仓库根目录，控制在 200 行以内，太长它反而不看"),
        L("B", "要不要写测试命令", reply=0),
        L("A", "要，写清楚怎么跑单测，它改完代码会自己跑", reply=1),
        L("C", "官方文档也有说明：https://docs.anthropic.com/en/docs/claude-code/memory"),
    )),
    T("cc_hooks", "cc_practice", ("wx_cccamp",), (-3,), (
        L("A", "hooks 真的好用：配了一个 PostToolUse 钩子，每次改完文件自动跑 ruff 和单测，失败了它会自己接着修"),
        L("B", "配置写在哪里", reply=0),
        L("A", "写在 .claude/settings.json 的 hooks 字段里，matcher 填 Edit|Write", reply=1),
        L("C", "这个省了好多来回"),
    )),
    T("cc_skill_basic", "cc_practice", ("wx_cccamp",), (-2,), (
        L("A", "Skill 和 slash 命令的区别：Skill 是按描述自动调用的，命令要自己输入。每个 Skill 一个文件夹，里面放 SKILL.md"),
        L("B", "description 要怎么写", reply=0),
        L("A", "写清楚什么时候该用它，比如「用户要写周报时使用」，写得越具体触发越准", reply=1),
    )),
    T("cc_skill_team", "cc_practice", ("wx_cccamp",), (0,), (
        L("A", "我们团队把常用流程都封装成 Skill 了：写周报、生成测试用例、整理会议纪要，三个 Skill 放在 .claude/skills 目录，新人入职直接能用"),
        L("B", "Skill 和子代理一起用是什么效果", reply=0),
        L("A", "子代理负责跑耗时的任务，比如批量生成测试用例；主会话只看结果，上下文干净很多", reply=1),
        L("C", "测试用例那个 Skill 能分享下 SKILL.md 吗"),
        L("A", "整理好了放这里：https://github.com/anthropics/skills ，我们的模板是照着官方示例改的", reply=3),
        L("D", "照着做了一个整理会议纪要的，第一次就触发对了"),
    ), hours=(20, 23), forward=("fs_agent", "wx_aichutu")),
    T("cc_vs_codex", "cc_practice", ("wx_cccamp",), (0,), (
        L("A", "实测对比：同一个 23 个文件的 Python 重构任务，Claude Code 用了 18 分钟一次跑通，Codex 用了 25 分钟，中间有 2 次测试没过要我提示"),
        L("B", "token 消耗呢", reply=0),
        L("A", "Claude Code 大概 1.2M token，Codex 没看到具体数字", reply=1),
        L("C", "我的体感也是，Codex 小改动更快，大重构还是 Claude Code 稳"),
        L("D", "有没有试过让两个互相 review"),
        L("A", "试过，Codex 写 Claude Code 审，能多抓出几个边界问题", reply=4),
        L("A", "", kind="image", media="cc_codex_compare.png"),
    ), hours=(12, 17)),
    T("cc_relay_risk", "cc_relay", ("wx_cccamp",), (0,), (
        L("A", "有人在推 Claude 中转 API，号称官方价格 3 折，有人用过吗"),
        L("B", "别用，这种基本是共享账号池，随时跑路，代码还可能被记录", reply=0),
        L("C", "我之前充了 200 用了一周就打不开了，客服也找不到"),
        L("D", "要省钱就用官方的订阅或者正规云厂商，别贪便宜"),
    ), hours=(21, 23)),
    # ---------------- 自动化（持续发酵） ----------------
    T("agent_n8n", "agent_auto", ("fs_agent",), (-4,), (
        L("A", "n8n 自托管版跑了一周：每天早上 8 点抓 20 个 RSS，调用模型写摘要，推到飞书群，一次都没挂"),
        L("B", "部署在哪", reply=0),
        L("A", "家里的 NAS 上用 Docker 跑的，内存占用 300M 左右", reply=1),
    )),
    T("agent_dify", "agent_auto", ("fs_agent",), (-2,), (
        L("A", "n8n 和 Dify 怎么选：流程编排用 n8n，知识库问答用 Dify，两个可以通过 webhook 串起来"),
        L("B", "有现成模板吗", reply=0),
        L("A", "n8n 官方模板库很多：https://n8n.io/workflows/", reply=1),
    )),
    T("agent_bitable", "agent_auto", ("fs_agent", "wx_xhs"), (0,), (
        L("A", "飞书多维表格 AI 字段批量写小红书文案：产品卖点一列，AI 字段写提示词引用这一列，200 行 3 分钟跑完"),
        L("B", "收费吗", reply=0),
        L("A", "企业版有免费额度，超出按次数计费，我这次没超", reply=1),
        L("C", "质量怎么样"),
        L("A", "六成能直接用，剩下的改改标题就行。提示词里写清楚「口语化、带 emoji、不超过 200 字」效果好很多", reply=3),
        L("D", "多维表格还能接自动化，生成完自动通知负责人"),
    ), hours=(10, 16)),
    T("agent_mcp_report", "agent_auto", ("fs_agent",), (0,), (
        L("A", "用 MCP 连 WeChatDataAnalysis 做群聊日报：本地导出群消息，Claude Code 写脚本按话题聚类，每天 8 点生成日报发到飞书"),
        L("B", "WeChatDataAnalysis 是开源的吗", reply=0),
        L("A", "开源的，本地跑，数据不出电脑：https://github.com/LifeArchiveProject/WeChatDataAnalysis", reply=1),
        L("C", "注意它的本地 API 没有鉴权，跑的时候别开乱七八糟的网页"),
        L("D", "日报里的数字最好让代码算，别让模型自己数，之前遇到过序号全是 1 的情况"),
    ), hours=(14, 18)),
]
