import json
import uuid

from models import CategorizationTask


def iter_jsonl(jsonl_path):
    with open(str(jsonl_path), 'r') as f:
        for line in f:
            yield json.loads(line)


def import_dump(jsonl_path):
    inserts = []

    rows = 0
    for item in iter_jsonl(jsonl_path):
        insert = {
            'id': str(uuid.uuid4()),
            'product_id': item['code'],
            'predicted_category': item['predicted_categories_tag'],
            'confidence': item['predicted_categories_prob'],
            'last_updated_at': str(item['last_modified_t']),
        }
        inserts.append(insert)
        rows += 1

        if rows % 100 == 0:
            CategorizationTask.insert_many(inserts).execute()
            inserts = []

    CategorizationTask.insert_many(inserts).execute()


if __name__ == "__main__":
    import_dump("predicted_categories.json")