# Copyright 2025-present DatusAI, Inc.
# Licensed under the Apache License, Version 2.0.
# See http://www.apache.org/licenses/LICENSE-2.0 for details.

"""Shared JS naming primitives for cube model authoring.

M7 (LLM generation) and M8 (OSI transpile) must derive identical cube and
member names from the same source names — two diverging camel implementations
would make the same column transpile differently depending on the path.
"""

import re

# Legal bare JS identifier: no quotes needed when used as an object key.
JS_IDENT_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")


def camel(name: str) -> str:
    """LowerCamelCase a source name into a legal JS member identifier.

    Single-token names that are already legal JS identifiers stay as-is
    (``CDSCode`` remains); separator-delimited names become lowerCamelCase;
    results that would be illegal (e.g. digit-leading) get a ``member_``
    prefix.
    """
    if "_" not in name and " " not in name and name and name[0].isalpha() and JS_IDENT_RE.match(name):
        return name
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", name) if p]
    out = "".join(p[:1].upper() + p[1:] for p in parts)
    out = out[0].lower() + out[1:] if out else "col"
    if not JS_IDENT_RE.match(out):
        out = "member_" + "".join(ch for ch in out if ch.isalnum())
    return out


def normalize_join_name(col: str) -> str:
    """Reduce a column name to a comparable join key: lowercase letters only,
    trailing ``s`` stripped (``schools`` ~ ``school``)."""
    n = re.sub(r"[^a-z]", "", col.lower())
    return n[:-1] if n.endswith("s") else n
