import multiprocessing
import yaml
from utils.run_book_pipeline import process_book_id

# Загружаем конфиг
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

book_id_start = config.get("book_id_start")
book_id_end = config.get("book_id_end")
book_ids = list(range(book_id_start, book_id_end + 1))

num_workers = config.get("options", {}).get("workers", 1)

if __name__ == "__main__":
    print(f"✅ Начинаем обработку {len(book_ids)} книг в {num_workers} потоков")
    with multiprocessing.Pool(processes=num_workers) as pool:
        pool.map(process_book_id, book_ids)
