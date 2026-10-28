# A small Markdown renderer for the report pages: headings, paragraphs,
# lists, code blocks, inline code, bold, italics and links. Everything is
# escaped first and only these constructs are turned into HTML, because the
# Markdown is written by a model that has just read a hostile repository: raw
# HTML in it must show as text, never become markup. Links go only to http(s)
# or to files beside the report.
import html
import re

_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_SAFE_HREF = re.compile(r"^(https?://[^\s\"'<>]+|[A-Za-z0-9._/-]+(#[A-Za-z0-9_-]+)?)$")


def _inline(t):
    """One line of already-escaped text."""
    parts = re.split(r"(`[^`]+`)", t)
    out = []
    for p in parts:
        if len(p) > 1 and p.startswith("`") and p.endswith("`"):
            out.append(f"<code>{p[1:-1]}</code>")
            continue
        p = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", p)
        p = re.sub(r"(?<![\w*])\*([^*\s][^*]*)\*(?![\w*])", r"<i>\1</i>", p)

        def link(m):
            href = html.unescape(m.group(2))
            if not _SAFE_HREF.match(href) or href.startswith("//"):
                return m.group(0)
            return f'<a href="{html.escape(href, quote=True)}" rel="nofollow noopener">{m.group(1)}</a>'
        out.append(_LINK.sub(link, p))
    return "".join(out)


def render(md, shift=0):
    """Markdown to HTML; headings are shifted down by `shift` levels."""
    lines = html.escape(md or "").splitlines()
    out, para, items, code, fence = [], [], None, None, ""

    def flush():
        nonlocal para, items
        if para:
            out.append("<p>" + _inline(" ".join(para)) + "</p>")
            para = []
        if items is not None:
            out.append("<ul>" + "".join(f"<li>{_inline(i)}</li>" for i in items) + "</ul>")
            items = None

    for raw in lines:
        if code is not None:
            if raw.strip().startswith(fence):
                out.append("<pre><code>" + "\n".join(code) + "</code></pre>")
                code = None
            else:
                code.append(raw)
            continue
        s = raw.strip()
        if s.startswith("```") or s.startswith("~~~"):
            flush(); fence = s[:3]; code = []
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            flush()
            n = min(6, len(m.group(1)) + shift)
            out.append(f"<h{n}>{_inline(m.group(2))}</h{n}>")
            continue
        m = re.match(r"^([-*]|\d+[.)])\s+(.*)$", s)
        if m:
            if para:
                flush()
            if items is None:
                items = []
            items.append(m.group(2))
            continue
        if not s:
            flush()
            continue
        if items is not None and raw.startswith((" ", "\t")):
            items[-1] += " " + s
            continue
        if items is not None:
            flush()
        para.append(s)
    if code is not None:
        out.append("<pre><code>" + "\n".join(code) + "</code></pre>")
    flush()
    return "\n".join(out)


def sections(md):
    """Split a report into {heading: body} by its ## and ### headings."""
    out, cur, buf = {}, "", []
    for line in (md or "").splitlines():
        m = re.match(r"^(#{2,3})\s+(.*)$", line)
        if m:
            out[cur] = "\n".join(buf).strip()
            cur, buf = m.group(2).strip(), []
        else:
            buf.append(line)
    out[cur] = "\n".join(buf).strip()
    return out
