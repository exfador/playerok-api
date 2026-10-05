import argparse
import json
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graphql import FieldNode, NameNode, OperationDefinitionNode, Visitor, parse, print_ast, visit

from constants.contracts import (
    CHUNK_PATTERN,
    CONTRACT_DIRECTORY,
    DEFINITION_PATTERN,
    INTERPOLATION_PATTERN,
    LAZY_CHUNK_PATTERN,
    LAZY_HASH_PATTERN,
    MAX_BUNDLE_BYTES,
    MAX_CHUNK_COUNT,
    MAX_DOCUMENT_BYTES,
    ORIGIN,
    REQUEST_TIMEOUT,
    REQUIRED_OPERATIONS,
    SCRIPT_PATTERN,
    TEMPLATE_PATTERN,
)
from constants.transport import DEFAULT_USER_AGENT


class AddTypename(Visitor):
    def enter_selection_set(self, node, key, parent, path, ancestors):
        if isinstance(parent, OperationDefinitionNode):
            return None
        fields = [entry for entry in node.selections if isinstance(entry, FieldNode)]
        if any(field.name.value == "__typename" for field in fields):
            return None
        typename = FieldNode(name=NameNode(value="__typename"))
        return type(node)(selections=(*node.selections, typename))


def contract_filename(name):
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower() + ".graphql"


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        data = response.read(MAX_BUNDLE_BYTES + 1)
    if len(data) > MAX_BUNDLE_BYTES:
        raise ValueError(f"Bundle file exceeds size limit: {url}")
    return data.decode("utf-8", "replace")


def discover_chunks(homepage):
    scripts = {path.lstrip("/").removeprefix("_next/") for path in re.findall(SCRIPT_PATTERN, homepage)}
    manifest = next((path for path in scripts if path.endswith("_buildManifest.js")), None)
    runtime = next((path for path in scripts if "/webpack-" in path), None)
    chunks = set(scripts)
    if manifest:
        chunks.update(re.findall(CHUNK_PATTERN, download(f"{ORIGIN}/_next/{manifest}")))
    if runtime:
        source = download(f"{ORIGIN}/_next/{runtime}")
        chunks.update(path for _, path in re.findall(LAZY_CHUNK_PATTERN, source))
        hashes = re.search(LAZY_HASH_PATTERN, source)
        if hashes:
            for chunk_id, digest in re.findall(r"(\d+):\"([0-9a-f]+)\"", hashes.group(1)):
                chunks.add(f"static/chunks/{chunk_id}.{digest}.js")
    if len(chunks) > MAX_CHUNK_COUNT:
        raise ValueError("Unexpected number of frontend chunks")
    return sorted(chunks)


def fetch_bundle(target):
    target.mkdir(parents=True, exist_ok=True)
    for path in discover_chunks(download(f"{ORIGIN}/")):
        destination = target / path.replace("/", "__")
        if not destination.exists():
            destination.write_text(download(f"{ORIGIN}/_next/{path}"), encoding="utf-8")
    return target


def collect_definitions(sources):
    operations, fragments, conflicts = {}, {}, set()
    for source in sources:
        for body in re.findall(TEMPLATE_PATTERN, source):
            clean = re.sub(INTERPOLATION_PATTERN, "", body)
            if not re.match(DEFINITION_PATTERN, clean):
                continue
            try:
                document = parse(clean)
            except Exception:
                continue
            for definition in document.definitions:
                if not getattr(definition, "name", None):
                    continue
                name = definition.name.value
                target = fragments if definition.kind == "fragment_definition" else operations
                if name in target and print_ast(target[name]) != print_ast(definition):
                    conflicts.add(name)
                target.setdefault(name, definition)
    return operations, fragments, conflicts


def fragment_spreads(node):
    found = []

    class Collector(Visitor):
        def enter_fragment_spread(self, spread, *args):
            found.append(spread.name.value)

    visit(node, Collector())
    return found


def assemble(name, operations, fragments, conflicts):
    operation = operations[name]
    ordered, seen, queue = [], set(), fragment_spreads(operation)
    while queue:
        fragment = queue.pop(0)
        if fragment in seen:
            continue
        seen.add(fragment)
        if fragment not in fragments:
            raise ValueError(f"{name}: missing fragment {fragment}")
        if fragment in conflicts:
            raise ValueError(f"{name}: ambiguous fragment {fragment}")
        ordered.append(fragments[fragment])
        queue.extend(fragment_spreads(fragments[fragment]))
    source = "\n\n".join(print_ast(node) for node in [operation, *ordered])
    if len(source.encode()) > MAX_DOCUMENT_BYTES:
        raise ValueError(f"{name}: document exceeds size limit")
    return print_ast(visit(parse(source), AddTypename()))


def extract_contracts(sources, required=REQUIRED_OPERATIONS):
    operations, fragments, conflicts = collect_definitions(sources)
    missing = sorted(set(required) - operations.keys())
    if missing:
        raise ValueError(f"Missing operations: {', '.join(missing)}")
    return {name: assemble(name, operations, fragments, conflicts) for name in required}


def current_contracts():
    return {
        name: (CONTRACT_DIRECTORY / contract_filename(name)).read_text(encoding="utf-8").rstrip()
        for name in REQUIRED_OPERATIONS
        if (CONTRACT_DIRECTORY / contract_filename(name)).exists()
    }


def changed_operations(contracts):
    current = current_contracts()
    return sorted(name for name, document in contracts.items() if current.get(name) != document)


def write_contracts(contracts):
    CONTRACT_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for name, document in contracts.items():
        (CONTRACT_DIRECTORY / contract_filename(name)).write_text(document + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.bundle and args.bundle.exists() and any(args.bundle.glob("*.js")):
        directory = args.bundle
    else:
        directory = fetch_bundle(args.bundle or Path(tempfile.mkdtemp(prefix="playerok-bundle-")))
    sources = [path.read_text(encoding="utf-8") for path in sorted(directory.glob("*.js"))]
    contracts = extract_contracts(sources)
    changed = changed_operations(contracts)
    if args.write:
        write_contracts(contracts)
    print(json.dumps({"bundle": str(directory), "checked": len(contracts), "changed": changed,
                      "written": bool(args.write)}, ensure_ascii=False))
    if args.check and changed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
