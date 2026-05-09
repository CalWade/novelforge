"""Bootstrap — seed the blackboard with initial novel state.

Run once before the pipeline:
    python -m src.bootstrap

Overwrites existing outline/characters/timeline/progress files (idempotent).
Does NOT touch chapters/ or summaries/ or issues.jsonl — those accumulate.

The seeded outline is a 10-chapter arc for the 港综 novel starring 林家耀
arriving in 1983 Hong Kong as a Fujian new-migrant with a knowledge-query
system. The first 3 chapters are fully beat-sheeted; chapters 4-10 are
outlines only (Planner will deepen when reached).
"""
from __future__ import annotations

import sys
from pathlib import Path

from .blackboard import Blackboard
from . import config


def seed_outline() -> dict:
    return {
        "title": "港务档案 · 1983",
        "subtitle": "一个福建仔、一张情报表、一座永远在涨潮的城市",
        "author_agent": "blackboard-novel-pipeline",
        "year_range": "1983-2000",
        "tone": "暴力美学 + 克制算计 + 市井温度",
        "protagonist": "林家耀",
        "system_name": "港务档案",
        "chapter_count_target": 800,
        "chapters_in_outline": 10,
        "chapters": [
            {
                "ch": 1,
                "title": "第一章 · 九龙城寨的第一顿饭",
                "year_month": "1983-06",
                "key_location": "九龙城寨 · 东头村道口",
                "key_characters": ["林家耀", "阿威", "阿威母亲"],
                "beats": [
                    "开篇：林家耀拎着破旅行袋从罗湖过关，到九龙城寨找远房表叔扑空",
                    "饥饿 36 小时后在城寨东头村道口一家大排档门口看见阿威被三个社团小混混堵着要钱",
                    "林家耀用系统快速查询大排档老板过去的新闻——发现老板是 14K 边缘人",
                    "他没出手，只对老板说了老板十年前一件旧事，老板默默把三个小混混赶走",
                    "阿威主动跟上来，要跟他混。林家耀给了他半碗面，说：明天早上六点来这里",
                ],
                "opening_hook": "六月的九龙城寨，地下水沟的味道和烧腊香混在一起，林家耀分辨不出哪种更重",
                "closing_hook": "阿威蹲在地上吃面，问他：大哥，你贵姓？林家耀没抬头：先别叫我大哥。",
                "tension": "生存 + 身份切换 + 第一个盟友",
                "landmines_to_avoid": ["开篇信息轰炸", "工具人配角", "AI 味形容词堆砌"],
                "word_target": 3000,
            },
            {
                "ch": 2,
                "title": "第二章 · 茶餐厅 + 第一次现金流",
                "year_month": "1983-06",
                "key_location": "旺角通菜街 + 铜锣湾怡和街",
                "key_characters": ["林家耀", "阿威", "赵老四", "路人茶餐厅老板娘"],
                "beats": [
                    "阿威按约六点到，带着一个发霉包子当早餐",
                    "林家耀在街上观察一个下午，选中一家通菜街茶餐厅做第一笔：帮老板娘追回被黑社会扣押的食油订单",
                    "手段：用系统查到放数（高利贷）商一段陈年丑闻，间接施压",
                    "老板娘给了他 800 港币谢礼。他没全拿，留 500，跟阿威说：这是第一笔，记好了",
                    "路遇赵老四（中环地产经纪）来收租，林家耀主动接近，要租一间旺角旧楼单间",
                    "章末：赵老四看着这个 22 岁福建仔，嗅出不寻常的味道",
                ],
                "opening_hook": "阿威的发霉包子落在大排档的铁皮桌上，跳了两下",
                "closing_hook": "赵老四数完押金，抬头看了林家耀一眼：后生仔，你做过什么？林家耀笑了笑没答。",
                "tension": "第一笔钱 + 观察港岛 + 种下第二个人脉",
                "landmines_to_avoid": ["流水账", "主角无动机做善事", "突然秀金手指"],
                "word_target": 3000,
            },
            {
                "ch": 3,
                "title": "第三章 · 港元黑色星期六前夜",
                "year_month": "1983-09",
                "key_location": "中环交易广场 + 湾仔酒吧街",
                "key_characters": ["林家耀", "阿威", "赵老四", "Mr. Walsh"],
                "beats": [
                    "九月，中英谈判消息密集，港币开始小幅贬值。林家耀用系统查到『黑色星期六』确切日期与港元跌至 9.6",
                    "他没资格进交易所，但可以通过赵老四的关系认识一个炒外汇小散户，借壳帮他短仓港币、长仓美元",
                    "消耗情报值 50 完成这次市场操作预览",
                    "湾仔一家英式酒吧，林家耀第一次遇见 Mr. Walsh —— 一个英籍督察，正在敲诈一个小毒贩",
                    "林家耀没介入，但把 Walsh 敲诈金额的数字记下来，意识到这个人将是长期可用的情报通道",
                    "黑色星期六当日：赌赢。利润 4.2 万港币。阿威第一次见到主角手上同时摸到这么多现金",
                    "章末：主角把利润的 30% 分给赵老四、10% 给阿威、留 60% 自己",
                ],
                "opening_hook": "九月第一个星期五傍晚，汇丰总行楼下的电话亭排队比早茶时段还长",
                "closing_hook": "阿威捧着 4200 港币发抖：大哥，这是我见过最多的钱。林家耀：记着，这还远远不够。",
                "tension": "第一次真正使用系统牟利 + 第一次接触英籍警察 + 建立三人核心圈",
                "landmines_to_avoid": ["机械降神", "金融术语不准确", "反派降智", "跪舔洋人"],
                "word_target": 3000,
            },
            # Chapters 4-10: outline only, Planner will deepen
            {
                "ch": 4,
                "title": "第四章 · 苏婷的第一篇专访",
                "year_month": "1983-10",
                "key_characters": ["林家耀", "苏婷", "阿威"],
                "beats": [
                    "TVB 记者苏婷追查一起『匿名举报放数商被警方扫荡』事件，线索指向一个福建仔",
                    "苏婷找到林家耀租的旧楼单间",
                    "林家耀与她谈话 20 分钟，话都不到 500 字，苏婷反而更想继续查",
                ],
                "tension": "第二方视角登场，埋长线伏笔",
                "word_target": 3000,
            },
            {
                "ch": 5,
                "title": "第五章 · 第一个敌人",
                "year_month": "1983-11",
                "key_characters": ["林家耀", "阿威", "赵老四", "一名 14K 堂主"],
                "beats": ["主角的小动作被 14K 某堂主注意到，开始反扑"],
                "tension": "第一次真正的危险",
                "word_target": 3000,
            },
            {
                "ch": 6,
                "title": "第六章 · 老姜与避风塘",
                "year_month": "1983-12",
                "key_characters": ["林家耀", "老姜"],
                "beats": ["铜锣湾避风塘，主角拜老姜为江湖向导（不是师父）"],
                "tension": "获得江湖规则解读人",
                "word_target": 3000,
            },
            {
                "ch": 7,
                "title": "第七章 · 中英联合声明",
                "year_month": "1984-12",
                "key_characters": ["林家耀", "赵老四", "Walsh"],
                "beats": ["1984 年 12 月 19 日联合声明签署。主角借势做多港股"],
                "tension": "第一次大额获利",
                "word_target": 3000,
            },
            {
                "ch": 8,
                "title": "第八章 · 阿威母亲病危",
                "year_month": "1985-03",
                "key_characters": ["林家耀", "阿威", "阿威母亲"],
                "beats": ["阿威的软肋第一次现形"],
                "tension": "兄弟情感考验",
                "word_target": 3000,
            },
            {
                "ch": 9,
                "title": "第九章 · Walsh 的第一次试探",
                "year_month": "1985-05",
                "key_characters": ["林家耀", "Walsh"],
                "beats": ["Walsh 想把主角变成他的棋子，主角反向下棋"],
                "tension": "主角与英籍警察的真正博弈开始",
                "word_target": 3000,
            },
            {
                "ch": 10,
                "title": "第十章 · 第一桶金到手",
                "year_month": "1985-08",
                "key_characters": ["林家耀", "阿威", "赵老四", "苏婷", "老姜"],
                "beats": ["第一个阶段性胜利：地产小楼 + 报馆股份"],
                "tension": "收 + 转",
                "word_target": 3000,
            },
        ],
    }


