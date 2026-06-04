#!/usr/bin/env python3
"""
Expand <include name="..."/> nodes in repo-style manifest XML files.

- Uses the standard library (xml.etree.ElementTree).
- Reads input filename from argparse.
- Recursively inlines included manifests, preserving order.
- Inserts an XML comment above each inlined block noting the source file.
- Preserves existing elements and attributes; unknown elements are left untouched.
- Included file paths are resolved relative to the directory of the including file.
"""

import argparse
import xml.etree.ElementTree as ET
from xml.dom import minidom
from pathlib import Path
import sys

def parse_manifest(path: Path):
    text = path.read_text(encoding="utf-8")
    return ET.fromstring(text)

def add_comment_and_children(parent, index, src_path, children):
    comment = ET.Comment(f' inlined from: {src_path} ')
    parent.insert(index, comment)
    for i, c in enumerate(children, start=1):
        parent.insert(index + i, c)

def resolve_includes(root, base_dir: Path, seen_files):
    """
    Walk direct children of root and expand <include> elements in-place.
    Returns when no include children remain under this root (recursive).
    """
    i = 0
    # iterate over a snapshot list because we will mutate parent
    children = list(root)
    while i < len(children):
        node = children[i]
        if node.tag == 'include':
            name = node.get('name')
            if not name:
                i += 1
                continue
            inc_path = (base_dir / name).resolve()
            if inc_path in seen_files:
                # Prevent infinite recursion by skipping re-include; still annotate.
                comment = ET.Comment(f' skipped recursive include of: {inc_path} ')
                root.insert(list(root).index(node), comment)
                root.remove(node)
                # refresh children snapshot
                children = list(root)
                i = 0
                continue
            if not inc_path.exists():
                raise FileNotFoundError(f'Included manifest not found: {inc_path}')
            seen_files.add(inc_path)
            inc_root = parse_manifest(inc_path)
            # Recursively expand includes in the included file
            resolve_includes(inc_root, inc_path.parent, seen_files)
            # Extract children of included manifest's root (usually <manifest> children)
            inc_children = list(inc_root)
            # Insert comment and the included children in place of the include node
            insert_pos = list(root).index(node)
            add_comment_and_children(root, insert_pos, inc_path, [deep_copy_element(c) for c in inc_children])
            # remove the <include> node
            root.remove(node)
            # refresh children snapshot and restart scanning (to handle newly inserted nodes)
            children = list(root)
            i = 0
            continue
        else:
            # For non-include elements, we must still recurse into their subtree
            resolve_includes(node, base_dir, seen_files)
        i += 1

def deep_copy_element(elem):
    """Return a deep copy of an ElementTree Element (including tail/text)."""
    new = ET.Element(elem.tag, elem.attrib)
    new.text = elem.text
    new.tail = elem.tail
    for child in elem:
        new.append(deep_copy_element(child))
    return new

def strip_whitespace(elem):
    #if elem.tag is ET.Comment:
    #    elem.text = '\n' + elem.text
    #    return elem
    if elem.text and elem.text.strip() == '':
        elem.text = None
    for child in elem:
        if child.tail and child.tail.strip() == '':
            child.tail = None
        strip_whitespace(child)

def prettify_xml(elem):
    strip_whitespace(elem)
    rough = ET.tostring(elem, encoding='utf-8')
    reparsed = minidom.parseString(rough)
    return reparsed.toprettyxml(indent="  ", encoding='utf-8')

def main():
    ap = argparse.ArgumentParser(description='Expand <include> nodes in repo manifest XML files.')
    ap.add_argument('input', help='Input manifest XML file')
    args = ap.parse_args()

    root_path = Path(args.input).resolve()
    if not root_path.exists():
        print(f'Error: file not found: {root_path}', file=sys.stderr)
        sys.exit(2)

    try:
        root = parse_manifest(root_path)
    except ET.ParseError as e:
        print(f'XML parse error: {e}', file=sys.stderr)
        sys.exit(3)

    seen = {root_path}
    resolve_includes(root, root_path.parent, seen)

    out_bytes = prettify_xml(root)
    # minidom adds XML declaration; ensure utf-8 bytes to stdout
    sys.stdout.buffer.write(out_bytes)

if __name__ == '__main__':
    main()
