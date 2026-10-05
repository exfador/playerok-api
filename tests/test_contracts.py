import hashlib
import runpy
from pathlib import Path

import pytest
from graphql import parse

from constants.contracts import REQUIRED_OPERATIONS
from pok.contract import PERSISTED_QUERIES, QUERIES

REFRESH = Path(__file__).parents[1] / "scripts" / "refresh-contracts.py"


def refresh_module():
    return runpy.run_path(str(REFRESH))


@pytest.mark.parametrize("name", REQUIRED_OPERATIONS)
def test_documents_have_consistent_operation_and_fragment_names(name):
    document = parse(QUERIES[name])
    operation = document.definitions[0]
    assert operation.name.value == name
    names = [definition.name.value for definition in document.definitions]
    assert len(names) == len(set(names))
    assert hashlib.sha256(QUERIES[name].encode("utf-8")).hexdigest() == PERSISTED_QUERIES[name]


def test_publish_and_boost_accept_keep_in_sale_through_shared_input():
    assert "PublishItemInput" in QUERIES["publishItem"]
    assert "PublishItemInput" in QUERIES["increaseItemPriorityStatus"]


def test_fragments_are_resolved_by_name_across_chunks():
    refresh = refresh_module()
    sources = [
        'a=(0,x.J1)`\n    fragment ItemPart on Item {\n  id\n}\n    `;',
        'b=(0,y.J1)`\n    query item($id: UUID) {\n  item(id: $id) {\n    ...ItemPart\n  }\n}\n    ${q.ab}`;',
    ]
    contracts = refresh["extract_contracts"](sources, required=("item",))
    assert "fragment ItemPart on Item" in contracts["item"]
    assert "__typename" in contracts["item"]


def test_refresh_does_not_evaluate_javascript():
    refresh = refresh_module()
    operations, fragments, conflicts = refresh["collect_definitions"](
        ['a=(0,gql.J1)`query viewer { viewer { id } }`;throw new Error("not executed");']
    )
    assert list(operations) == ["viewer"]
    assert not fragments and not conflicts


def test_refresh_rejects_missing_operations_instead_of_partial_update():
    refresh = refresh_module()
    with pytest.raises(ValueError, match="Missing operations"):
        refresh["extract_contracts"](['a=(0,gql.J1)`query viewer { viewer { id } }`;'])


def test_refresh_rejects_missing_fragments():
    refresh = refresh_module()
    with pytest.raises(ValueError, match="missing fragment"):
        refresh["extract_contracts"](['a=(0,g.J1)`query viewer { viewer { ...Nope } }`;'], required=("viewer",))


def test_conflicting_fragment_definitions_are_rejected():
    refresh = refresh_module()
    sources = [
        'a=(0,g.J1)`fragment Part on User { id }`;',
        'b=(0,g.J1)`fragment Part on User { username }`;',
        'c=(0,g.J1)`query viewer { viewer { ...Part } }`;',
    ]
    with pytest.raises(ValueError, match="ambiguous fragment"):
        refresh["extract_contracts"](sources, required=("viewer",))
