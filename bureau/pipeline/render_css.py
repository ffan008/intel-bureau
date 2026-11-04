"""HTML 报告样式（深色主题，自包含，不引用任何外部资源）。"""

CSS = """
:root{--bg-0:#03060f;--bg-1:#060b1a;--bg-2:#0a1428;--panel:rgba(10,22,46,.72);--line:rgba(80,200,255,.18);
--line-strong:rgba(80,220,255,.45);--cyan:#22e4ff;--violet:#8b5cff;--magenta:#ff3db8;--amber:#ffb020;--green:#2bff9a;
--red:#ff4d5e;--text-0:#eaf6ff;--text-1:#a9c4dd;--text-2:#6c86a3;--wechat:#2bd96b;--qq:#2aa8ff;--feishu:#4f7cff;--demo:#b48cff}
*{box-sizing:border-box}
html{background:var(--bg-0)}
body{margin:0;color:var(--text-0);font:15px/1.8 "HarmonyOS Sans SC","PingFang SC","Microsoft YaHei UI","Microsoft YaHei",sans-serif;
background:radial-gradient(1200px 600px at 50% -10%,#0a1a3a 0%,var(--bg-0) 70%) fixed;-webkit-font-smoothing:antialiased}
.wrap{max-width:980px;margin:0 auto;padding:40px 24px 64px}
a{color:var(--cyan);text-decoration:none;word-break:break-all}a:hover{text-decoration:underline}
.num,.kpi b,td.n{font-family:"JetBrains Mono",Consolas,monospace;font-variant-numeric:tabular-nums}
.hero{border:1px solid var(--line);background:var(--panel);padding:28px 28px 22px;position:relative;border-radius:4px}
.hero:before,.hero:after{content:"";position:absolute;width:14px;height:14px;border:2px solid var(--cyan)}
.hero:before{left:-1px;top:-1px;border-right:0;border-bottom:0}.hero:after{right:-1px;bottom:-1px;border-left:0;border-top:0}
.brand{font:600 11px/1 Consolas,monospace;letter-spacing:4px;color:var(--text-2)}
h1{margin:10px 0 8px;font-size:26px;line-height:1.4;background:linear-gradient(90deg,var(--cyan),var(--violet));
-webkit-background-clip:text;background-clip:text;color:transparent}
.meta{color:var(--text-1);font-size:13px;margin:0}
.demo-note{margin-top:10px;color:var(--amber);font-size:13px}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-top:18px}
.kpi{border:1px solid var(--line);padding:10px 12px;background:rgba(6,11,26,.6)}
.kpi span{display:block;color:var(--text-2);font-size:12px}.kpi b{font-size:22px;color:var(--cyan)}
section{margin-top:34px}
h2{display:flex;align-items:center;gap:10px;font-size:19px;margin:0 0 14px;padding-bottom:8px;border-bottom:1px solid var(--line)}
h2 span{font:600 12px/1 Consolas,monospace;color:var(--bg-0);background:var(--cyan);padding:4px 6px;border-radius:2px}
h3{font-size:16px;margin:0 0 6px}
ol.j{counter-reset:j;list-style:none;padding:0;margin:0}
ol.j li{counter-increment:j;position:relative;padding:10px 12px 10px 44px;border-left:2px solid var(--violet);
background:rgba(139,92,255,.06);margin-bottom:8px}
ol.j li:before{content:counter(j);position:absolute;left:12px;top:10px;font:700 15px/1.8 Consolas,monospace;color:var(--violet)}
ol.j b{display:block}ol.j small{color:var(--text-1)}
.card{border:1px solid var(--line);background:var(--panel);padding:16px 18px;margin-bottom:12px;border-radius:4px;
border-left:3px solid var(--cyan)}
.card .top{display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}
.rank{font:700 20px/1 Consolas,monospace;color:var(--cyan)}
.hook{color:var(--text-0);margin:6px 0}
.row{display:flex;flex-wrap:wrap;gap:8px 16px;color:var(--text-1);font-size:13px}
.badge{display:inline-block;font-size:12px;padding:0 8px;border-radius:10px;border:1px solid var(--line-strong);color:var(--text-1);line-height:20px}
.t-new{color:var(--cyan);border-color:var(--cyan)}.t-developing{color:var(--amber);border-color:var(--amber)}
.t-repeat{color:var(--text-2);border-color:var(--text-2)}
.risk{color:var(--red);border-color:var(--red)}
.bar{display:inline-block;width:90px;height:6px;background:rgba(255,255,255,.08);vertical-align:middle;margin-left:6px}
.bar i{display:block;height:100%;background:linear-gradient(90deg,var(--cyan),var(--violet))}
.action{margin-top:8px;font-size:13px;color:var(--green)}
article{border:1px solid var(--line);background:var(--panel);padding:18px 20px;margin-bottom:14px;border-radius:4px}
article h4{margin:12px 0 4px;font-size:14px;color:var(--cyan)}
article ol{margin:4px 0;padding-left:22px}
blockquote{margin:8px 0;padding:8px 12px;border-left:3px solid var(--cyan);background:rgba(34,228,255,.05);color:var(--text-1)}
blockquote cite{display:block;font-style:normal;font-size:12px;color:var(--text-2);margin-top:4px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left}
th{color:var(--text-2);font-weight:500}td.n,th.n{text-align:right}
.spark{display:inline-flex;align-items:flex-end;gap:2px;height:22px;vertical-align:middle}
.spark i{width:6px;background:var(--cyan);opacity:.55}.spark i:last-child{background:var(--magenta);opacity:1}
ul.plain{margin:4px 0 12px;padding-left:20px}
.hours{display:flex;align-items:flex-end;gap:3px;height:90px;border-bottom:1px solid var(--line);margin-top:8px}
.hours i{flex:1;background:linear-gradient(180deg,var(--cyan),rgba(34,228,255,.15))}
.hlabels{display:flex;justify-content:space-between;color:var(--text-2);font-size:11px}
.heat{display:grid;grid-template-columns:44px repeat(24,1fr);gap:2px;font-size:10px;color:var(--text-2);margin-top:8px}
.heat i{display:block;height:14px;border-radius:1px}
.muted{color:var(--text-2)}
.pf-wechat{color:var(--wechat)}.pf-qq{color:var(--qq)}.pf-feishu{color:var(--feishu)}.pf-demo{color:var(--demo)}
footer{margin-top:40px;color:var(--text-2);font-size:12px;text-align:center}
@media (max-width:760px){.kpis{grid-template-columns:repeat(2,1fr)}.wrap{padding:20px 14px}}
@media print{body{background:#fff;color:#111}.hero,.card,article{background:#fff}h1{color:#111;-webkit-text-fill-color:#111}}
"""

