#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦门卡路里精算师 · 营养数据解析器

把麦当劳 MCP `list-nutrition-foods` 返回的文本，转成 meal_planner.py 能吃的 JSON。

MCP 返回的 data 字段是一个自定义格式的字符串：
    [160]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:
      猪柳麦满分,null,1288,308,16,16,24,781,213
      ...

本脚本负责解析它、按餐品名推断品类、可选地合并价格表，输出标准 items JSON。
"""

import argparse
import json
import re
import sys

# 表头正则：[N]{字段1,字段2,...}:
HEADER_RE = re.compile(r"\[(\d+)\]\{([^}]*)\}\s*:")

# 科目数量级：kJ → kcal 的兜底换算（官方已给 energyKcal，仅在缺失时使用）
KJ_TO_KCAL = 0.239

# 品类关键词：按顺序匹配，先命中者胜
CATEGORY_RULES = [
    ("堡", ["堡", "麦满分", "吉士蛋", "板烧", "巨无霸", "麦香鸡", "麦香鱼", "双层", "麦辣鸡腿"]),
    ("卷", ["卷"]),
    ("小食", ["薯条", "麦乐鸡", "鸡翅", "鸡块", "洋葱圈", "玉米杯", "薯格", "鸡排", "盐酥鸡", "派"]),
    ("甜品", ["新地", "麦旋风", "圆筒", "冰淇淋", "圣代", "蛋卷", "华夫", "蛋糕", "布丁"]),
    ("饮料", ["可乐", "雪碧", "咖啡", "美式", "牛奶", "豆浆", "茶", "果汁", "水", "美汁源", "酷儿",
              "拿铁", "卡布奇诺", "奶茶", "柠檬", "气泡", "椰子", "燕麦"]),
    ("早餐", ["麦满分", "猪柳", "烟肉", "火腿扒", "炒蛋", "粥"]),
    ("沙拉", ["沙拉"]),
]


def guess_category(name: str) -> str:
    for cat, kws in CATEGORY_RULES:
        for kw in kws:
            if kw in name:
                return cat
    return "其他"


def parse_payload(raw: str) -> list:
    """
    解析 MCP 返回的整段文本（可以是 tools/call 的 JSON，也可以是 data 字符串本身）。
    """
    # 若是完整 JSON 响应，抽出 content[].text，再从文本里抠出 data 字段的 JSON
    text = raw
    stripped = raw.strip()
    if stripped.startswith("{"):
        try:
            obj = json.loads(stripped)
        except json.JSONDecodeError:
            obj = None
        if obj is not None:
            texts = []
            for c in (obj.get("result", {}).get("content") or []):
                if isinstance(c, dict) and c.get("text"):
                    texts.append(c["text"])
            if not texts:
                raise ValueError("JSON 响应里没有 content[].text")
            text = "\n".join(texts)

    # 从说明性文本里找第一段真正的 JSON（含 "success" 与 "data"）
    m = re.search(r"\{[^{}]*\"success\"[\s\S]*?\}\s*$|(\{[\s\S]*?\"data\"\s*:\s*\"[\s\S]*?\"\})", text)
    data_str = None
    # 优先：直接找 "data":"......" 这段（注意内部有转义引号）
    dm = re.search(r'"data"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
    if dm:
        data_str = dm.group(1)
        # 反转义
        data_str = data_str.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
    elif HEADER_RE.search(text):
        data_str = text
    else:
        raise ValueError("没找到 data 字段，也无法识别自定义格式")

    hm = HEADER_RE.search(data_str)
    if not hm:
        raise ValueError("没找到表头 [N]{...}:")
    declared = int(hm.group(1))
    fields = [f.strip() for f in hm.group(2).split(",")]

    items = []
    for line in data_str[hm.end():].splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < len(fields):
            continue
        rec = dict(zip(fields, parts))
        name = rec.get("productName", "").strip()
        if not name:
            continue

        def num(key, default=0.0):
            v = rec.get(key, "")
            if v in ("", "null", "None", "-"):
                return default
            try:
                return float(v)
            except ValueError:
                return default

        kcal = num("energyKcal")
        if kcal <= 0:
            kcal = num("energyKj") * KJ_TO_KCAL

        items.append({
            "name": name,
            "category": guess_category(name),
            "energy": kcal,
            "protein": num("protein"),
            "fat": num("fat"),
            "carb": num("carbohydrate"),
            "sodium": num("sodium"),
            "calcium": num("calcium"),
            "price": 0.0,
        })

    if declared and len(items) != declared:
        print(f"⚠️  声明 {declared} 条，实际解析 {len(items)} 条，可能有脏行被跳过", file=sys.stderr)
    return items


def merge_prices(items: list, price_map: dict) -> list:
    """按餐品名（支持部分匹配）合并价格。"""
    hit = 0
    for it in items:
        if it["name"] in price_map:
            it["price"] = float(price_map[it["name"]])
            hit += 1
    print(f"价格合并：{hit}/{len(items)} 条命中", file=sys.stderr)
    return items


def self_test() -> int:
    sample = json.dumps({
        "result": {"content": [{"text": (
            "一些说明文字\n"
            '{"success":true,"code":200,"data":"[3]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:\\n'
            "  猪柳麦满分,null,1288,308,16,16,24,781,213\\n"
            "  中薯条,null,1210,289,4,12,38,165,18\\n"
            "  零度可乐(中),null,0,0,0,0,0,20,0\\n\"}"
        )}]}
    }, ensure_ascii=False)

    items = parse_payload(sample)
    assert len(items) == 3, f"应解析出 3 条，实际 {len(items)}"
    pm = items[0]
    assert pm["name"] == "猪柳麦满分" and pm["energy"] == 308 and pm["protein"] == 16, pm
    assert pm["sodium"] == 781 and pm["calcium"] == 213, pm
    print("== 自测 1：标准格式解析 ==")
    print(f"  通过：{items[0]['name']} {items[0]['energy']}kcal 蛋白{items[0]['protein']}g")

    print("== 自测 2：品类推断 ==")
    cats = {i["name"]: i["category"] for i in items}
    assert cats["猪柳麦满分"] == "堡", cats
    assert cats["中薯条"] == "小食", cats
    assert "可乐" in items[2]["name"] and cats["零度可乐(中)"] == "饮料", cats
    # 真实数据踩到的坑：「冰美式小杯」不含"咖啡"二字，曾被误判为"其他"
    assert guess_category("冰美式小杯") == "饮料", guess_category("冰美式小杯")
    print(f"  通过：{cats}；冰美式小杯 → {guess_category('冰美式小杯')}")

    print("== 自测 3：kJ 兜底换算（energyKcal 缺失时）==")
    kj_only = '[1]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:\n  测试品,null,1000,null,1,1,1,1,1'
    it = parse_payload(kj_only)[0]
    assert abs(it["energy"] - 239.0) < 1.0, it
    print(f"  通过：1000kJ → {it['energy']:.0f}kcal")

    print("== 自测 4：脏行与缺字段不能崩 ==")
    dirty = ('[3]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:\n'
             "  正常品,null,100,25,2,1,3,10,5\n"
             "  \n"
             "  缺字段品\n")
    out = parse_payload(dirty)
    assert len(out) == 1 and out[0]["name"] == "正常品", out
    print("  通过：脏行被跳过，正常行保留")

    print("\n全部自测通过 ✅")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="解析麦当劳 MCP 营养数据为 meal_planner 输入")
    ap.add_argument("--input", help="MCP 原始响应文件；省略则从 stdin 读")
    ap.add_argument("--prices", help="价格 JSON 文件，形如 {\"餐品名\": 价格}")
    ap.add_argument("--output", help="输出文件；省略则输出到 stdout")
    ap.add_argument("--min-cal", type=float, default=0.0, help="过滤：热量下限")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    raw = open(args.input, encoding="utf-8").read() if args.input else sys.stdin.read()
    items = parse_payload(raw)
    if args.min_cal:
        items = [i for i in items if i["energy"] >= args.min_cal]
    if args.prices:
        items = merge_prices(items, json.load(open(args.prices, encoding="utf-8")))

    out = json.dumps(items, ensure_ascii=False, indent=1)
    if args.output:
        open(args.output, "w", encoding="utf-8").write(out)
        print(f"已写出 {len(items)} 条到 {args.output}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
