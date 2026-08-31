# HHRating 数据字典（v1.0）

`restaurants.json` 数据库（顶层为文档库，`data/seed/restaurants.json` 为种子导入源）的
字段定义。所有时间使用 ISO 8601（`YYYY-MM-DD`），所有 ID 使用小写 kebab-case slug。

## 顶层结构

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `schema_version` | int | 是 | 数据库结构版本，当前 `1` |
| `restaurants` | list[object] | 是 | 饭店记录数组 |

## 饭店记录（Restaurant）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | str | 是 | 唯一 slug；人工整理记录用语义化 kebab-case（如 `quanjude-qianmen`）；自动批量采集记录为 `{城市前缀}-{店名哈希8位}`（如 `gz-1a2b3c4d`），由店名确定性生成 |
| `name` | str | 是 | 中文名称 |
| `name_en` | str | 否 | 英文名 |
| `city` | str | 是 | 所在城市 |
| `cuisine` | str | 是 | 菜系/品类，如 `烤鸭`、`本帮菜`；自动采集可先记占位 `待分类`，事后由 `hhrating classify` 按店名/备注关键词推断 |
| `branch` | str | 否 | 分店名/地址描述 |
| `address` | str | 否 | 详细地址（如"广州市荔湾区第十甫路20号"） |
| `metrics` | object | 是 | 原始指标，见下表 |
| `sources` | list[str] | 是 | 数据来源 URL 列表（至少 1 条） |
| `data_date` | str | 是 | 数据快照日期 |
| `index` | str \| null | 否 | 计算得到的 5 位指数 |
| `index_detail` | object \| null | 否 | 逐位明细 `{overall, celebrity, popularity, online, age}` |
| `notes` | str | 否 | 备注 |

## 指标对象（Metrics）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `online_rating` | float 0–5 | 否 | 跨平台归一化平均评分（10 分制平台折算为 5 分制） |
| `review_count` | int ≥ 0 | 否 | 全网点评总数 |
| `social_mentions` | int ≥ 0 | 否 | 社交媒体可统计热度条目数 |
| `awards` | list[str] | 否 | 奖项记录，如 `michelin_1_star`、`blackpearl_1_diamond`、`bib_gourmand`、`michelin_plate`，可带年份后缀 `michelin_1_star@2025` |
| `celebrity_endorsements` | list[str] | 否 | 名人实名推荐记录，格式 `姓名：说明` |
| `media_features` | list[str] | 否 | 权威媒体报道，如 `舌尖上的中国第一季` |
| `master_chef` | bool | 否 | 是否有国家级/省部级烹饪大师坐镇 |
| `founded_year` | int | 否 | 创立年份 |

## 采集来源标记

- 人工整理记录：`notes` 写明依据与快照时间，`sources` 为直接依据页面。
- 自动批量采集（`hhrating batch`）：`notes` 标注"自动采集…未经人工核实"，
  并记录搜索引擎给出的信号候选（评分/年份/点评数候选值）；
  `sources` 为检索结果链接（可能是搜索引擎跳转链）。
  同名（分店级全名）记录不会被自动采集覆盖。
- 菜系事后分类（`hhrating classify`）：只改 `cuisine` 为空或 `待分类` 的记录，
  用店名与 `notes` 中的最长关键词推断规范菜系；无线索不强判，已有菜系不覆盖。

## 奖项枚举

`michelin_3_star` / `michelin_2_star` / `michelin_1_star` / `bib_gourmand` / `michelin_plate` /
`blackpearl_3_diamond` / `blackpearl_2_diamond` / `blackpearl_1_diamond`

未知枚举值在导入时告警并在评分时忽略。
