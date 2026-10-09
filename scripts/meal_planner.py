#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦门卡路里精算师 · 配餐组合优化器

输入：麦当劳餐品营养数据（来自 MCP list-nutrition-foods）+ 用户约束
输出：满足「热量上限 / 蛋白质下限 / 预算上限」的 Top3 配餐方案

设计原则：
1. 纯本地计算，不依赖网络，可离线自测（--self-test）
2. 营养/价格数据由调用方注入，脚本本身不写死任何门店或餐品
3. 组合搜索带热量剪枝，避免组合爆炸
"""

import argparse
import itertools
import json
import sys
from typing import Any, Dict, List, Optional

DEFAULT_MAX_ITEMS = 4
DEFAULT_POOL_SIZE = 48
TOP_N = 3

MODES = {
    # 模式名: (说明, 排序键函数权重)
    "cut": "减脂控卡：优先高蛋白密度，热量尽量压在上限内",
    "bulk": "增肌：优先总蛋白最高",
    "cheap": "省钱：优先总价最低",
    "balanced": "均衡：蛋白密度 + 省钱 + 贴近热量预算 三者加权",
}


# --------------------------------------------------------------------------
# 数据规整
# --------------------------------------------------------------------------

NUM_FIELDS = ("energy", "protein", "fat", "carb", "sodium", "price")


def normalize_item(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """把任意来源的一条餐品记录规整成内部格式。缺字段按 0 处理。"""
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or raw.get("mealName") or raw.get("title") or "").strip()
    if not name:
        return None
    item = {
        "code": str(raw.get("code") or raw.get("mealCode") or raw.get("id") or ""),
        "name": name,
        "category": str(raw.get("category") or raw.get("categoryName") or "其他").strip(),
    }
    for f in NUM_FIELDS:
        v = raw.get(f, raw.get({"energy": "kcal"}.get(f, f), 0))
        try:
            item[f] = float(v)
        except (TypeError, ValueError):
            item[f] = 0.0
    return item


def build_pool(items: List[Dict[str, Any]], constraints: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    裁剪候选池：
    - 丢掉单品热量已经超过总上限的（不可能入选）
    - 按「蛋白密度」排序，每类最多保留若干，其余按密度取满 pool_size
    """
    max_cal = float(constraints.get("max_calories") or 0) or float("inf")
    pool = [it for it in items if it["energy"] <= max_cal or max_cal == float("inf")]

    def density(it):
        return (it["protein"] * 10.0) / it["energy"] if it["energy"] > 0 else 0.0

    pool.sort(key=density, reverse=True)

    per_cat = int(constraints.get("per_category") or 12)
    by_cat: Dict[str, int] = {}
    kept: List[Dict[str, Any]] = []
    for it in pool:
        c = it["category"]
        if by_cat.get(c, 0) < per_cat:
            kept.append(it)
            by_cat[c] = by_cat.get(c, 0) + 1
    pool = kept

    size = int(constraints.get("pool_size") or DEFAULT_POOL_SIZE)
    return pool[:size]


# --------------------------------------------------------------------------
# 组合搜索
# --------------------------------------------------------------------------

def feasible(comb: List[Dict[str, Any]], c: Dict[str, Any]) -> bool:
    tot = total(comb)
    if tot["energy"] > float(c.get("max_calories") or float("inf")):
        return False
    min_pro = float(c.get("min_protein") or 0)
    if tot["protein"] + 1e-9 < min_pro:
        return False
    max_price = c.get("max_price")
    if max_price is not None and float(max_price) > 0:
        if tot["price"] > float(max_price) + 1e-9:
            return False
    max_sodium = c.get("max_sodium")
    if max_sodium is not None and float(max_sodium) > 0:
        if tot["sodium"] > float(max_sodium) + 1e-9:
            return False
    must = c.get("must_categories") or []
    cats = {it["category"] for it in comb}
    for m in must:
        if m not in cats:
            return False
    avoid = c.get("avoid") or []
    for it in comb:
        for a in avoid:
            if a and a in it["name"]:
                return False
    return True


