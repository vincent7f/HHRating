"""大众点评 m 站"人气商户排行"页（/dishes/list/）解析与 URL 提取。

这些页面为服务端渲染，内嵌 JSON 状态（每页 20 家商户，含 shopName/branchName），
是分城市×菜品的人气管名单来源。
"""
from __future__ import annotations

import re

_NAME_RE = re.compile(r'"shopName":"([^"]{1,40})"')
_BRANCH_RE = re.compile(r'"branchName":"([^"]*)"')
_URL_RE = re.compile(r"https?://m\.dianping\.com/dishes/list/[A-Za-z0-9]+")


def _unescape(s: str) -> str:
    return s.replace("\\/", "/").replace("\\u002F", "/")


_NAME_RE = re.compile(r'"shopName":"([^"]{1,40})"')
_BRANCH_RE = re.compile(r'"branchName":"([^"]*)"')


def _unescape(s: str) -> str:
    return s.replace("\\/", "/").replace("\\u002F", "/")


def parse_dianping_dishes(html: str) -> list[dict]:
    """解析排行页 → [{name, branch}]（按页面排名顺序，去空）。

    部分页面把 JSON 以转义字符串内嵌（\\"shopName\\"），先统一反转义；
    shopinfo 对象内含嵌套结构，故以 shopName 定位、向前窗口取 branchName。
    """
    html = html.replace('\\"', '"')
    shops: list[dict] = []
    for m in _NAME_RE.finditer(html):
        name = _unescape(m.group(1)).strip()
        if not name:
            continue
        window = html[max(0, m.start() - 500): m.start()]
        branches = _BRANCH_RE.findall(window)
        branch = _unescape(branches[-1]).strip() if branches else ""
        full = f"{name}（{branch}）" if branch else name
        if all(s["name"] != full for s in shops):
            shops.append({"name": full, "branch": branch})
    return shops


def dianping_urls(text: str) -> list[str]:
    """从搜索结果中提取 m 站排行页 URL（去重、去查询参数）。"""
    urls = []
    for u in _URL_RE.findall(text or ""):
        if u not in urls:
            urls.append(u)
    return urls
