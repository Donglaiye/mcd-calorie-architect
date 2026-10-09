#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
麦门卡路里精算师 · 运动消耗换算器

把「这顿吃了多少 kcal」翻译成人话：要跑几公里、走多少步、骑多久车才能消耗掉。

公式：kcal/min = MET × 3.5 × 体重kg / 200（ACSM 代谢当量公式，公开通用算法）
"""

import argparse
import sys

# 活动名: (MET, 速度 km/h, 是否有距离)
ACTIVITIES = {
    "跑步": (8.3, 8.0, True),
    "快跑": (9.8, 10.0, True),
    "快走": (4.3, 5.0, True),
    "慢走": (2.8, 3.5, True),
    "骑车": (5.8, 16.0, True),
    "游泳": (7.0, 2.0, True),
    "跳绳": (11.0, 0.0, False),
    "力量训练": (3.5, 0.0, False),
    "爬楼梯": (8.0, 0.0, False),
}

STEP_LENGTH_M = 0.75   # 成人平均步幅
RICE_BOWL_KCAL = 230.0  # 一碗米饭约 230 kcal


def kcal_per_minute(met: float, weight: float) -> float:
    return met * 3.5 * weight / 200.0


def burn(kcal: float, weight: float = 65.0) -> dict:
    """返回每种活动消耗掉 kcal 需要多久 / 多远 / 多少步。"""
    out = {}
    for name, (met, speed, has_dist) in ACTIVITIES.items():
        per_min = kcal_per_minute(met, weight)
        minutes = kcal / per_min if per_min > 0 else 0.0
        entry = {"minutes": round(minutes, 1), "met": met}
        if has_dist:
            km = minutes * speed / 60.0
            entry["km"] = round(km, 2)
            if name in ("快走", "慢走", "跑步", "快跑"):
                entry["steps"] = int(km * 1000 / STEP_LENGTH_M)
        out[name] = entry
    return out


def render(kcal: float, weight: float) -> str:
    r = burn(kcal, weight)
    lines = [
        f"🔥 这一顿约 {kcal:.0f} kcal（按体重 {weight:.0f} kg 估算）",
        f"   相当于 {kcal / RICE_BOWL_KCAL:.1f} 碗米饭",
        "",
        "要把它消耗掉，你得：",
    ]
    order = ["跑步", "快走", "骑车", "游泳", "跳绳", "爬楼梯", "力量训练"]
    for name in order:
        e = r[name]
        bit = f"  🏃 {name}：{e['minutes']:.0f} 分钟"
        if "km" in e:
            bit += f"（约 {e['km']:.1f} km"
            if "steps" in e:
                bit += f" / {e['steps']:,} 步"
            bit += "）"
        lines.append(bit)
    lines.append("")
    lines.append("注：以上为 ACSM 代谢当量公式估算值，个体差异较大，仅供参考，不构成医疗或营养建议。")
    return "\n".join(lines)


def self_test() -> int:
    print("== 自测 1：热量翻倍，运动时长必须翻倍（线性）==")
    # 注意：对外输出的 minutes 已四舍五入到 1 位小数，线性断言必须用未取整的底层值，
    # 否则 42.35→42.4 与 84.7 会被误判为非线性。
    per_min = kcal_per_minute(ACTIVITIES["跑步"][0], 65)
    a, b = 400 / per_min, 800 / per_min
    assert abs(b - 2 * a) < 1e-9, f"非线性：{a} vs {b}"
    # 同时确认取整后的展示值与真实值差距不超过 0.05
    shown = burn(800, 65)["跑步"]["minutes"]
    assert abs(shown - round(b, 1)) < 1e-9, f"取整异常：{shown} vs {round(b, 1)}"
    print(f"  通过：400kcal={a:.2f}min, 800kcal={b:.2f}min（展示值 {shown}）")

    print("== 自测 2：体重越大，单位时间消耗越多，耗时越短 ==")
    light = burn(500, 50)["跑步"]["minutes"]
    heavy = burn(500, 90)["跑步"]["minutes"]
    assert heavy < light, f"体重 90kg 应比 50kg 更快消耗完：{heavy} vs {light}"
    print(f"  通过：50kg={light:.1f}min > 90kg={heavy:.1f}min")

    print("== 自测 3：MET 越高，耗时越短（跳绳应快于慢走） ==")
    jump = burn(500, 65)["跳绳"]["minutes"]
    walk = burn(500, 65)["慢走"]["minutes"]
    assert jump < walk, f"跳绳({jump}) 应快于慢走({walk})"
    print(f"  通过：跳绳 {jump:.1f}min < 慢走 {walk:.1f}min")

    print("== 自测 4：0 kcal 不应产生除零错误 ==")
    z = burn(0, 65)
    assert z["跑步"]["minutes"] == 0.0
    print("  通过：0 kcal → 0 分钟")

    print("== 自测 5：步数与距离换算自洽（5km/h 快走 ≈ 111 步/分钟）==")
    e = burn(230, 65)["快走"]
    per_min_steps = e["steps"] / e["minutes"] if e["minutes"] else 0
    assert 100 <= per_min_steps <= 125, f"步频异常：{per_min_steps:.0f} 步/分钟"
    print(f"  通过：{per_min_steps:.0f} 步/分钟")

    print("\n全部自测通过 ✅")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="麦门卡路里精算师 · 运动消耗换算器")
    ap.add_argument("kcal", nargs="?", type=float, help="这一餐的总热量")
    ap.add_argument("--weight", type=float, default=65.0, help="体重（kg），默认 65")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        return self_test()
    if args.kcal is None:
        ap.error("请提供 kcal，或使用 --self-test")

    if args.json:
        print(__import__("json").dumps(burn(args.kcal, args.weight), ensure_ascii=False, indent=2))
    else:
        print(render(args.kcal, args.weight))
    return 0


if __name__ == "__main__":
    sys.exit(main())
