import dataset
import time
import logging

db = dataset.connect('sqlite:///twitchdata.db')
tables = {}
logger = logging.getLogger(__name__)


def exists(tbl_name):
    table = tables.get(tbl_name, None)
    if not table:
        table = db[tbl_name]
        tables[tbl_name] = table
    try:
        return table.exists
    except Exception:
        logger.info("Table %s not found", tbl_name)
        return False


def create(tbl_name, primary):
    logger.info("Create table %s", tbl_name)
    tbl = db.create_table(tbl_name, primary_id=primary, primary_type=db.types.text)
    tables[tbl_name] = tbl


def get(tbl_name):
    table = tables.get(tbl_name, None)
    if not table:
        table = db[tbl_name]
        tables[tbl_name] = table
    return table.all()


def find(tbl_name, **kwargs):
    table = db[tbl_name]
    return table.find_one(**kwargs)


def update(tbl_name, record, keys):
    table = db[tbl_name]
    table.upsert(record, keys, ensure=True)
    stats = tables.get("stats", None)
    if not stats:
        stats = db["stats"]
    stats.upsert({"name": tbl_name, "val": time.time()}, keys=keys)


def update_multi(tbl_name, rows, primary, keys):
    table = tables.get(tbl_name, None)
    if not table:
        table = db[tbl_name]
        tables[tbl_name] = table
    try:
        for record in rows:
            table.upsert(record, ["name"], ensure=True)
    except Exception as e:
        logger.error(e)
    else:
        stats = tables.get("stats", None)
        if not stats:
            stats = db["stats"]
        stats.upsert({"name": tbl_name, "val": time.time()}, keys=keys)


def insert_multi(tbl_name, rows, primary, keys):
    table = tables.get(tbl_name, None)
    if not table:
        table = db[tbl_name]
        tables[tbl_name] = table

    try:
        for record in rows:
            table.insert(record)
    except Exception as e:
        logger.warning(e)
    else:
        stats = tables.get("stats", None)
        if not stats:
            stats = db["stats"]
        stats.upsert({"name": tbl_name, "val": time.time()}, keys=keys)


def expired(tbl_name):
    stats = db['stats']
    if not stats:
        stats = db.create_table("stats", primary_id="name", primary_type=db.types.text)
        logger.debug("Table %s expired", tbl_name)
        return True

    stored = stats.find_one(name=tbl_name)
    if not stored:
        logger.debug("Table %s expired", tbl_name)
        return True

    if stored["val"] < time.time() - 86400:
        logger.debug("Table %s older than %d", tbl_name, time.time() - 86400)
        return True

    return False
