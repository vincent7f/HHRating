# HHRating · 美食点评指数资料库

HHRating（Huì Huǒ Rating）是一个美食点评资料库：收集、整理并分析市场上各家饭店的公开网络信息，
以一个 **5 位指数** 的形式发布评价结果。

## 指数含义

指数形如 `86852`，共 5 位，每一位取值 **1–9，由差到好**（`0` 表示该维度暂无数据）：

| 位次 | 含义 | 说明 |
|------|------|------|
| 第 1 位 | 综合得分 | 其余四维的加权综合（网上 0.35 / 人气 0.25 / 名人 0.20 / 年代 0.20） |
| 第 2 位 | 名人推荐值 | 名人/名厨推荐、权威奖项（米其林、黑珍珠等）、媒体报道 |
| 第 3 位 | 人气度 | 点评数分桶 + 社交媒体热度修正 |
| 第 4 位 | 网上得分 | 点评平台公开评分（0–5 分制分档） |
| 第 5 位 | 出现时间 | 历史越悠久，分值越高（≥120 年记 9） |

示例：`86852` = 综合 8 / 名人推荐 6 / 人气 8 / 网上得分 5 / 年代 2。

评分标准与换算规则见 [`docs/index-spec.md`](docs/index-spec.md)（当前 v1.1），
字段定义见 [`docs/data-dictionary.md`](docs/data-dictionary.md)。

## 首期榜单（2026-08-29）

| 排名 | 指数 | 名称 | 城市 | 菜系 |
|-----:|:-----|:-----|:-----|:-----|
| 1 | `90890` | 四季民福烤鸭店（故宫店） | 北京 | 烤鸭 |
| 2 | `80088` | 点都德（大茶楼店） | 广州 | 粤式茶点 |
| 3 | `79004` | 新荣记（新源南路店） | 北京 | 台州菜 |
| 4 | `73089` | 南翔馒头店（豫园店） | 上海 | 小笼包/点心 |
| 5 | `66059` | 老正兴菜馆（福州路店） | 上海 | 本帮菜 |
| 6 | `65085` | 绿波廊（豫园店） | 上海 | 本帮菜/海派点心 |
| 7 | `64069` | 陶陶居酒家（第十甫路总店） | 广州 | 粤菜茶点 |
| 8 | `63079` | 便宜坊烤鸭店（三元桥店） | 北京 | 焖炉烤鸭 |
| 9 | `63059` | 陈麻婆豆腐（青华路店） | 成都 | 川菜 |
| 10 | `62069` | 全聚德（前门店） | 北京 | 烤鸭 |
| 11 | `52549` | 东来顺饭庄（王府井步行街店） | 北京 | 涮羊肉（清真火锅） |
| 12 | `00008` | 广州酒家（文昌南路总店） | 广州 | 粤菜 |

发布产物：[`published/index.md`](published/index.md)、
[`published/index.html`](published/index.html)（可排序静态页）、
[`published/hhrating-index.json`](published/hhrating-index.json)（机器可读，含逐位明细与来源）。

## 数据来源与免责声明

所有分值均由**公开网络资料统计**产生（大众点评/携程/Trip.com 等平台评分与点评数、
米其林指南与黑珍珠榜单、媒体报道、店铺创立年份等），每条记录附带数据快照日期
（`data_date`）与来源 URL 列表（`sources`）。检索不到的字段如实置空（评分记 0），
不做臆测填充；后续可用内置采集器辅助更新。

> 免责声明：种子数据来自公开网络的近似统计，仅供研究与演示；如需商用请自行核实。

## 快速开始

```bash
# 安装（开发模式）
python -m pip install -e .

# 运行测试（140 个用例）
python -m pytest

# 导入种子数据并计算指数
python -m hhrating import data/seed/restaurants.json
python -m hhrating score

# 日常使用
python -m hhrating list                 # 指数榜单
python -m hhrating list --min 7         # 只看综合 ≥ 7
python -m hhrating show quanjude-qianmen  # 档案详情（逐位说明+来源）
python -m hhrating publish              # 生成 published/ 下三种产物

# 录入新店（指标缺省可只填已知项）
python -m hhrating add --id xx-dian --name XX店 --city 杭州 --cuisine 浙菜 \
    --rating 4.5 --reviews 8000 --founded-year 1985 \
    --award blackpearl_1_diamond --source https://... 

# 联网检索辅助信号（走本地代理；DuckDuckGo 失败自动切换必应）
python -m hhrating collect --query "XX店 大众点评 评分 创立" --proxy http://127.0.0.1:8009
```

## 项目结构

```
├── docs/                # 评分标准（index-spec.md）、数据字典（data-dictionary.md）
├── src/hhrating/        # 核心包
│   ├── models.py        #   数据模型与校验
│   ├── scoring.py       #   五位指数评分引擎（规范的代码化）
│   ├── storage.py       #   JSON 文档库
│   ├── collectors/      #   联网采集器（DuckDuckGo/必应，代理支持，可注入测试）
│   ├── publish.py       #   发布模块（JSON/MD/HTML）
│   └── cli.py           #   命令行接口
├── tests/               # pytest 测试（140 个）
├── data/                # 种子数据（seed/）与数据库文件（restaurants.json）
└── published/           # 发布产物（JSON / Markdown / HTML）
```

## 开发约定

- 采用 superpowers 工作流：先写规范 → 测试驱动开发（TDD）→ 小步提交（Conventional Commits）。
- 遵循 PEP 8 / PEP 621（pyproject.toml）；运行时零第三方依赖，开发依赖仅 pytest。
- 规范修订必须同步更新 `docs/index-spec.md`、`SPEC_VERSION` 与测试，并提升版本号。
- 每次修改或新增内容都必须提交到本地 Git 仓库。
- CI：`.github/workflows/ci.yml` 在 Python 3.10–3.12 上运行测试。
