"""Optional Meta Pixel base snippet for public HTML pages."""

__all__ = ["meta_pixel_head_html", "apply_meta_pixel_placeholder", "is_meta_pixel_enabled"]


MARKER_COMMENT = "<!--META_PIXEL_HEAD-->"


def apply_meta_pixel_placeholder(html: str, pixel_id: str) -> str:
    """Replace META_PIXEL_HEAD in HTML with the base Meta Pixel snippet."""
    return html.replace(MARKER_COMMENT, meta_pixel_head_html(pixel_id))


def _sanitize_pixel_id(pixel_id: str) -> str:
    """Extract Meta Pixel ID: digits only (strips BOM, zero-width chars, labels like \"ID: …\" )."""
    if not pixel_id:
        return ""
    digits = "".join(c for c in str(pixel_id) if c.isdigit())
    # Real Meta pixels are typically 15–16 digits; allow 10+ to avoid accidental short matches
    return digits if len(digits) >= 10 else ""


def is_meta_pixel_enabled(pixel_id: str) -> bool:
    """True when pixel_id is usable (non-empty, numeric after sanitize)."""
    return bool(_sanitize_pixel_id(pixel_id))


def meta_pixel_head_html(pixel_id: str) -> str:
    """Official Meta Pixel base snippet; omitted if pixel_id is unset or invalid (non-numeric)."""
    pid = _sanitize_pixel_id(pixel_id)
    if not pid:
        return ""
    return (
        "<!-- Meta Pixel Code -->\n"
        "<script>\n"
        "!function(f,b,e,v,n,t,s)\n"
        "{if(f.fbq)return;n=f.fbq=function(){n.callMethod?\n"
        "n.callMethod.apply(n,arguments):n.queue.push(arguments)};\n"
        "if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';\n"
        "n.queue=[];t=b.createElement(e);t.async=!0;\n"
        "t.src=v;s=b.getElementsByTagName(e)[0];\n"
        "s.parentNode.insertBefore(t,s)}(window, document,'script',\n"
        "'https://connect.facebook.net/en_US/fbevents.js');\n"
        f"fbq('init', '{pid}');\n"
        "fbq('track', 'PageView');\n"
        "</script>\n"
        f'<noscript><img height="1" width="1" style="display:none"\n'
        f'src="https://www.facebook.com/tr?id={pid}&ev=PageView&noscript=1"\n'
        "/></noscript>\n"
        "<!-- End Meta Pixel Code -->"
    )