# ---------------- v2：板块标签页（纯 CSS 切换，:target + 兄弟选择器；:has 做增强） ----------------
CSS_V2 = """
:root{--bg:#070b16;--bg2:#0b1222;--panel:#0f1729;--panel2:#131d33;--line:#22304d;--line2:#30426a;--text:#e6edf7;
--text2:#a7b4c8;--text3:#7385a0;--accent:#38bdf8;--accent2:#a78bfa;--warn:#fbbf24;--red:#f87171;--green:#4ade80}
*{box-sizing:border-box}
html{background:var(--bg);scroll-behavior:auto}
body{margin:0;color:var(--text);background:var(--bg);font:16px/1.8 "HarmonyOS Sans SC","PingFang SC","Microsoft YaHei UI",
"Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none;word-break:break-all}a:hover{text-decoration:underline}
.layout{display:grid;grid-template-columns:232px minmax(0,1fr);min-height:100vh}
nav.tabs{position:sticky;top:0;align-self:start;height:100vh;overflow:auto;padding:22px 12px;background:var(--bg2);
border-right:1px solid var(--line)}
nav.tabs .brand{font:600 12px/1.4 Consolas,monospace;letter-spacing:2px;color:var(--text3);padding:0 10px 14px}
nav.tabs .brand b{display:block;font:600 15px/1.5 "Microsoft YaHei UI",sans-serif;letter-spacing:0;color:var(--text)}
nav.tabs a{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:8px 10px;margin:2px 0;
border-radius:6px;color:var(--text2);font-size:15px;line-height:1.4;border-left:3px solid transparent}
nav.tabs a:hover{background:var(--panel);text-decoration:none;color:var(--text)}
nav.tabs a .n{font:12px/1 Consolas,monospace;color:var(--text3);background:var(--panel);padding:3px 7px;border-radius:9px}
main{min-width:0;padding:26px 40px 64px}
.top{max-width:760px;margin:0 0 18px}
.top h1{font-size:22px;line-height:1.5;margin:0 0 4px}
.top .meta{color:var(--text3);font-size:13px;line-height:1.7;margin:0}
.demo{display:inline-block;margin-top:6px;color:var(--warn);font-size:13px}
.pane{display:none;max-width:760px;scroll-margin-top:16px}
.pane:target{display:block}
#overview{display:block}
.pane:target~#overview{display:none}
.pane>h2{font-size:20px;line-height:1.5;margin:0 0 4px;padding-bottom:8px;border-bottom:1px solid var(--line)}
.pane>h2 .n{font:13px Consolas,monospace;color:var(--text3);margin-left:8px}
.pane .lead{color:var(--text3);font-size:13px;margin:6px 0 16px}
h3{font-size:17px;line-height:1.6;margin:22px 0 8px}
h4{font-size:15px;line-height:1.6;margin:16px 0 6px;color:var(--text2)}
h5,h6{font-size:15px;margin:12px 0 4px;color:var(--text2)}
p{margin:0 0 12px}
ol,ul{margin:4px 0 14px;padding-left:24px}li{margin:4px 0}
blockquote{margin:10px 0;padding:8px 14px;border-left:3px solid var(--accent);background:var(--panel);border-radius:0 6px 6px 0}
blockquote p{margin:0;color:var(--text2);max-height:none}
blockquote cite{display:block;font-style:normal;font-size:12px;color:var(--text3);margin-top:2px}
code{font:13px/1.6 "JetBrains Mono",Consolas,monospace;background:var(--panel2);padding:1px 5px;border-radius:4px}
pre.code{margin:6px 0 14px;padding:12px 14px;background:#050913;border:1px solid var(--line);border-radius:6px;
white-space:pre-wrap;word-break:break-word;font:13px/1.7 "JetBrains Mono",Consolas,monospace;color:#d6e2f2}
pre.code code{background:none;padding:0}
details{margin:8px 0}
details>summary{cursor:pointer;color:var(--accent);font-size:14px;list-style:none}
details>summary::-webkit-details-marker{display:none}
details>summary:before{content:"▸ ";color:var(--text3)}details[open]>summary:before{content:"▾ "}
.tw{overflow-x:auto;margin:6px 0 12px}
table{width:100%;border-collapse:collapse;font-size:14px;line-height:1.6}
th,td{padding:7px 9px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{color:var(--text3);font-weight:500;white-space:nowrap}
td code{white-space:nowrap}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin:12px 0}
.card>h3:first-child,.card>h4:first-child{margin-top:0}
.card.risk{border-left:3px solid var(--warn)}.card.risk.illegal{border-left-color:var(--red)}
.card.group{border-left:3px solid var(--accent2)}
.card.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;background:none;border:0;padding:0}
.card.kpi{margin:0;padding:10px 12px;text-align:center}
.card.kpi p{margin:0}.card.kpi .k{color:var(--text3);font-size:12px}
.card.kpi .v{font:600 22px/1.4 Consolas,monospace;color:var(--accent)}
.card.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;background:none;border:0;padding:0}
.card.thumb{margin:0;padding:10px}
figure{margin:0 0 8px}figure img{display:block;max-width:100%;max-height:420px;border-radius:6px;border:1px solid var(--line)}
.card.thumb figure img{width:100%;height:150px;object-fit:cover}
figcaption{font-size:12px;color:var(--text3);margin-top:4px}
.meta{color:var(--text3);font-size:13px;line-height:1.6}
.muted{color:var(--text3);font-size:14px}
.warn{color:var(--warn);font-size:14px}
.disclaimer{color:var(--text3);font-size:12px;line-height:1.6;border-top:1px dashed var(--line);padding-top:6px;margin-top:10px}
sup.ref{font-size:11px;color:var(--accent);margin-left:1px}
.badge{display:inline-block;font-size:12px;line-height:20px;padding:0 8px;border-radius:10px;border:1px solid var(--line2);
color:var(--text2);margin:0 6px 4px 0}
.badge.risk{color:var(--warn);border-color:#6b5520}.badge.illegal{color:var(--red);border-color:#7a2f35}
details.art{background:var(--panel);border:1px solid var(--line);border-radius:8px;margin:12px 0;scroll-margin-top:16px}
details.art>summary{display:block;padding:14px 16px;color:var(--text)}
details.art>summary:before{content:none}
details.art>summary .seq{font:700 15px Consolas,monospace;color:var(--accent);margin-right:8px}
details.art>summary .t{font-size:17px;font-weight:600}
details.art>summary .h{display:block;color:var(--text2);font-size:14px;margin:4px 0 6px}
details.art>summary .more{font-size:13px;color:var(--accent)}
details.art[open]>summary .more{display:none}
details.art .body{padding:0 18px 16px;border-top:1px solid var(--line)}
details.art:target{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent)}
hr{border:0;border-top:1px solid var(--line);margin:18px 0}
footer{max-width:760px;margin-top:36px;color:var(--text3);font-size:12px}
@media (max-width:900px){.layout{grid-template-columns:1fr}nav.tabs{position:sticky;top:0;z-index:2;height:auto;display:flex;
overflow-x:auto;padding:8px;border-right:0;border-bottom:1px solid var(--line)}nav.tabs .brand{display:none}
nav.tabs a{white-space:nowrap;border-left:0}main{padding:18px 16px 48px}.pane{scroll-margin-top:64px}
.card.kpis{grid-template-columns:repeat(3,1fr)}}
@media print{nav.tabs{display:none}.layout{display:block}.pane,#overview{display:block!important;page-break-before:always}
body,html{background:#fff;color:#111}.card,details.art,blockquote,pre.code{background:#fff;color:#111;border-color:#bbb}
details>*{display:block}a{color:#0645ad}}
"""


def nav_css(keys: list[str]) -> str:
    """当前板块高亮（:has 增强；不支持 :has 的浏览器只是不高亮，切换不受影响）。"""
    rules = []
    for k in keys:
        rules.append(f'.layout:has(#{k}:target,#{k} :target) nav.tabs a[href="#{k}"]')
    hi = ",".join(rules)
    other = ",".join(f"#{k}:target,#{k} :target" for k in keys if k != "overview")
    return (f"{hi}{{background:var(--panel);color:var(--text);border-left-color:var(--accent)}}"
            f'.layout:not(:has({other})) nav.tabs a[href="#overview"]'
            "{background:var(--panel);color:var(--text);border-left-color:var(--accent)}"
            # 指向某篇专题（#a03）时显示它所在的板块；兄弟选择器只处理直接指向板块的情况
            ".panes:has(.pane :target) .pane:not(:has(:target)){display:none!important}"
            ".panes:has(.pane :target) .pane:has(:target){display:block!important}")
