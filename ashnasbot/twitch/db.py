import dataset
import time
import logging

db = dataset.connect('sqlite:///db/twitchdata.db')
logger = logging.getLogger(__name__)


def exists(tbl_name):
    table = db[tbl_name]
    try:
        return table.exists
    except Exception:
        logger.info("Table %s not found", tbl_name)
        return False


def create(tbl_name, primary):
    # Load or create table
    logger.info("Create table %s", tbl_name)
    db.create_table(tbl_name, primary_id=primary, primary_type=db.types.text)


def get(tbl_name):
    table = db[tbl_name]
    return table.all()


def find(tbl_name, **kwargs):
    table = db[tbl_name]
    return table.find_one(**kwargs)


def update(tbl_name, record, keys):
    table = db[tbl_name]
    table.upsert(record, keys, ensure=True)
    stats = db["stats"]
    stats.upsert({"name": tbl_name, "val": time.time()}, keys=['name'])


def update_multi(tbl_name, rows, primary, keys):
    table = db[tbl_name]
    try:
        for record in rows:
            table.upsert(record, ["name"], ensure=True)
    except Exception as e:
        logger.error(e)
    else:
        stats = db["stats"]
        stats.upsert({"name": tbl_name, "val": time.time()}, keys=['name'])


def insert_multi(tbl_name, rows, primary, keys):
    table = db[tbl_name]

    try:
        for record in rows:
            table.insert(record)
    except Exception as e:
        logger.warning(e)
    else:
        stats = db["stats"]
        stats.upsert({"name": tbl_name, "val": time.time()}, keys=['name'])


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