def total(comb: List[Dict[str, Any]]) -> Dict[str, float]:
    t = {f: 0.0 for f in NUM_FIELDS}
    for it in comb:
        for f in NUM_FIELDS:
            t[f] += it[f]
    return t


def score(comb: List[Dict[str, Any]], c: Dict[str, Any], mode: str) -> float:
    t = total(comb)
    cal = t["energy"] or 1.0
    max_cal = float(c.get("max_calories") or cal) or 1.0
    density = t["protein"] * 100.0 / cal           # 每 100 kcal 的蛋白
    fit = 1.0 - abs(cal - max_cal * 0.85) / max_cal  # 贴近预算 85% 最理想
    cheap = 1.0 / (1.0 + t["price"])

    if mode == "bulk":
        return t["protein"] * 10.0 + density
    if mode == "cheap":
        return cheap * 100.0 + density * 0.5
    if mode == "cut":
        return density * 2.0 + fit * 10.0
    # balanced
    return density * 1.0 + fit * 8.0 + cheap * 40.0


def search(pool: List[Dict[str, Any]], constraints: Dict[str, Any], mode: str) -> List[Dict[str, Any]]:
    max_items = int(constraints.get("max_items") or DEFAULT_MAX_ITEMS)
    max_cal = float(constraints.get("max_calories") or float("inf"))
    min_pro = float(constraints.get("min_protein") or 0)

    results: List[Dict[str, Any]] = []
    seen = set()
    n = len(pool)

    for size in range(1, max_items + 1):
        for comb in itertools.combinations(range(n), size):
            # 剪枝：先累加热量，超了直接换
            cal = 0.0
            pro = 0.0
            skip = False
            for idx in comb:
                cal += pool[idx]["energy"]
                pro += pool[idx]["protein"]
                if cal > max_cal:
                    skip = True
                    break
            if skip:
                continue
            # 剪枝：剩余容量已无法补到蛋白下限（仅在扩层时近似判断）
            items = [pool[i] for i in comb]
            if not feasible(items, constraints):
                continue
            key = tuple(sorted(it["code"] or it["name"] for it in items))
            if key in seen:
                continue
            seen.add(key)
            results.append({
                "items": items,
                "total": total(items),
                "score": score(items, constraints, mode),
            })

    results.sort(key=lambda r: (-r["score"], r["total"]["energy"]))
    return dedupe_by_nutrition(results)[:TOP_N]


