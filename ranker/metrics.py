from ranker.db import SelectionDB


def compute_metrics(db: SelectionDB) -> dict:
    selections = db.get_all_selections()
    if not selections:
        return {"total": 0, "top1_rate": 0.0, "avg_position": 0.0}

    total = len(selections)
    top1 = sum(1 for s in selections if s["position"] == 0)
    avg_pos = sum(s["position"] for s in selections) / total

    return {
        "total": total,
        "top1_rate": round(top1 / total, 4),
        "avg_position": round(avg_pos, 2),
    }


if __name__ == "__main__":
    from ranker.config import DB_PATH
    db = SelectionDB(DB_PATH)
    metrics = compute_metrics(db)
    print(f"Total selections: {metrics['total']}")
    print(f"Top-1 hit rate:   {metrics['top1_rate']:.1%}")
    print(f"Avg position:     {metrics['avg_position']:.2f}")
    db.close()
