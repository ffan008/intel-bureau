"""AI 创作类脚本：漫剧（最近 24 小时的上升话题）、ComfyUI、手绘、风格词。"""

from bureau.demo.model import L, T

CREATE_THREADS: list[T] = [
    # ---------------- 上升话题：即梦首尾帧做漫剧（只在最近 24 小时） ----------------
    T("manju_flow_main", "manju_flow", ("wx_shouhui8",), (0,), (
        L("A", "分享一个我这两天跑通的漫剧流程：先用即梦文生图定角色，再用首尾帧模式做 5 秒镜头，最后剪映拼起来配音。一集 1 分钟大概 12 个镜头"),
        L("B", "首尾帧具体怎么用？是上传两张图吗", reply=0),
        L("A", "对，第一步在即梦选「首尾帧」，上传起始和结束两张图；第二步写动作描述，比如「女孩转身走向窗边」；第三步时长选 5 秒，生成 2~3 次挑最好的", reply=1),
        L("C", "积分消耗怎么样，一集要多少"),
        L("A", "我实测一集 12 个镜头大概花了 360 积分，算下来不到 30 块钱", reply=3),
        L("D", "比我外包便宜太多了，之前找人做一集要 800"),
        L("E", "学到了，回去试试"),
    ), hours=(19, 23)),
    T("manju_storyboard", "manju_flow", ("qq_manju",), (0,), (
        L("A", "做漫剧最重要的是分镜，我现在用表格写：镜号、景别、画面描述、台词、时长五列，一集 12 格。写完整张表再批量丢给即梦"),
        L("B", "能发个模板吗", reply=0),
        L("A", "", kind="file", media="漫剧分镜表模板.docx"),
        L("A", "", kind="image", media="storyboard_table.png"),
        L("C", "这个表格思路好，之前都是想到哪做到哪"),
        L("D", "分镜写细一点，首尾帧出来的动作就准很多，我试过写「中景，侧身回头」比只写「回头」稳定"),
        L("A", "对，景别一定要写，不然镜头忽远忽近", reply=4),
    ), hours=(20, 23)),
    T("manju_consistency", "manju_flow", ("wx_aichutu",), (0,), (
        L("A", "角色一致性我测了一圈，最稳的组合是：MJ 先出一张定妆照，即梦里用参考图模式加固定种子，同一个角色 10 个镜头基本不崩"),
        L("B", "固定种子在即梦哪里设", reply=0),
        L("A", "高级设置里有个「随机种子」，关掉随机，手动填一个数字，后面每个镜头都填同一个", reply=1),
        L("C", "MJ 定妆照要加 --cref 吗"),
        L("A", "要，--cref 加上 --cw 100，脸和衣服都会锁住", reply=3),
        L("D", "照着试了，侧脸也没崩，感谢"),
    ), hours=(12, 16)),
    T("manju_xhs", "manju_flow", ("wx_xhs",), (0,), (
        L("A", "AI 漫剧号最近起号很快，我看到一个古风短剧账号，一周涨粉 3000+，每天更一集 1 分钟"),
        L("B", "他们配音是真人还是 AI", reply=0),
        L("A", "大部分用剪映的克隆音色，录 1 分钟样本就能用，听不太出来", reply=1),
        L("C", "封面一般怎么做"),
        L("A", "统一用第一个镜头的首帧加大字标题，做成固定模板，辨识度高", reply=3),
        L("D", "感觉这个赛道很快会卷起来"),
        L("E", "现在入场还算早，先把流程跑顺比较重要"),
    ), hours=(20, 23)),
    T("manju_pilot", "manju_flow", ("fs_aigc",), (0,), (
        L("A", "同步一下本周 AI 漫剧试点：用即梦首尾帧做了 3 集，平均每集 1 分 20 秒，单集制作时间从 2 天降到 5 小时"),
        L("B", "分镜还是人工写吗", reply=0),
        L("A", "分镜脚本先让模型出初稿，人工改 30% 左右，画面全部 AI 生成", reply=1),
        L("C", "下周可以把配音也换成 AI，我这边测过剪映克隆音色"),
        L("A", "可以，周三前出一版对比，周五选题会上定", reply=3),
    ), hours=(10, 17)),
    T("manju_comfy_flf", "manju_flow", ("qq_comfy",), (0,), (
        L("A", "ComfyUI 能做首尾帧吗？不想一直花即梦积分"),
        L("B", "可以，用 Wan 的首尾帧工作流，不过 12G 显存起步，5 秒视频本地要跑 8 分钟左右", reply=0),
        L("C", "我 4070 跑过，分辨率降到 480p 能跑，画质差一点"),
        L("A", "那还是先用即梦出样片，定稿镜头再本地跑", reply=1),
    ), hours=(21, 23)),
    T("manju_demand", "jiedan", ("qq_jiedan",), (0,), (
        L("A", "有偿求：AI 漫剧短视频 20 条，用于投放测试，每条 30~60 秒，按条结算，单条预算 300，要求角色统一"),
        L("B", "有样片要求吗", reply=0),
        L("A", "要先出 1 条样片，风格古风或都市都行，下周一前交样片", reply=1),
        L("C", "可以接，我用即梦首尾帧做，私聊发你作品"),
    ), hours=(14, 18)),
    # ---------------- ComfyUI 角色一致性（持续发酵） ----------------
    T("comfy_lora", "comfy_char", ("qq_comfy",), (-5,), (
        L("A", "分享一下角色 LoRA 的训练参数：30 张图，rank 16，学习率 1e-4，训练 10 个 epoch，Flux 底模，效果很稳"),
        L("B", "图片要什么角度", reply=0),
        L("A", "正面、侧面、半身、全身都要有，表情也要多几种，不然泛化很差", reply=1),
        L("C", "打标用什么"),
        L("A", "用 Florence2 自动打标，再手动删掉多余的描述词", reply=3),
    )),
    T("comfy_ipadapter", "comfy_char", ("qq_comfy", "wx_aichutu"), (-3,), (
        L("A", "角色一致性工作流更新：IPAdapter 加 LoRA 一起用，IPAdapter 权重 0.6，LoRA 权重 0.8，脸和服装都比较稳定"),
        L("B", "IPAdapter 用哪个模型"),
        L("A", "脸用 plus face，服装用普通版，两个串起来", reply=1),
        L("C", "求工作流文件"),
        L("A", "放 GitHub 了：https://github.com/comfyanonymous/ComfyUI 的 custom_nodes 里装 IPAdapter_plus，工作流 json 在群文件", reply=3),
    )),
    T("comfy_pulid", "comfy_char", ("qq_comfy",), (0,), (
        L("A", "工作流又更新了：把 IPAdapter 换成 PuLID，脸部相似度明显更高，就是多吃 2G 显存"),
        L("B", "PuLID 支持 Flux 吗", reply=0),
        L("A", "支持，装 PuLID-Flux 节点包就行，我的工作流已经切到 v2 分支", reply=1),
        L("C", "配合首尾帧做漫剧镜头应该很合适"),
        L("A", "对，先用 PuLID 出首帧和尾帧，再丢给视频模型，一致性好很多", reply=3),
    ), hours=(20, 23)),
    T("comfy_vram", "comfy_vram", ("qq_comfy",), (-1,), (
        L("A", "显存 8G 的看过来：Flux 用 fp8 版本，再加 --lowvram 启动参数，1024 分辨率也能出图，一张 40 秒左右"),
        L("B", "画质掉得多吗", reply=0),
        L("A", "肉眼基本看不出来，细节稍微少一点", reply=1),
        L("C", "我 3060 试了，确实能跑，感谢"),
    )),
    T("mj_hand_qa", "mj_qa", ("wx_aichutu",), (0,), (
        L("A", "MJ 放大以后手指总是糊，有什么办法吗"),
        L("B", "先用局部重绘（Vary Region）把手单独重画，再做 Subtle 放大，不要直接 Creative", reply=0),
        L("C", "或者丢 ComfyUI 用 hand refiner 节点修，我试下来成功率七成左右"),
        L("A", "好的，两个都试试", reply=1),
    ), hours=(9, 12)),
    # ---------------- 手绘风（持续） ----------------
    T("shouhui_prompt", "shouhui", ("wx_shouhui8",), (-6,), (
        L("A", "手绘水彩风的提示词结构分享：主体 + loose watercolor, ink outline, paper texture + 留白，MJ 里 --stylize 150 左右最自然"),
        L("B", "用的 v7 吗", reply=0),
        L("A", "是 v7，v6 也可以但纸张纹理弱一点", reply=1),
        L("C", "收藏了"),
    )),
    T("shouhui_quote", "shouhui", ("wx_shouhui8",), (-4,), (
        L("A", "接了个绘本插画单，12 页，甲方给 2400，大家觉得这个价合理吗"),
        L("B", "偏低了，正常水彩插画商用 150~250 一页", reply=0),
        L("C", "要看是否包含修改次数和商用授权，最好合同里写清楚"),
        L("A", "好，我去补一下授权范围再谈", reply=2),
    )),
    T("shouhui_homework", "shouhui", ("wx_shouhui8",), (-1,), (
        L("A", "本周作业复盘：一共交了 46 份，用即梦的占六成，MJ 三成，剩下是 ComfyUI。优秀作业的提示词和参数整理在文档里了"),
        L("B", "文档在哪看", reply=0),
        L("A", "https://docs.qq.com/doc/demo-shouhui8-week12", reply=1, kind="link", title="水彩手绘研习社 · 第 12 周作业复盘"),
        L("C", "这周的水彩手绘头像好多都很好看"),
    )),
    # ---------------- 风格词对照表（持续） ----------------
    T("style_mj", "style_table", ("wx_aichutu",), (-2,), (
        L("A", "整理了 50 个 MJ 常用风格词对照表，每个都配了同一提示词的出图对比，链接放这里了"),
        L("B", "https://www.notion.so/demo-mj-style-50", kind="link", title="MJ 风格词对照表（50 个）"),
        L("C", "太实用了，收藏"),
        L("D", "能不能也出一个即梦版的", reply=0),
    )),
    T("style_jimeng", "style_table", ("wx_shouhui8",), (0,), (
        L("A", "即梦版风格词对照表也做好了，40 种风格，同一个提示词对比出图，厚涂和赛璐璐的区别一眼就能看出来"),
        L("B", "https://www.notion.so/demo-jimeng-style-40", kind="link", title="即梦风格词对照表（40 种）"),
        L("C", "厚涂那组好好看，求原提示词", reply=0),
        L("A", "每张图下面都附了原提示词和种子", reply=2),
    ), hours=(13, 18)),
]
