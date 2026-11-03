"""Conservative EXSD experiment: shorten only structural XML indentation.

This is not a general XML formatter. It preserves original bytes for attribute
values, comments, processing instructions, CDATA, documentation, unknown
elements and xml:space='preserve' subtrees. No serializer rewrites the document.
"""
import re
from xml.parsers import expat


STRUCTURAL = frozenset({
    "schema", "element", "attribute", "complexType", "simpleType", "sequence",
    "choice", "all", "group", "restriction", "enumeration", "annotation",
    "appinfo", "include", "meta.schema", "meta.element", "meta.attribute",
    "meta.section",
})


def tabs_for_schema_indentation(source: bytes) -> bytes:
    parser = expat.ParserCreate()
    stack = []
    edits = []
    text_start = None
    in_cdata = False

    def flush():
        nonlocal text_start
        if text_start is not None and stack and not stack[-1]["protected"] and not stack[-1]["mixed"] and not in_cdata:
            end = parser.CurrentByteIndex
            original = source[text_start:end]
            if original and not original.strip(b" \t\r\n"):
                changed = re.sub(rb"(?m)^ {3,}", lambda m:
                    b"\t" * (len(m[0]) // 3) + b" " * (len(m[0]) % 3), original)
                if changed != original:
                    stack[-1]["edits"].append((text_start, end, changed))
        text_start = None

    def start(name, attrs):
        flush()
        namespace = attrs.get("xmlns", stack[-1]["namespace"] if stack else "")
        protected = (bool(stack and (stack[-1]["protected"] or stack[-1]["mixed"]))
                     or name not in STRUCTURAL
                     or namespace not in ("", "http://www.w3.org/2001/XMLSchema")
                     or attrs.get("xml:space") == "preserve")
        stack.append({"protected": protected, "namespace": namespace, "mixed": False, "edits": []})

    def end(name):
        flush()
        frame = stack.pop()
        if not frame["protected"] and not frame["mixed"]:
            (stack[-1]["edits"] if stack else edits).extend(frame["edits"])

    def text(data):
        nonlocal text_start
        if text_start is None:
            text_start = parser.CurrentByteIndex
        if stack and data.strip():
            stack[-1]["mixed"] = True

    def cdata_start():
        nonlocal in_cdata
        flush()
        in_cdata = True

    def cdata_end():
        nonlocal in_cdata
        flush()
        in_cdata = False

    def reject_doctype(*args):
        raise ValueError("DOCTYPE is outside the supported EXSD experiment")

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = text
    parser.CommentHandler = lambda data: flush()
    parser.ProcessingInstructionHandler = lambda target, data: flush()
    parser.StartCdataSectionHandler = cdata_start
    parser.EndCdataSectionHandler = cdata_end
    parser.StartDoctypeDeclHandler = reject_doctype
    parser.Parse(source, True)
    result = source
    for begin, end, replacement in sorted(edits, reverse=True):
        result = result[:begin] + replacement + result[end:]
    return result
