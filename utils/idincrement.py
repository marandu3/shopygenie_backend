from pymongo.collection import Collection

def increment_id(collection: Collection, id_field: str = "id") -> str:
    """
    Universal increment function for MongoDB collections.

    Args:
        collection (Collection): The MongoDB collection to query.
        id_field (str): The field to increment (default "id").

    Returns:
        str: The next ID as a string.
    """
    max_doc = collection.find_one(sort=[(id_field, -1)], projection={id_field: 1})
    if not max_doc or id_field not in max_doc:
        return "1"  # Start from 1 if empty
    try:
        return str(int(max_doc[id_field]) + 1)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid {id_field} value in collection: {max_doc[id_field]}")
