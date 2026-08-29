# HHRating · 美食点评指数资料库

HHRating（Huì Huǒ Rating）是一个美食点评资料库：收集、整理并分析市场上各家饭店的公开网络信息，
以一个 **5 位指数** 的形式发布评价结果。

## 指数含义

指数形如 `86752`，共 5 位，每一位取值 **1–9，由差到好**：

| 位次 | 含义 | 说明 |
|------|------|------|
| 第 1 位 | 综合得分 | 其余四维的加权综合 |
| 第 2 位 | 名人推荐值 | 名人/名厨推荐、权威奖项（米其林、黑珍珠等）、媒体报道 |
| 第 3 位 | 人气度 | 点评数、社交媒体热度 |
| 第 4 位 | 网上得分 | 点评平台公开评分 |
| 第 5 位 | 出现时间 | 历史越悠久，分值越高 |

示例：`86752` = 综合 8 / 名人推荐 6 / 人气 7 / 网上得分 5 / 年代 2。

评分标准与换算规则见 [`docs/index-spec.md`](docs/index-spec.md)。

## 数据来源

所有分值均由**公开网络资料统计**产生（点评平台评分与点评数、奖项名录、媒体报道、社媒热度、
店铺创立年份等），每条记录附带数据快照日期与来源链接。首次发布数据通过联网调研采集，
后续可用内置采集器（支持本地代理）辅助更新。

> 免责声明：种子数据来自公开网络的近似统计，仅用于研究与演示；如需商用请自行核实。

## 快速开始

```bash
# 安装开发依赖
python -m pip install -e . pytest

# 运行测试
python -m pytest

# 导入种子数据并计算指数
python -m hhrating import data/seed/restaurants.json
python -m hhrating score

# 查看榜单 / 详情 / 发布
python -m hhrating list
python -m hhrating show quanjude
python -m hhrating publish
```

## 项目结构

```
├── docs/            # 评分标准、数据字典
├── src/hhrating/    # 核心包（模型、评分、采集、CLI、发布）
├── tests/           # pytest 测试
├── data/            # 种子数据与数据库文件
└── published/       # 发布产物（JSON / Markdown / HTML）
```

## 开发约定

- 采用 superpowers 工作流：先写规范 → 测试驱动开发 → 小步提交（Conventional Commits）。
- 遵循 PEP 8 / PEP 621（pyproject.toml）标准，零运行时第三方依赖。
- 每次修改或新增内容都必须提交到本地 Git 仓库。