def seed_timeline() -> dict:
    """YAML-friendly timeline of real 1983-1984 HK events."""
    return {
        "1983": [
            {"date": "1983-01-01", "event": "新年开市，恒指开盘约 738 点"},
            {"date": "1983-06", "event": "中英第二阶段谈判僵持，港元缓慢贬值"},
            {"date": "1983-09-24", "event": "黑色星期六：港元兑美元跌至 9.6，挤兑超市与米铺"},
            {"date": "1983-10-17", "event": "联系汇率制度公布：7.8 HKD = 1 USD"},
            {"date": "1983-11", "event": "港股反弹，恒指年底收复至 ~1000 点"},
            {"date": "1983-12", "event": "九龙城寨仍在运作；传呼机开始普及"},
        ],
        "1984": [
            {"date": "1984-04", "event": "撒切尔夫人访华，第六轮谈判"},
            {"date": "1984-12-19", "event": "《中英联合声明》在北京签署"},
        ],
        "1985": [
            {"date": "1985-05-27", "event": "《联合声明》生效，过渡期开始"},
        ],
    }


def seed_characters() -> dict:
    """Duplicate (not parse) rules/characters-canon.md — deliberate for MVP.

    All agents read this yaml. The canonical markdown stays in rules/ for
    human editing; this is the machine copy.
    """
    return {
        "protagonist": {
            "id": "lin_jiayao",
            "name": "林家耀",
            "gender": "男",
            "age_1983": 22,
            "origin": "福建泉州",
            "arrived_hk": "1983-06",
            "appearance": "约 177cm，瘦削，眼神冷，左眉骨上有细长旧伤疤",
            "traits": ["极致利己", "有底线", "算计>胆大"],
            "redlines": ["不碰毒品生意", "不动未成年人", "不杀无辜老人小孩"],
            "contradictions": ["话少但熟悉港乐", "可黑吃黑但吃街边大排档"],
            "catchphrase": ["数字不会骗人", "先算账，再算命"],
            "system": {
                "name": "港务档案",
                "capability": "查询 1983-2000 公开事件、股价、报纸头条（仅查询）",
                "currency": "情报值",
                "initial_balance": 100,
                "earn_by": "完成拨乱反正任务（扳贪官、阻惨案）",
                "hard_limits": [
                    "不能预知任何人的私密对话",
                    "不能物理输出（不发炮、不治伤）",
                    "不能替主角谈判或参与现场",
                ],
            },
        },
        "supporting": [
            {"id": "a_wei", "name": "阿威（陈威）", "role": "第一个小弟",
             "age_1983": 22, "origin": "九龙城寨",
             "weakness": "母亲病重，钱和孝是两条命",
             "loyalty_source": "第 1 章被主角救过"},
            {"id": "su_ting", "name": "苏婷", "role": "第二方视角记者",
             "age_1983": 25, "affiliation": "TVB 新闻部",
             "motivation": "记者本能 + 家族求真传统",
             "narrative_rule_前10章": "不是恋爱对象，是对手+镜像"},
            {"id": "zhao_laosi", "name": "赵老四", "role": "中环地产经纪 / 情报触手",
             "age_1983": 41, "origin": "浙江宁波 → 1949 南下",
             "trust_level_for_主角": "永远不完全信"},
            {"id": "mr_walsh", "name": "Mr. Walsh", "role": "英籍皇家警察高级督察",
             "age_1983": 45, "nationality": "苏格兰",
             "利用边界": "用其情报、借其手、最后驱逐或控制"},
            {"id": "lao_jiang", "name": "老姜（姜伯）", "role": "避风塘江湖向导",
             "age_1983": 60, "unspoken_pain": "儿子在新义安做红棍"},
        ],
    }


