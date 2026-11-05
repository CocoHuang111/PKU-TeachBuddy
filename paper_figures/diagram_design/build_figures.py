"""Build the two editable diagram-design HTML figure sources.

The HTML files are the canonical figure sources; SVG, PNG and PDF are exports.
"""

from html import escape
from pathlib import Path


OUT = Path(__file__).resolve().parent
PAPER = "#fbfaf8"
INK = "#252d35"
MUTED = "#566574"
SOFT = "#6a7782"
RED = "#a61b1b"
RED_PALE = "#fff4f2"
LINE = "#c8cfd3"
ZONE = "#f5f5f3"
WHITE = "#ffffff"
FONT = "PingFang SC, Noto Sans SC, Microsoft YaHei, sans-serif"


def text(x, y, value, size=14, fill=INK, weight=400, anchor="start", extra=""):
    return (f'<text x="{x}" y="{y}" fill="{fill}" font-size="{size}" '
            f'font-weight="{weight}" text-anchor="{anchor}" {extra}>{escape(value)}</text>')


def node(x, y, w, h, title, lines=(), *, focal=False):
    fill = RED_PALE if focal else WHITE
    stroke = RED if focal else LINE
    out = [f'<g class="diagram-node">',
           f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="7" fill="{fill}" stroke="{stroke}" stroke-width="{1.7 if focal else 1.2}"/>']
    if focal:
        out.append(f'<rect x="{x}" y="{y}" width="5" height="{h}" rx="2" fill="{RED}"/>')
    title_y = y + (34 if h >= 88 else 23)
    out.append(text(x + 20, title_y, title, 17, RED if focal else INK, 600))
    for i, line in enumerate(lines):
        out.append(text(x + 20, title_y + (26 if h >= 88 else 20) + 20 * i, line, 12.5, MUTED))
    out.append('</g>')
    return '\n'.join(out)


def arrow(d, *, accent=False, dashed=False):
    color = RED if accent else MUTED
    marker = 'arrow-red' if accent else 'arrow-muted'
    dash = ' stroke-dasharray="6 5"' if dashed else ''
    return f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{1.7 if accent else 1.4}" stroke-linecap="round" stroke-linejoin="round" marker-end="url(#{marker})"{dash}/>'


def zone_label(x, y, index, label):
    return (text(x, y, index, 12, RED, 700, extra='letter-spacing="1.2"') + '\n' +
            text(x + 34, y, label, 13, SOFT, 600))


def wrap(slug, title, description, svg_body):
    svg = f'''<svg viewBox="0 0 1120 792" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="{slug}-title {slug}-desc">
  <title id="{slug}-title">{escape(title)}</title>
  <desc id="{slug}-desc">{escape(description)}</desc>
  <defs>
    <marker id="arrow-muted" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto"><polygon points="0 0, 9 3.5, 0 7" fill="{MUTED}"/></marker>
    <marker id="arrow-red" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto"><polygon points="0 0, 9 3.5, 0 7" fill="{RED}"/></marker>
  </defs>
  <rect width="1120" height="792" fill="{PAPER}"/>
  {svg_body}
</svg>'''
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(title)}｜TeachBuddy</title>
<style>
  *,*::before,*::after{{box-sizing:border-box}}
  body{{margin:0;padding:36px 28px;background:{PAPER};color:{INK};font-family:{FONT}}}
  .frame{{max-width:1120px;margin:auto;min-width:0}}
  .eyebrow{{margin:0 0 7px;color:{RED};font-size:12px;font-weight:700;letter-spacing:.11em}}
  h1{{margin:0 0 24px;font-size:26px;font-weight:600;line-height:1.35}}
  .diagram-container{{width:100%;overflow-x:auto}}
  svg{{display:block;width:100%;min-width:1120px;font-family:{FONT}}}
  @media print{{body{{padding:0}}.diagram-container{{overflow-x:visible}}svg{{min-width:0}}}}
</style>
</head>
<body><main class="frame">
<p class="eyebrow">TEACHBUDDY · 论文插图</p>
<h1>{escape(title)}</h1>
<div class="diagram-container">{svg}</div>
</main></body>
</html>
'''


def architecture():
    parts = []
    parts += [zone_label(80, 72, '01', '交互与任务调度'),
              zone_label(80, 288, '02', '智能服务'),
              zone_label(80, 536, '03', '共享底座')]
    for y in (88, 304, 552):
        parts.append(f'<line x1="80" y1="{y}" x2="1040" y2="{y}" stroke="{LINE}" stroke-width="1"/>')
    # Draw all connectors before the nodes.
    parts += [
        arrow('M 336,156 H 432'),
        arrow('M 688,156 H 784'),
        arrow('M 492,200 V 252 Q 492,260 484,260 H 216 Q 208,260 208,268 V 320'),
        arrow('M 560,200 V 320'),
        arrow('M 912,200 V 320'),
        arrow('M 208,432 V 560'),
        arrow('M 560,432 V 560'),
        arrow('M 912,432 V 560'),
        arrow('M 432,390 H 336', accent=True, dashed=True),
    ]
    parts.append(f'<rect x="352" y="366" width="64" height="18" rx="2" fill="{PAPER}"/>')
    parts.append(text(384, 379, '报告复用', 10.5, RED, 600, 'middle'))
    parts += [
        node(80, 112, 256, 88, '教师端 · Vue 3', ('四种问答 / 视频提交 / 大纲修订',)),
        node(432, 112, 256, 88, '任务服务 · FastAPI', ('身份、文件、会话与任务状态',), focal=True),
        node(784, 112, 256, 88, '后台任务', ('视频评估 / 大纲优化 / 邮件通知',)),
        node(80, 320, 256, 112, '教学智能问答', ('模式路由、分类检索', '证据化回答与私有资料调用')),
        node(432, 320, 256, 112, '课堂教学评估', ('多模态证据、五维判断', 'GB 综合评分与报告生成')),
        node(784, 320, 256, 112, '课程大纲优化', ('原文微调 / 框架重构', '生成结果校验与人工审阅')),
    ]
    parts += [
        '<g class="diagram-node">',
        f'<rect x="80" y="560" width="960" height="136" rx="7" fill="{WHITE}" stroke="{LINE}" stroke-width="1.2"/>',
        f'<line x1="400" y1="586" x2="400" y2="678" stroke="{LINE}"/>',
        f'<line x1="720" y1="586" x2="720" y2="678" stroke="{LINE}"/>',
        text(100, 591, '公共教学知识库', 15, INK, 600),
        text(100, 617, '分类语料、Chroma 向量检索', 12.5, MUTED),
        text(100, 639, '引用定位与原文回读', 12.5, MUTED),
        text(420, 591, '共享模型与教学规则', 15, INK, 600),
        text(420, 617, 'LLM / VLM / ASR / Embedding', 12.5, MUTED),
        text(420, 639, '五维指标与评分规则', 12.5, MUTED),
        text(740, 591, '业务数据与私有索引', 15, INK, 600),
        text(740, 617, 'PostgreSQL：用户、任务、会话', 12.5, MUTED),
        text(740, 639, '附件与本人评估报告摘要', 12.5, MUTED),
        '</g>',
        f'<line x1="80" y1="734" x2="1040" y2="734" stroke="{LINE}"/>',
        text(80, 759, '主链路', 11, SOFT),
        f'<line x1="136" y1="755" x2="180" y2="755" stroke="{MUTED}" stroke-width="1.4" marker-end="url(#arrow-muted)"/>',
        text(222, 759, '报告摘要写入本人私有索引；教师选择后用于问答', 11, SOFT),
        f'<line x1="480" y1="755" x2="528" y2="755" stroke="{RED}" stroke-width="1.4" stroke-dasharray="6 5" marker-end="url(#arrow-red)"/>',
    ]
    return wrap('teachbuddy-architecture', 'TeachBuddy 系统架构图',
                '教师端经 FastAPI 和后台任务进入教学问答、课堂评估与课程大纲优化服务。三项服务共用知识、模型和业务数据底座；评估报告摘要可由教师选择后用于问答。', '\n'.join(parts))


def evidence():
    parts = []
    parts += [zone_label(80, 52, '01', '输入与多模态采集'),
              zone_label(80, 360, '02', '证据结构化'),
              zone_label(80, 508, '03', '判断、评分与输出')]
    for y in (68, 376, 524):
        parts.append(f'<line x1="80" y1="{y}" x2="1040" y2="{y}" stroke="{LINE}" stroke-width="1"/>')
    parts += [
        arrow('M 224,148 V 212'),
        arrow('M 560,148 V 212'),
        arrow('M 896,148 V 212'),
        arrow('M 224,308 V 340 Q 224,348 232,348 H 400 Q 408,348 408,356 V 388'),
        arrow('M 560,308 V 388'),
        arrow('M 896,308 V 340 Q 896,348 888,348 H 720 Q 712,348 712,356 V 388'),
        arrow('M 448,476 V 500 Q 448,508 440,508 H 328 Q 320,508 320,516 V 536'),
        arrow('M 672,476 V 500 Q 672,508 680,508 H 792 Q 800,508 800,516 V 536'),
        arrow('M 480,580 H 640', accent=True),
        arrow('M 368,624 V 642 Q 368,650 376,650 H 492 Q 500,650 500,658 V 676'),
        arrow('M 752,624 V 642 Q 752,650 744,650 H 628 Q 620,650 620,658 V 676', accent=True),
    ]
    parts += [
        node(80, 92, 960, 56, '课堂视频与可选教学材料', ('讲稿 / 逐字稿、课程大纲、课件可作为补充输入',), focal=True),
        node(80, 212, 288, 96, '语言文本', ('FFmpeg 抽音；ASR 转写', '有讲稿时以讲稿替代转写')),
        node(416, 212, 288, 96, '声音与时间轴', ('响度、基频、停顿、语速', '转写时间戳与课堂节奏')),
        node(752, 212, 288, 96, '画面与课程材料', ('稀疏帧 VLM 标注；密集帧变化', '课件 / 大纲解析')),
        node(344, 388, 432, 88, '结构化课堂证据包', ('七类、69 个字段按可用模态提取', '原始观察与教学判断分离；缺失不补零')),
        node(160, 536, 320, 88, '五维教学判断', ('25 项二级指标与证据依据', '证据不足标记“未评估”')),
        node(640, 536, 320, 88, 'GB 综合评分', ('客观特征 + 五维判断结果', '线上五分类模型生成综合分')),
        node(360, 676, 400, 56, '可追溯评估报告', ('维度结果、综合分、指标依据与建议',), focal=True),
        f'<line x1="80" y1="752" x2="1040" y2="752" stroke="{LINE}"/>',
        text(80, 776, '报告摘要可写入本人私有索引，由教师选择后用于后续问答。', 11, SOFT),
    ]
    return wrap('classroom-evidence', '课堂证据处理流程图',
                '课堂视频和可选材料分路形成语言、声音时间轴和画面材料信息，再汇聚为结构化证据包，进入五维教学判断和 GB 综合评分，生成可追溯报告。', '\n'.join(parts))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'teachbuddy_architecture.html').write_text(architecture(), encoding='utf-8')
    (OUT / 'classroom_evidence_flow.html').write_text(evidence(), encoding='utf-8')


if __name__ == '__main__':
    main()
