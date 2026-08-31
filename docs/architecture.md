# HHRating 系统架构与数据管线

> 版本 1.2 · 2026-08-31 · 本文档描述 HHRating 的采集/评分/发布全链路设计与运维方法。

## 1. 总体架构

```
┌──────────────────────────── 采集层（全部代码化，可并行） ───────────────────────────┐
│ So360Collector   360 搜索（主引擎，直链+跳转解析，Cookie 会话）                      │
│ SogouCollector   搜狗（中文备援，/link 还原）                                        │
│ BingCollector / DuckDuckGoCollector（备援，CJK 多词能力弱）                          │
│ AmapCollector    高德"状元榜·美食"分区榜（JSON-LD，服务端渲染）                      │
│ Dianping 解析器  m 站人气排行页（shopName/branchName JSON）                         │
│ discovery 模块   名录文章搜索→抓取→店名提取（后缀白名单+噪声拒绝）                    │
│ 引擎链 FallbackCollector：按序尝试，首个非空结果胜出，限流自动冷却                    │
├──────────────────────────── 支撑层 ─────────────────────────────────────────────┤
│ cache.TextCache  网页正文缓存（SQLite，仅存解码文本，7 天 TTL，线程安全）             │
│ storage.Database JSON 文档库（锁文件互斥 + 临时文件原子替换；bulk_upsert/remove_many）│
│ 代理策略：--proxy 显式指定；默认显式直连（绕过系统代理劫持）                          │
├──────────────────────────── 评分与发布层 ────────────────────────────────────────┤
│ batch.classify_all_cuisines  待分类菜系推断（店名+备注，最长关键词，不覆盖已有）     │
│ scoring.compute_index  五位指数（规范 docs/index-spec.md v1.1 的代码化）             │
│ publish                四件产物：hhrating-index.json / index.md / index.html /       │
│                        explorer.html（全字段搜索/筛选/排序/详情，零依赖单文件）       │
│ analysis.summarize     覆盖率/分布/TOP 榜统计                                       │
└────────────────────────────────────────────────────────────────────────────────┘
```

## 2. 数据源清单与现状（2026-08-30）

| 数据源 | 接入方式 | 产出 | 状态 |
|--------|---------|------|------|
| 高德状元榜·美食 | `scripts/harvest_amap_national.py`（全国 241 slug 探测 + 12 线程） | ~5500 家（992 页已穷尽） | ✅ 已收割 |
| 搜索摘要 | `scripts/snippet_harvest.py`（4 引擎线程轮转 + 限流冷却） | ~800 家/多轮 | ✅ 可重复跑 |
| 名录文章 | `scripts/article_harvest.py`（360 跳转解析 → 抓文 → 提取） | ~1500 家 | ✅ 可重复跑 |
| 大众点评 m 站排行页 | `hhrating/dianping.py`（解析器就绪） | 待 URL 发现方案 | ⏸ 搜索引擎不收录其 URL |
| OpenStreetMap Overpass | `data/seed/osm-batch1.json` 样例 + §6 网格收割法 | 首批 18 家 | ⏸ 直连被 406 拦截 |
| Wikidata SPARQL | query.wikidata.org | 未接入 | ⏸ SSL 被墙 |

## 3. 关键设计决策

1. **诚实优先**：所有记录带 `sources`（≥1 条来源 URL）与 `data_date` 快照日期；
   提取不到的指标置空（评分记 0），绝不臆测；自动采集的记录在 `notes` 标注
   "未经人工核实"。
2. **去重**：`name_key` 为分店级全名（全角括号折算半角、去空白）；`normalize_name`
   去除括号注记用于奖项匹配。名录导入与搜索导入互不覆盖已有人工数据。
3. **质量门**：导入时校验（评分范围、年份、奖项枚举、来源必填）；事后审计脚本
   扫描噪声名/平分评分/不可能年份并删除留痕（`notes` 记录"人工复核"字样）。
4. **性能**：`bulk_upsert`/`remove_many`/score 单次写盘——逐条全文件序列化在
   万级记录下会触发 O(n²) I/O 直至进程崩溃（已发生并修复）。
5. **并发**：写库经锁文件互斥；长时间运行的收割器必须在**收割结束后**重新加载
   数据库再导入（避免旧快照丢失更新——已发生并修复）。

