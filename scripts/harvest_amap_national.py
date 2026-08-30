"""高德状元榜全国收割：探测城市 → 并行抓分区页 → 增量写盘。

用法：python scripts/harvest_amap_national.py [--out data/seed/amap-national.json]
城市 slug 为常见拼音名，探测失败的自动跳过；全部请求走本地缓存（7 天 TTL）。
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hhrating.amap import USER_AGENT, parse_amap_html, ranking_url  # noqa: E402
from hhrating.cache import TextCache  # noqa: E402

CITY_NAMES = {
    "beijing": "北京", "shanghai": "上海", "tianjin": "天津", "chongqing": "重庆",
    "guangzhou": "广州", "shenzhen": "深圳", "foshan": "佛山", "dongguan": "东莞",
    "zhuhai": "珠海", "zhongshan": "中山", "huizhou": "惠州", "jiangmen": "江门",
    "zhaoqing": "肇庆", "shantou": "汕头", "chaozhou": "潮州", "jieyang": "揭阳",
    "shanwei": "汕尾", "meizhou": "梅州", "heyuan": "河源", "qingyuan": "清远",
    "shaoguan": "韶关", "yunfu": "云浮", "yangjiang": "阳江", "maoming": "茂名",
    "zhanjiang": "湛江", "chengdu": "成都", "hangzhou": "杭州", "nanjing": "南京",
    "wuhan": "武汉", "xian": "西安", "suzhou": "苏州", "ningbo": "宁波",
    "wuxi": "无锡", "changzhou": "常州", "nantong": "南通", "xuzhou": "徐州",
    "yangzhou": "扬州", "jiaxing": "嘉兴", "shaoxing": "绍兴", "taizhou": "台州",
    "hefei": "合肥", "wuhu": "芜湖", "xiamen": "厦门", "fuzhou": "福州",
    "quanzhou": "泉州", "zhangzhou": "漳州", "jinan": "济南", "qingdao": "青岛",
    "yantai": "烟台", "weifang": "潍坊", "linyi": "临沂", "zhengzhou": "郑州",
    "luoyang": "洛阳", "kaifeng": "开封", "changsha": "长沙", "zhuzhou": "株洲",
    "xiangtan": "湘潭", "nanning": "南宁", "liuzhou": "柳州", "guilin": "桂林",
    "haikou": "海口", "sanya": "三亚", "kunming": "昆明", "dali": "大理",
    "lijiang": "丽江", "guiyang": "贵阳", "zunyi": "遵义", "shenyang": "沈阳",
    "dalian": "大连", "anshan": "鞍山", "jilin": "吉林", "changchun": "长春",
    "harbin": "哈尔滨", "qiqihar": "齐齐哈尔", "shijiazhuang": "石家庄",
    "tangshan": "唐山", "baoding": "保定", "handan": "邯郸", "taiyuan": "太原",
    "datong": "大同", "hohhot": "呼和浩特", "huhehaote": "呼和浩特", "baotou": "包头",
    "lanzhou": "兰州", "xining": "西宁", "yinchuan": "银川", "urumqi": "乌鲁木齐",
    "wulumuqi": "乌鲁木齐", "lasa": "拉萨", "nanchang": "南昌", "ganzhou": "赣州",
    "jiujiang": "九江", "shangrao": "上饶", "haerbin": "哈尔滨", "anhui": "合肥",
    "cangzhou": "沧州", "langfang": "廊坊", "weihai": "威海", "zibo": "淄博",
    "taian": "泰安", "jining": "济宁", "heze": "菏泽", "puyang": "濮阳",
    "xingtai": "邢台", "zhangjiakou": "张家口", "chengde": "承德", "rinchang": "日喀则",
    "wenzhou": "温州", "huzhou": "湖州", "jinhua": "金华", "quzhou": "衢州", "zhoushan": "舟山", "lishui": "丽水",
    "zhenjiang": "镇江", "huaian": "淮安", "yancheng": "盐城", "lianyungang": "连云港", "suqian": "宿迁",
    "bengbu": "蚌埠", "maanshan": "马鞍山", "anqing": "安庆", "huainan": "淮南",
    "putian": "莆田", "longyan": "龙岩", "sanming": "三明", "nanping": "南平",
    "jingdezhen": "景德镇", "pingxiang": "萍乡", "xinyu": "新余", "yingtan": "鹰潭", "jian": "吉安",
    "xinxiang": "新乡", "anyang": "安阳", "jiaozuo": "焦作", "xuchang": "许昌", "luohe": "漯河",
    "nanyang_hn": "南阳", "shangqiu": "商丘", "xinyang_hn": "信阳", "zhumadian": "驻马店", "sanmenxia": "三门峡",
    "yichang": "宜昌", "xiangyang": "襄阳", "jingzhou_hb": "荆州", "huangshi": "黄石", "shiyan": "十堰",
    "hengyang": "衡阳", "yueyang": "岳阳", "changde": "常德", "chenzhou": "郴州", "shaoyang": "邵阳",
    "yiyang_hn": "益阳", "huaihua": "怀化", "zhangjiajie_hn": "张家界",
    "beihai": "北海", "qinzhou": "钦州", "guigang": "贵港", "baise": "百色", "hechi": "河池", "danzhou": "儋州",
    "mianyang": "绵阳", "leshan": "乐山", "luzhou_sc": "泸州", "yibin": "宜宾", "nanchong": "南充",
    "deyang": "德阳", "dazhou": "达州", "neijiang": "内江", "suining_sc": "遂宁", "meishan": "眉山",
    "ziyang": "资阳", "yaan": "雅安", "bazhong": "巴中", "guangyuan": "广元", "guangan": "广安",
    "yuxi": "玉溪", "qujing": "曲靖", "puer": "普洱",
    "liupanshui": "六盘水", "anshun": "安顺", "bijie": "毕节", "tongren": "铜仁",
    "jinzhong_sx": "晋中", "luliang": "吕梁", "changzhi_sx": "长治", "jincheng": "晋城",
    "linfen": "临汾", "yuncheng_sx": "运城", "shuozhou": "朔州", "yangquan": "阳泉",
    "xianyang": "咸阳", "baoji": "宝鸡", "weinan": "渭南", "hanzhong": "汉中",
    "ankang": "安康", "shangluo": "商洛", "yulin_sn": "榆林",
    "tianshui": "天水", "jiuquan": "酒泉", "zhangye": "张掖", "wuwei": "武威", "pingliang": "平凉",
    "wuzhong_nx": "吴忠", "zhongwei": "中卫", "guyuan_nx": "固原", "shizuishan": "石嘴山", "haidong": "海东",
    "kashi": "喀什", "korla": "库尔勒", "turpan": "吐鲁番", "yining": "伊宁", "aletai": "阿勒泰",
    "jinzhou_ln": "锦州", "yingkou": "营口", "fushun_ln": "抚顺", "chaoyang_ln": "朝阳", "dandong": "丹东",
    "huludao": "葫芦岛", "panjin": "盘锦", "liaoyang_ln": "辽阳", "tieling": "铁岭", "benxi": "本溪", "fuxin": "阜新",
    "songyuan": "松原", "siping": "四平", "tonghua": "通化", "baicheng": "白城", "yanji": "延吉",
    "daqing": "大庆", "mudanjiang": "牡丹江", "jiamusi": "佳木斯", "jixi_hlj": "鸡西",
    "shuangyashan": "双鸭山", "qitaihe": "七台河", "heihe": "黑河", "hengshui": "衡水",
    "dezhou_sd": "德州", "liaocheng": "聊城", "rizhao": "日照", "dongying": "东营", "binzhou_sd": "滨州",
    "xishuangbanna": "西双版纳", "wenshan_yn": "文山", "honghe_yn": "红河", "dehong": "德宏",
    "nujiang": "怒江", "diqing": "迪庆", "liangshan": "凉山", "ganzi": "甘孜", "aba": "阿坝",
    "enshi": "恩施", "xiangxi": "湘西", "yanbian": "延边", "linxia": "临夏", "gannan": "甘南",
    "changdu": "昌都", "linzhi": "林芝", "shannan": "山南", "naqu": "那曲",
    "chizhou": "池州", "tongling": "铜陵", "huangshan": "黄山", "liuan": "六安", "bozhou": "亳州",
    "fuyang_ah": "阜阳", "longnan": "陇南", "dingxi": "定西", "jiayuguan": "嘉峪关", "jinchang": "金昌",
    "kelamayi": "克拉玛依", "hami": "哈密", "tongliao": "通辽", "chifeng": "赤峰",
    "ordos": "鄂尔多斯", "eerduosi": "鄂尔多斯", "wuhai": "乌海", "bayannur": "巴彦淖尔",
    "hulunbuir": "呼伦贝尔", "hongkong": "香港", "aomen": "澳门", "taibei": "台北",
    "pingdingshan": "平顶山", "hebi": "鹤壁", "zhoukou": "周口", "kaifeng_hn": "开封",
    "meizhou_gd": "梅州", "yancheng": "盐城",
}


CACHE = TextCache(Path(__file__).parent.parent / "data" / "cache" / "text-cache.sqlite3")
opener = urllib.request.build_opener(urllib.request.ProxyHandler({})).open


def get(url: str) -> str | None:
    html = CACHE.get(url)
    if html is not None:
        return html
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with opener(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
        CACHE.put(url, html)
        return html
    except Exception:
        return None


def probe_city(slug: str) -> list[str]:
    html = get(f"https://www.amap.com/ranking/{slug}/food")
    if not html:
        return []
    return sorted(set(re.findall(rf"/ranking/{slug}/food/(\d+)", html)))


def harvest_district(slug: str, code: str) -> list[dict]:
    city = CITY_NAMES[slug]
    url = ranking_url(slug, code)
    html = get(url)
    if not html:
        return []
    return [
        {
            "name": it["name"],
            "city": city,
            "address": it.get("address"),
            "source": url,
            "list_name": "高德状元榜·美食（必吃美食）",
        }
        for it in parse_amap_html(html)
        if it.get("name")
    ]


def main() -> None:
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else 999
    out_path = Path(__file__).parent.parent / "data" / "seed" / "amap-national.json"
    slugs = [s for s in CITY_NAMES if s not in
             ("guangzhou", "shenzhen", "foshan", "dongguan", "zhuhai", "zhongshan",
              "huizhou", "jiangmen", "zhaoqing", "shantou", "chaozhou", "jieyang",
              "shanwei", "meizhou", "heyuan", "qingyuan", "shaoguan", "yunfu",
              "yangjiang", "maoming", "zhanjiang", "huhehaote", "wulumuqi", "haerbin", "anhui")][:limit]

    print(f"探测 {len(slugs)} 个城市 …", flush=True)
    city_districts: dict[str, list[str]] = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(probe_city, s): s for s in slugs}
        for fut in as_completed(futures):
            slug = futures[fut]
            codes = fut.result()
            if codes:
                city_districts[slug] = codes

    total_pages = sum(len(v) for v in city_districts.values())
    print(f"{len(city_districts)} 个城市有榜单，共 {total_pages} 个分区页，并行抓取 …", flush=True)

    entries: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {}
        for slug, codes in city_districts.items():
            for code in codes:
                futures[pool.submit(harvest_district, slug, code)] = (slug, code)
        for fut in as_completed(futures):
            slug, code = futures[fut]
            try:
                items = fut.result()
                entries.extend(items)
            except Exception as exc:
                print(f"[失败] {slug}/{code}: {exc}")
            done += 1
            if done % 20 == 0:
                print(f"  进度 {done}/{total_pages}，已收割 {len(entries)} 家", flush=True)

    out_path.write_text(
        json.dumps({"schema_version": 1, "source": "amap.com 状元榜·美食（全国收割）", "entries": entries},
                   ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    per_city: dict[str, int] = {}
    for e in entries:
        per_city[e["city"]] = per_city.get(e["city"], 0) + 1
    print("完成：", dict(sorted(per_city.items(), key=lambda x: -x[1])[:25]), flush=True)
    print(f"合计 {len(entries)} 家 → {out_path.name}", flush=True)


if __name__ == "__main__":
    main()
