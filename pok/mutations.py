import hashlib
import json

from constants.mutations import LISTING_MUTATIONS


def mutation_key(operation, variables):
    if operation in LISTING_MUTATIONS:
        fields = variables.get("input") or variables
        identity = fields.get("itemId") or fields.get("id")
        if identity:
            return f"listing:{identity}"
    encoded = json.dumps(variables, sort_keys=True, separators=(",", ":"))
    return f"{operation}:{hashlib.sha256(encoded.encode()).hexdigest()}"
