import multiprocessing
import yaml
import sys
from utils.run_book_pipeline import process_book_id
from steps import export

# Загружаем конфиг
with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)

book_id_start = config.get("book_id_start")
book_id_end = config.get("book_id_end")
book_ids = sorted(range(book_id_start, book_id_end + 1))
steps_enabled = config["steps"]
source_lang = config["source_lang"]
target_langs = [lang.strip() for lang in config["target_lang"].split(",")]

num_workers = config.get("options", {}).get("workers", 1)

if __name__ == "__main__":

    if steps_enabled.get("export"):
        from dotenv import load_dotenv
        load_dotenv()
        export.export_book_json(book_id_start=book_id_start, book_id_end=book_id_end,
                                source_lang=source_lang, target_langs=target_langs)
        sys.exit(0)

    print(f"✅ Начинаем обработку {len(book_ids)} книг в {num_workers} потоков")
    with multiprocessing.Pool(processes=num_workers) as pool:
        pool.map(process_book_id, book_ids, chunksize=1)
