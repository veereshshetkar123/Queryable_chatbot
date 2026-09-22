from validator import validate_collection, validate_fields, validate_filters, validate_operation

print("employees:", validate_collection("employees"))
print("wrong_collection:", validate_collection("wrong_collection"))

print(
    "valid fields:",
    validate_fields("employees", ["department", "city"])
)

print(
    "invalid fields:",
    validate_fields("employees", ["name", "email"])
)
print(
    "valid filters:",
    validate_filters(
        "employees",
        {
            "department": "AI",
            "city": "Bangalore"
        }
    )
)

print(
    "invalid filters:",
    validate_filters(
        "employees",
        {
            "wrong_field": "AI"
        }
    )
)
print("find operation:", validate_operation("find"))
print("delete operation:", validate_operation("delete"))
