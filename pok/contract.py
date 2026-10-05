import hashlib
import re
from types import MappingProxyType

from constants.contracts import CONTRACT_DIRECTORY, REQUIRED_OPERATIONS


def contract_filename(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower() + ".graphql"


def load_documents():
    return MappingProxyType({
        name: (CONTRACT_DIRECTORY / contract_filename(name)).read_text(encoding="utf-8").rstrip()
        for name in REQUIRED_OPERATIONS
    })


QUERIES = load_documents()
PERSISTED_QUERIES = MappingProxyType({
    name: hashlib.sha256(query.encode("utf-8")).hexdigest()
    for name, query in QUERIES.items()
})
