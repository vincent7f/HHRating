"""把 data/seed/osm-names/{城市}.txt（逗号分隔店名）转为条目并导入。"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from hhrating.batch import import_list_records
from hhrating.storage import Database

SRC = "https://overpass-api.de/api/interpreter"
LIST_NAME = "OpenStreetMap amenity=restaurant"

def main():
    db = Database("data/restaurants.json").load()
    total = 0
    for f in sorted(Path("data/seed/osm-names").glob("*.txt")):
        city = f.stem
        names = [n.strip() for n in f.read_text(encoding="utf-8").split(",") if n.strip()]
        entries = [{"name": n, "city": city, "source": SRC, "list_name": LIST_NAME} for n in names]
        s = import_list_records(entries, db)
        total += s["imported"]
        print(f"{city}: 导入 {s['imported']}（重复跳过 {s['skipped_existing']}）")
    db.save()
    print("本轮合计:", total, "| 数据库总数:", len(db))

if __name__ == "__main__":
    main()
