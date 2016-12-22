def identity(x):
    return x

def key_by_env_var(record):
    """Key record by environment and variable"""
    return (record["environment"], record["variable"])

def should_update_value(prev_record, next_record):
    return prev_record["value"] != next_record["value"]

class KeyframeProxyStore:
    def __init__(self, db, should_update, key=None):
        """
        Given a DB object, this class will return a proxy interface which will
        store only "keyframes" (e.g. adjacent unique datapoints). Uniqueness is
        determined by `key` function and `should_update` function.

        Arguments:
        db: stateful object with a dict-key-like interface (CouchDB db)
        should_update: compare previous record to next record and return boolean

        Keyword arguments:
        key: generate a key for a record
        """
        self.db = db
        self.__prev_index = {}
        self.should_update
        self.key = key or identity

    def put(id, next_record):
        """
        Given an id and record, put record, but only if it is different
        from previous record by key.
        """
        """For a given record, get previous record by key"""
        key = self.key(record)
        prev_record = self.__prev_index[key]
        if self.should_update(prev_record, next_record):
            self.db[id] = record
            self.__prev_index[key] = next_record
        return self