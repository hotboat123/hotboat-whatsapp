"""Optional Google Tag Manager snippet for public HTML pages."""

__all__ = [
    "gtm_head_html", "gtm_body_html",
    "apply_gtm_placeholders", "is_gtm_enabled",
]


HEAD_MARKER = "<!--GTM_HEAD-->"
BODY_MARKER = "<!--GTM_BODY-->"


def _sanitize_container_id(container_id: str) -> str:
    """Extract GTM container id: GTM-XXXXXXX, uppercased. Strips BOM/zero-width chars."""
    if not container_id:
        return ""
    candidate = "".join(c for c in str(container_id) if c.isprintable()).strip().upper()
    return candidate if candidate.startswith("GTM-") and len(candidate) > 4 else ""


def is_gtm_enabled(container_id: str) -> bool:
    """True when container_id is usable (non-empty, matches GTM-XXXXXXX)."""
    return bool(_sanitize_container_id(container_id))


def gtm_head_html(container_id: str) -> str:
    """Official GTM base snippet for <head>; omitted if container_id is unset/invalid."""
    cid = _sanitize_container_id(container_id)
    if not cid:
        return ""
    return (
        "<!-- Google Tag Manager -->\n"
        "<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':\n"
        "new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],\n"
        "j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=\n"
        "'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);\n"
        f"}})(window,document,'script','dataLayer','{cid}');</script>\n"
        "<!-- End Google Tag Manager -->"
    )


def gtm_body_html(container_id: str) -> str:
    """Official GTM noscript snippet for right after <body>; omitted if unset/invalid."""
    cid = _sanitize_container_id(container_id)
    if not cid:
        return ""
    return (
        "<!-- Google Tag Manager (noscript) -->\n"
        f'<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={cid}"\n'
        'height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>\n'
        "<!-- End Google Tag Manager (noscript) -->"
    )


def apply_gtm_placeholders(html: str, container_id: str) -> str:
    """Replace GTM_HEAD/GTM_BODY markers in HTML with the official GTM snippets."""
    html = html.replace(HEAD_MARKER, gtm_head_html(container_id))
    html = html.replace(BODY_MARKER, gtm_body_html(container_id))
    return html