def dedupe_by_nutrition(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    营养指纹去重：营养完全一样时只留最便宜的那个。

    场景：方案「堡+牛奶 ¥29.5」和「堡+牛奶+零度可乐 ¥38.5」的热量/蛋白一模一样，
    后者只是多花 9 块买了 0 kcal 的可乐，对用户没有额外价值却更贵，必须剔除。
    """
    best: Dict[tuple, Dict[str, Any]] = {}
    for r in results:
        t = r["total"]
        fp = (round(t["energy"]), round(t["protein"]), round(t["fat"]), round(t["carb"]))
        cur = best.get(fp)
        if cur is None or (r["total"]["price"], r["score"]) < (cur["total"]["price"], cur["score"]):
            best[fp] = r
    out = list(best.values())
    out.sort(key=lambda r: (-r["score"], r["total"]["energy"]))
    return out


# --------------------------------------------------------------------------
# 输出
# --------------------------------------------------------------------------

def render(plans: List[Dict[str, Any]], mode: str, c: Dict[str, Any]) -> str:
    if not plans:
        return (
            "没找到满足全部约束的方案。建议放宽条件：提高热量上限 / 降低蛋白质下限 / "
            "提高预算，或去掉某个必选品类。\n"
            f"当前约束：{json.dumps(c, ensure_ascii=False)}"
        )

    lines = [f"🍟 配餐模式：{mode}（{MODES.get(mode, '')}）", ""]
    for i, p in enumerate(plans, 1):
        t = p["total"]
        lines.append(f"——— 方案 {i} ———")
        for it in p["items"]:
            lines.append(
                f"  · {it['name']}（{it['category']}）  "
                f"{it['energy']:.0f} kcal / 蛋白 {it['protein']:.0f} g / ¥{it['price']:.1f}"
            )
        lines.append(
            f"  合计：{t['energy']:.0f} kcal ｜ 蛋白 {t['protein']:.0f} g ｜ "
            f"脂肪 {t['fat']:.0f} g ｜ 碳水 {t['carb']:.0f} g ｜ 钠 {t['sodium']:.0f} mg ｜ ¥{t['price']:.1f}"
        )
        rem = float(c.get("max_calories") or 0) - t["energy"]
        if rem > 0:
            lines.append(f"  热量余额：还可再吃 {rem:.0f} kcal")
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 自测
# --------------------------------------------------------------------------

SAMPLE_ITEMS = [
    {"code": "A1", "name": "板烧鸡腿堡", "category": "堡", "price": 21.0, "energy": 404, "protein": 27, "fat": 17, "carb": 37, "sodium": 980},
    {"code": "A2", "name": "吉士蛋麦满分", "category": "堡", "price": 12.5, "energy": 300, "protein": 17, "fat": 13, "carb": 31, "sodium": 720},
    {"code": "A3", "name": "麦香鱼", "category": "堡", "price": 15.0, "energy": 340, "protein": 16, "fat": 14, "carb": 38, "sodium": 640},
    {"code": "B1", "name": "麦乐鸡（5块）", "category": "小食", "price": 12.0, "energy": 220, "protein": 13, "fat": 14, "carb": 10, "sodium": 480},
    {"code": "B2", "name": "玉米杯", "category": "小食", "price": 8.0, "energy": 70, "protein": 2, "fat": 1, "carb": 15, "sodium": 5},
    {"code": "B3", "name": "大薯条", "category": "小食", "price": 13.0, "energy": 430, "protein": 5, "fat": 21, "carb": 56, "sodium": 330},
    {"code": "C1", "name": "零度可乐（中）", "category": "饮料", "price": 9.0, "energy": 0, "protein": 0, "fat": 0, "carb": 0, "sodium": 20},
    {"code": "C2", "name": "鲜煮咖啡（中）", "category": "饮料", "price": 10.0, "energy": 15, "protein": 1, "fat": 0, "carb": 2, "sodium": 10},
    {"code": "C3", "name": "纯牛奶", "category": "饮料", "price": 8.5, "energy": 130, "protein": 8, "fat": 7, "carb": 12, "sodium": 120},
    {"code": "D1", "name": "蔬菜沙拉", "category": "配餐", "price": 11.0, "energy": 35, "protein": 2, "fat": 0, "carb": 6, "sodium": 180},
]


def self_test() -> int:
    """用内置样例验证：约束是否被真正遵守（而不是算个大概）。"""
    print("== 自测 1：约束必须被遵守 ==")
    c = {"max_calories": 600, "min_protein": 30, "max_price": 45, "must_categories": ["堡"], "max_items": 3}
    pool = build_pool([normalize_item(x) for x in SAMPLE_ITEMS], c)
    plans = search(pool, c, "cut")
    assert plans, "600 kcal / 蛋白>=30 / 必含堡 应当有解，实际无解"
    for p in plans:
        t = p["total"]
        assert t["energy"] <= 600 + 1e-6, f"热量超上限：{t}"
        assert t["protein"] >= 30 - 1e-6, f"蛋白未达下限：{t}"
        assert t["price"] <= 45 + 1e-6, f"超预算：{t}"
        cats = {i["category"] for i in p["items"]}
        assert "堡" in cats, f"缺少必选品类：{cats}"
        assert len(p["items"]) <= 3, "超出件数上限"
    print(f"  通过：Top{len(plans)} 全部满足约束")

    print("== 自测 2：不可满足的约束必须返回空，而不是硬凑 ==")
    c2 = {"max_calories": 200, "min_protein": 60, "max_items": 2}
    pool2 = build_pool([normalize_item(x) for x in SAMPLE_ITEMS], c2)
    assert search(pool2, c2, "cut") == [], "200 kcal 内不可能有 60g 蛋白，应无解"
    print("  通过：无解返回空")

    print("== 自测 3：省钱模式单价必须不高于减脂模式 ==")
    c3 = {"max_calories": 700, "min_protein": 20, "must_categories": ["堡"], "max_items": 3}
    pool3 = build_pool([normalize_item(x) for x in SAMPLE_ITEMS], c3)
    cheap = search(pool3, c3, "cheap")[0]["total"]["price"]
    cut = search(pool3, c3, "cut")[0]["total"]["price"]
    assert cheap <= cut + 1e-6, f"cheap({cheap}) 应 <= cut({cut})"
    print(f"  通过：cheap ¥{cheap:.1f} <= cut ¥{cut:.1f}")

    print("== 自测 4：脏数据不能崩（缺字段 / 字符串数字 / 空记录）==")
    dirty = [
        {"name": "缺字段堡", "category": "堡"},
        {"name": "字符串数字", "category": "堡", "energy": "300", "protein": "20", "price": "15.0"},
        {"name": ""},
        "not a dict",
        {"name": "正常项", "category": "小食", "energy": 100, "protein": 3, "price": 6},
    ]
    norm = [x for x in (normalize_item(d) for d in dirty) if x]
    assert len(norm) == 3, f"应过滤掉 2 条脏数据，实际剩 {len(norm)}"
    c4 = {"max_calories": 500, "max_items": 3}
    search(build_pool(norm, c4), c4, "balanced")
    print("  通过：脏数据被过滤且未抛异常")

    print("== 自测 5：营养完全相同的方案只留最便宜的（不能为凑数多卖一瓶零度可乐）==")
    c5 = {"max_calories": 650, "min_protein": 30, "must_categories": ["堡"], "max_items": 3}
    pool5 = build_pool([normalize_item(x) for x in SAMPLE_ITEMS], c5)
    plans5 = search(pool5, c5, "cut")
    fps = [(round(p["total"]["energy"]), round(p["total"]["protein"]),
            round(p["total"]["fat"]), round(p["total"]["carb"])) for p in plans5]
    assert len(fps) == len(set(fps)), f"存在营养重复方案：{fps}"
    # 零度可乐是 0 kcal / ¥9，若出现在方案里说明去重失效
    for p in plans5:
        for it in p["items"]:
            assert it["name"] != "零度可乐（中）", f"0 热量商品不应入选：{[i['name'] for i in p['items']]}"
    print(f"  通过：{len(plans5)} 个方案营养指纹互不相同，且无 0 热量凑数商品")

    print("\n全部自测通过 ✅")
    return 0


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="麦门卡路里精算师 · 配餐组合优化器")
    ap.add_argument("--input", help="JSON 文件路径；省略则从 stdin 读")
    ap.add_argument("--mode", default="cut", choices=sorted(MODES))
    ap.add_argument("--self-test", action="store_true", help="运行内置自测")
    ap.add_argument("--list-modes", action="store_true")
    args = ap.parse_args()

    if args.list_modes:
        for k, v in MODES.items():
            print(f"{k}\t{v}")
        return 0
    if args.self_test:
        return self_test()

    raw = open(args.input, encoding="utf-8").read() if args.input else sys.stdin.read()
    payload = json.loads(raw)
    items = [x for x in (normalize_item(i) for i in payload.get("items", [])) if x]
    if not items:
        print("未读到有效餐品数据，请检查 items 字段。")
        return 1
    constraints = payload.get("constraints", {})
    mode = payload.get("mode") or args.mode
    pool = build_pool(items, constraints)
    plans = search(pool, constraints, mode)
    print(render(plans, mode, constraints))
    return 0


if __name__ == "__main__":
    sys.exit(main())
