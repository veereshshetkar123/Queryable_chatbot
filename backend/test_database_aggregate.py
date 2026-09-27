from schema_discovery import get_schema


def validate_collection(collection_name):
    schema = get_schema()

    if collection_name in schema:
        return True

    return False


def validate_fields(collection_name, fields):
    schema = get_schema()

    if collection_name not in schema:
        return False

    available_fields = schema[collection_name]

    for field in fields:
        if field not in available_fields:
            return False

    return True


def validate_filters(collection_name, filters):
    schema = get_schema()

    if collection_name not in schema:
        return False

    available_fields = schema[collection_name]

    for field in filters:
        if field not in available_fields:
            return False

    return True


def validate_operation(operation):
    allowed_operations = [
        "find",
        "count",
        "aggregate"
    ]

    if operation in allowed_operations:
        return True

    return False


def validate_query(query):

    collection = query["collection"]
    operation = query["operation"]

    if not validate_collection(collection):
        return False

    if not validate_operation(operation):
        return False

    if operation == "find":

        filters = query.get("filters", {})
        fields = query.get("fields", [])

        if not validate_filters(collection, filters):
            return False

        if not validate_fields(collection, fields):
            return False

    elif operation == "count":

        filters = query.get("filters", {})

        if not validate_filters(collection, filters):
            return False

    elif operation == "aggregate":

        pipeline = query.get("pipeline", [])

        if not isinstance(pipeline, list):
            return False

        if len(pipeline) == 0:
            return False

    return True