def seed_progress() -> dict:
    return {
        "current_chapter": 0,
        "completed_chapters": [],
        "in_flight": None,  # dict or None
        "last_update": None,
        "total_llm_calls": 0,
    }


def main() -> None:
    bb = Blackboard()
    print(f"Seeding blackboard at {bb.root}/ ...")

    # Overwrite seeds (idempotent)
    bb.write_json("outline.json", seed_outline())
    print(f"  ✓ outline.json ({len(bb.read_json('outline.json')['chapters'])} chapters)")

    bb.write_yaml("timeline.yaml", seed_timeline())
    print("  ✓ timeline.yaml")

    bb.write_yaml("characters.yaml", seed_characters())
    print("  ✓ characters.yaml")

    bb.write_json("progress.json", seed_progress())
    print("  ✓ progress.json")

    # Touch accumulating files (create if missing, don't erase)
    for f in ("issues.jsonl", "debt.jsonl"):
        p = bb._abs(f)
        if not p.exists():
            p.touch()
            print(f"  ✓ {f} (empty)")
        else:
            print(f"  · {f} (existing, preserved)")

    # Ensure sub-dirs
    for sub in ("chapters", "summaries", "fixes"):
        (bb.root / sub).mkdir(exist_ok=True)
        print(f"  · {sub}/ directory ready")

    print(f"\nReady. Run: python -m src.pipeline --chapter 1")


if __name__ == "__main__":
    main()
