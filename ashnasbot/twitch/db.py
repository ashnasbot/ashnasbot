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
    logger.info("Create table %s", tbl_name)
    db.create_table(tbl_name, primary_id=primary, primary_type=db.types.text)


def ensure(tbl_name, primary):
    if not exists(tbl_name):
        create(tbl_name, primary)


def get(tbl_name):
    table = db[tbl_name]
    return table.all()


def find(tbl_name, **kwargs):
    table = db[tbl_name]
    return table.find_one(**kwargs)


def touch(tbl_name):
    stats = db["stats"]
    stats.upsert({"name": tbl_name, "val": time.time()}, keys=['name'])


def update(tbl_name, record, keys):
    table = db[tbl_name]
    table.upsert(record, keys, ensure=True)
    touch(tbl_name)


def update_multi(tbl_name, rows, keys):
    table = db[tbl_name]
    try:
        for record in rows:
            table.upsert(record, keys, ensure=True)
    except Exception as e:
        logger.error(e)
    else:
        touch(tbl_name)


def expired(tbl_name):
    stats = db['stats']
    if not stats.exists:
        db.create_table("stats", primary_id="name", primary_type=db.types.text)
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