## 4. 菜系分类管线

采集入库时大量记录的 `cuisine` 只能记占位「待分类」。分类分两段，不要混用：

1. **采集期** `guess_cuisine(texts)`：扫搜索标题/摘要，`CUISINE_KEYWORDS` 首次命中即返回该词本身，否则「待分类」。这是收割时的弱信号，不回写已有菜系。
2. **事后** `hhrating classify`（`classify_all_cuisines`）：只处理 `cuisine` 为空或「待分类」的记录；把店名与 `notes` 拼成 haystack，按关键词长度降序匹配到规范菜系名（如「韩式」→「韩国料理」、「冰室」→「茶餐厅」）。

规则：

- 最长关键词优先；同长度保持词表原顺序。
- 已有菜系绝不覆盖。
- 店名与备注都无线索则保持「待分类」（知名品牌如「海底捞」不强判）。
- 写盘走 `bulk_upsert` 一次，避免万级记录逐条序列化。

```bash
python -m hhrating classify
```

## 5. 指数与发布

- 评分规范唯一依据：`docs/index-spec.md`（v1.1）。五位指数每位 1–9（0=暂无数据），
  综合位要求至少两个维度可得（防单维度放大）。
- 发布产物不可变快照：`generated_at` + `spec_version` 写入产物头。
- explorer.html 为零依赖单文件应用，可直接双击或托管为静态站点
  （GitHub Pages：仓库设置 → Pages → 选择 main 分支 /published 目录）。

## 6. 续采手册（冲 1 万条的操作路线）

### 6.1 常规增量（引擎未封禁时）

```bash
python scripts/snippet_harvest.py --limit 400        # 摘要收割（4 引擎并行，约 30-40 分钟）
python scripts/article_harvest.py --batch-cities 10  # 名录文章收割（360 跳转解析）
python scripts/harvest_amap_national.py              # 高德新城市（新榜上线时）
python -m hhrating fill --city 广州 --proxy http://127.0.0.1:8009   # 补采指标
python -m hhrating classify
python -m hhrating score && python -m hhrating publish && python -m hhrating stats
```

### 6.2 Overpass 网格收割法（代理恢复后自动化 / 当前用 WebFetch 人工转录）

Overpass GET 模板（bbox 按城市网格切分，单格 ≤300 条保证转录完整）：

```
https://overpass-api.de/api/interpreter?data=[out:json][timeout:50];
(node[amenity=restaurant][name](<lat1>,<lon1>,<lat2>,<lon2>);
 way[amenity=restaurant][name](<lat1>,<lon1>,<lat2>,<lon2>););out tags 300;
```

- 直连被 406 拦截时的替代通道：WebFetch 该 URL（harness 出口可达），
  要求"逗号分隔输出所有 tags.name"；每格 ~100-300 条。
- 广州全域约 20-40 格、深圳约 15 格、佛山/东莞/珠海/中山/惠州/江门/肇庆各 8-15 格。
- 转录结果存 `data/seed/osm-*.json`（结构同 osm-batch1.json）后 `import_list_records` 导入。

### 6.3 限流与封锁应对

| 症状 | 处置 |
|------|------|
| 360/搜狗返回空或 403/500 | 停 1-2 小时（引擎冷却）；snippet_harvest 内置 45 秒自动冷却 |
| Overpass 406/500 | 换镜像（kumi/mail.ru/osm.jp）或经代理/WebFetch 通道 |
| 系统代理劫持 | 收割器已显式 `ProxyHandler({})` 直连，不受注册表代理影响 |

## 7. 已知限制

- 搜索摘要/名录文章自动提取的店名存在少量噪声（已多轮过滤+审计清理，
  残留率约 1-2%），记录 `notes` 均标注"未经人工核实"。
- 自动收割记录的指标（评分/点评数/年份）覆盖率低，依赖 `fill`/`batch`
  随引擎配额逐步补齐。
- 中文拼音排序未实现（`list_all` 按 id 排序；发布层按综合分排序）。
- Python 3.12.0 在高并发 SSL 下偶发段错误（已将文章收割并发降为 2；
  根治需升级 Python 补丁版本）。
