"""v2 演示脚本：覆盖 v2 的全部板块（全部虚构）。

- 完整提示词（中文四段式模板 + MJ 英文参数串）；
- 网盘链接与提取码、GitHub / X / 公众号链接；
- 被验证过的 SOP（编号步骤 + 实测）；群友自述的收益和耗时数字；
- 演示图片和文档（data_dir/demo_media/，由 seed 生成）；
- 违法高危话题（出售实名号）、含个人手机号的隐私消息（曝光甲方）。
手机号用的是公开的测试号段示例，不是真实号码。
"""

from bureau.demo.model import L, T

AVATAR_PROMPT = ("分享一个我反复调了两周的水彩头像提示词模板，即梦 4.0 直接用：\n"
                 "【画面风格】水彩手绘，湿画法晕染，留白 30%，纸张纹理明显，线条松弛不描边\n"
                 "【主体】{人物或宠物}的半身像，表情放松，眼神看向镜头左侧\n"
                 "【色彩】低饱和莫兰迪色，主色不超过 3 种，阴影用冷灰紫\n"
                 "【构图】主体居中偏下，头顶留出三分之一空白，背景只有淡淡的色块")
MJ_PROMPT = ("MJ 版本：watercolor portrait of a young woman, loose wet-on-wet washes, visible paper texture, "
             "muted morandi palette, generous white space, soft cool shadows --ar 3:4 --stylize 150 --v 7")

V2_THREADS: list[T] = [
    # ---------------- 完整提示词（prompts 板块） ----------------
    T("avatar_prompt", "avatar_prompt", ("wx_shouhui8",), (0,), (
        L("A", AVATAR_PROMPT),
        L("A", "", kind="image", media="watercolor_avatar.png"),
        L("B", "MJ 能用吗，还是只适合即梦", reply=0),
        L("A", "MJ 要换成英文，我也整理了一版，参数是实测下来最稳的", reply=2),
        L("A", MJ_PROMPT, reply=3),
        L("C", "照着试了，宠物头像也能用，固定种子以后风格基本不跑"),
        L("D", "收藏了，留白那条很关键，之前总是画得太满"),
    ), hours=(20, 23)),
    # ---------------- 网盘链接与提取码（resources 板块） ----------------
    T("comfy_pack", "comfy_pack", ("qq_comfy",), (0,), (
        L("A", "整理了一个 ComfyUI 工作流整合包：PuLID 角色一致性、Wan 首尾帧、Flux GGUF 低显存三套，"
               "百度网盘 https://pan.baidu.com/s/1DemoPackA7k2Xq?pwd=a7k2 提取码：a7k2"),
        L("B", "有夸克的吗，百度限速太慢", reply=0),
        L("A", "夸克也传了一份：https://pan.quark.cn/s/demo8c3f2e1a 不用提取码", reply=1),
        L("C", "PuLID 那套是 v2 分支吗"),
        L("A", "是，跟前面群里说的 v2 分支一样，节点版本写在包里的说明文档里", reply=3),
    ), hours=(19, 22)),
    # ---------------- X 链接 ----------------
    T("seedance_x", "seedance_x", ("wx_aichutu",), (0,), (
        L("A", "Seedance 官方号发了多镜头一致性的演示，一段 10 秒视频里切了 4 个镜头，人物没崩："
               "https://x.com/demo_seedance/status/1850000000000000001"),
        L("B", "能免费用吗", reply=0),
        L("A", "目前只开了内测，排队申请，正式开放时间没说", reply=1),
        L("C", "做漫剧的话这个比首尾帧一格一格拼省事多了"),
    ), hours=(10, 13)),
    # ---------------- 公众号文章 ----------------
    T("bitable_article", "agent_auto", ("wx_xhs",), (0,), (
        L("A", "这篇多维表格自动化讲得很细，10 个模板直接能抄，商品表一行进、小红书文案一行出："
               "https://mp.weixin.qq.com/s/DemoBitableAutoTemplates10"),
        L("B", "里面的 AI 字段提示词有写吗", reply=0),
        L("A", "有，每个模板都附了字段提示词，还有触发自动化的设置截图", reply=1),
        L("C", "我们店就是这么批量出文案的，200 个商品半小时搞定"),
    ), hours=(9, 12)),
    # ---------------- SOP + GitHub + 图片 + 自述数字（sops / tools / data 板块） ----------------
    T("flux_gguf", "flux_gguf", ("qq_comfy",), (0,), (
        L("A", "8G 显存跑 Flux 的流程我跑通了，分享一下：第一步装 ComfyUI-GGUF 节点 https://github.com/city96/ComfyUI-GGUF ；"
               "第二步下载 flux1-dev-Q4_K_S.gguf 放进 models/unet；第三步把 Load Diffusion Model 换成 Unet Loader (GGUF)；"
               "第四步启动参数加 --lowvram。实测 1024 出图 75 秒左右"),
        L("A", "", kind="image", media="flux_gguf_workflow.png"),
        L("B", "Q4 画质掉得厉害吗", reply=0),
        L("A", "细节比 fp8 少一点，出草图和测提示词完全够用", reply=2),
        L("C", "3060 8G 照着做一次跑通了，比 fp8 快一倍"),
        L("D", "这个 GGUF 节点 GitHub 上星挺多的，应该靠谱"),
    ), hours=(20, 23)),
    # ---------------- 文档（PDF）：LoRA 参数备忘 ----------------
    T("comfy_lora_doc", "comfy_char", ("qq_comfy",), (0,), (
        L("A", "之前问 LoRA 训练参数的，我把自己的备忘整理成文档了，底模、rank、学习率、打标和验收标准都在里面"),
        L("A", "", kind="file", media="角色LoRA训练参数备忘.pdf"),
        L("B", "12G 显存能训吗", reply=0),
        L("A", "能，开 gradient checkpointing，文档最后一段写了", reply=2),
    ), hours=(14, 17)),
    # ---------------- 违法高危：只进风险板块 ----------------
    T("risk_account", "risk_account", ("qq_jiedan",), (0,), (
        L("A", "出售实名号，老号带好友带朋友圈，注册满三年，防封稳定，批量拿价格私聊，加V看号"),
        L("B", "买卖账号是违法的，号主找回来钱也没了", reply=0),
        L("C", "这种实名号多半是盗来的，碰了要担责任"),
        L("D", "群主踢了吧"),
    ), hours=(22, 23)),
    # ---------------- 隐私：整条剔除 ----------------
    T("privacy_doxx", "privacy_doxx", ("qq_jiedan",), (0,), (
        L("A", "大家注意这个人：上周找我做海报，交稿以后不给尾款还拉黑，尾款 600 块，他叫王某某，"
               "电话 13800138000，住在滨江区某某小区，接单的都小心"),
        L("B", "这样公开别人电话不太好吧，可以走平台投诉", reply=0),
        L("C", "先留聊天记录和交付记录，以后先收定金", reply=0),
        L("A", "好，我去平台投诉", reply=1),
    ), hours=(15, 18)),
]
