#!/usr/bin/env python3
"""Generate the architecture diagrams used by README.md.

The visual language follows the official Azure VMware Solution master diagram
deck (Azure/azure-vmware-solution -> azure-vmware-master-diagrams.pptx):

  * a thin solid Azure-blue boundary for "Microsoft Azure"
  * dashed Azure-blue boundaries for virtual networks and delegated subnets
  * a solid high-contrast boundary for the AVS private cloud
  * purple for ExpressRoute, green for data flow, Segoe UI throughout

Each diagram is emitted twice, in a light and a dark theme, so the README can
serve the right one with <picture media="(prefers-color-scheme: dark)">.

Usage:  python generate_diagrams.py [output_dir]
"""

import os
import sys

# --- palette, sampled from the master deck --------------------------------
# #0078D4 Azure blue, #50E6FF Azure cyan, #8661C5 Azure purple,
# #00B050 green, #C00000 red, #505050 / #333333 text greys.

LIGHT = {
    "name": "light",
    "bg": "#FFFFFF",
    "azure": "#0078D4",
    "vnet": "#0078D4",
    "avs": "#1F2328",
    "card": "#FFFFFF",
    "card_alt": "#F6F9FC",
    "card_line": "#C5D9EA",
    "text": "#1F2328",
    "muted": "#505050",
    "cyan": "#50E6FF",
    "cyan_soft": "#E8F7FE",
    "purple": "#8661C5",
    "purple_soft": "#F1EBFA",
    "green": "#00A44F",
    "green_soft": "#E8F6EE",
    "red": "#C00000",
    "blue_soft": "#E8F1FB",
    "shadow": "#00000014",
}

DARK = {
    "name": "dark",
    "bg": "#0D1117",
    "azure": "#4DA3FF",
    "vnet": "#4DA3FF",
    "avs": "#E6EDF3",
    "card": "#161B22",
    "card_alt": "#1C2430",
    "card_line": "#30455C",
    "text": "#E6EDF3",
    "muted": "#9198A1",
    "cyan": "#50E6FF",
    "cyan_soft": "#102A38",
    "purple": "#B39BE8",
    "purple_soft": "#241C36",
    "green": "#3FB950",
    "green_soft": "#122A1B",
    "red": "#FF7B72",
    "blue_soft": "#122236",
    "shadow": "#00000000",
}

FONT = ("Segoe UI','Segoe UI Web (West European)','-apple-system',"
        "'BlinkMacSystemFont','Helvetica Neue',Arial,sans-serif")


# --- tiny SVG helpers ------------------------------------------------------

def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def text(x, y, s, size=15, fill="#000", weight="400", anchor="start",
         opacity=None):
    op = ' opacity="%s"' % opacity if opacity else ""
    return ('<text x="%g" y="%g" font-family="%s" font-size="%g" '
            'font-weight="%s" fill="%s" text-anchor="%s"%s>%s</text>'
            % (x, y, FONT, size, weight, fill, anchor, op, esc(s)))


def rect(x, y, w, h, stroke, fill="none", rx=4, dash=None, sw=1.5, opacity=None):
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    op = ' opacity="%s"' % opacity if opacity else ""
    return ('<rect x="%g" y="%g" width="%g" height="%g" rx="%g" fill="%s" '
            'stroke="%s" stroke-width="%g"%s%s/>' % (x, y, w, h, rx, fill,
                                                     stroke, sw, d, op))


def line(x1, y1, x2, y2, stroke, sw=2, dash=None, marker=None, cap="round"):
    d = ' stroke-dasharray="%s"' % dash if dash else ""
    m = ' marker-end="url(#%s)"' % marker if marker else ""
    return ('<line x1="%g" y1="%g" x2="%g" y2="%g" stroke="%s" '
            'stroke-width="%g" stroke-linecap="%s"%s%s/>'
            % (x1, y1, x2, y2, stroke, sw, cap, d, m))


def path(d, stroke, sw=2, fill="none", dash=None, marker=None):
    ds = ' stroke-dasharray="%s"' % dash if dash else ""
    m = ' marker-end="url(#%s)"' % marker if marker else ""
    return ('<path d="%s" fill="%s" stroke="%s" stroke-width="%g" '
            'stroke-linecap="round" stroke-linejoin="round"%s%s/>'
            % (d, fill, stroke, sw, ds, m))


def defs(th):
    """Arrowhead markers, one per accent colour."""
    out = ["<defs>"]
    for key in ("azure", "green", "purple", "muted", "cyan", "text"):
        c = th[key]
        out.append(
            '<marker id="ah-%s" viewBox="0 0 10 10" refX="8.5" refY="5" '
            'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            '<path d="M 0 1 L 9 5 L 0 9 z" fill="%s"/></marker>' % (key, c))
    out.append("</defs>")
    return "\n".join(out)


def svg_open(w, h, th):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%g" height="%g" '
            'viewBox="0 0 %g %g" role="img">\n' % (w, h, w, h)) + defs(th) + \
           '\n<rect width="%g" height="%g" fill="%s"/>' % (w, h, th["bg"])


# --- glyphs (simple, consistent marks in the Azure palette) ----------------

def g_azure(x, y, th, s=1.0):
    """The Azure 'A' chevron mark, drawn as two simple wedges."""
    c1, c2 = th["cyan"], th["azure"]
    return ('<g transform="translate(%g,%g) scale(%g)">'
            '<path d="M10 0 L18 20 L2 20 Z" fill="%s"/>'
            '<path d="M8.2 4.5 L0 20 L11.5 20 L5.5 15.5 Z" fill="%s"/>'
            '</g>' % (x, y, s, c2, c1))


def g_vnet(x, y, th, s=1.0):
    """The deck's VNet mark: two chevrons around three dots."""
    c = th["azure"]
    return ('<g transform="translate(%g,%g) scale(%g)" stroke="%s" '
            'stroke-width="1.8" fill="none" stroke-linecap="round" '
            'stroke-linejoin="round">'
            '<path d="M5 2 L0 8 L5 14"/><path d="M17 2 L22 8 L17 14"/>'
            '<circle cx="7.5" cy="8" r="1.5" fill="%s" stroke="none"/>'
            '<circle cx="11" cy="8" r="1.5" fill="%s" stroke="none"/>'
            '<circle cx="14.5" cy="8" r="1.5" fill="%s" stroke="none"/>'
            '</g>' % (x, y, s, c, c, c, c))


def g_cloud(x, y, th, s=1.0, color=None):
    c = color or th["azure"]
    return ('<g transform="translate(%g,%g) scale(%g)">'
            '<path d="M6 16 a5 5 0 0 1 0.6 -9.95 a6.5 6.5 0 0 1 12.3 2.1 '
            'a4.4 4.4 0 0 1 -0.9 7.85 Z" fill="%s"/>'
            '<rect x="4" y="16.4" width="16" height="3.2" rx="1.4" fill="%s"/>'
            '</g>' % (x, y, s, c, th["cyan"]))


def g_agent(x, y, th, s=1.0):
    """AI spark."""
    c, c2 = th["purple"], th["cyan"]
    return ('<g transform="translate(%g,%g) scale(%g)">'
            '<path d="M11 0 L13.4 7.6 L21 10 L13.4 12.4 L11 20 L8.6 12.4 '
            'L1 10 L8.6 7.6 Z" fill="%s"/>'
            '<path d="M19 13 L20.1 16.4 L23.5 17.5 L20.1 18.6 L19 22 '
            'L17.9 18.6 L14.5 17.5 L17.9 16.4 Z" fill="%s"/>'
            '</g>' % (x, y, s, c, c2))


def g_container(x, y, th, s=1.0):
    """Container App: a box with two bars."""
    c = th["azure"]
    return ('<g transform="translate(%g,%g) scale(%g)">'
            '<rect x="0.9" y="2.4" width="20.2" height="15.2" rx="2.4" '
            'fill="none" stroke="%s" stroke-width="1.8"/>'
            '<rect x="4.2" y="6.6" width="13.6" height="2.6" rx="1.3" fill="%s"/>'
            '<rect x="4.2" y="11" width="9" height="2.6" rx="1.3" fill="%s"/>'
            '</g>' % (x, y, s, c, c, th["cyan"]))


def g_key(x, y, th, s=1.0):
    c = th["azure"]
    return ('<g transform="translate(%g,%g) scale(%g)">'
            '<circle cx="6.4" cy="7" r="4.6" fill="none" stroke="%s" '
            'stroke-width="2.2"/>'
            '<path d="M9.6 10.2 L18.5 19.1" stroke="%s" stroke-width="2.2" '
            'stroke-linecap="round"/>'
            '<path d="M15.2 15.7 L17.8 13.1" stroke="%s" stroke-width="2.2" '
            'stroke-linecap="round"/>'
            '</g>' % (x, y, s, c, c, th["cyan"]))


def g_db(x, y, th, s=1.0):
    c, c2 = th["azure"], th["cyan"]
    return ('<g transform="translate(%g,%g) scale(%g)">'
            '<ellipse cx="10" cy="3.6" rx="8.4" ry="3.1" fill="%s"/>'
            '<path d="M1.6 3.6 L1.6 16.4 a8.4 3.1 0 0 0 16.8 0 L18.4 3.6" '
            'fill="%s"/>'
            '<ellipse cx="10" cy="16.4" rx="8.4" ry="3.1" fill="%s" '
            'opacity="0.55"/>'
            '</g>' % (x, y, s, c2, c, c2))


def g_user(x, y, th, s=1.0):
    c = th["muted"]
    return ('<g transform="translate(%g,%g) scale(%g)">'
            '<circle cx="10" cy="5.6" r="4.4" fill="%s"/>'
            '<path d="M1.6 20 a8.4 8.4 0 0 1 16.8 0 Z" fill="%s"/>'
            '</g>' % (x, y, s, c, c))


def g_shield(x, y, th, s=1.0):
    c = th["purple"]
    return ('<g transform="translate(%g,%g) scale(%g)">'
            '<path d="M10 0.8 L18.6 4.2 L18.6 10.4 C18.6 15.4 14.9 18.9 10 20.2 '
            'C5.1 18.9 1.4 15.4 1.4 10.4 L1.4 4.2 Z" fill="%s"/>'
            '<path d="M6.2 10.3 L8.9 13 L14 7.9" stroke="%s" stroke-width="2" '
            'fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            '</g>' % (x, y, s, c, th["bg"]))


def g_host(x, y, th, s=1.0):
    """Bare-metal ESXi host: a stacked server."""
    c = th["muted"]
    return ('<g transform="translate(%g,%g) scale(%g)">'
            '<rect x="2" y="2.5" width="16" height="6.4" rx="1.5" fill="none" '
            'stroke="%s" stroke-width="1.7"/>'
            '<rect x="2" y="11.2" width="16" height="6.4" rx="1.5" fill="none" '
            'stroke="%s" stroke-width="1.7"/>'
            '<circle cx="5.4" cy="5.7" r="1.15" fill="%s"/>'
            '<circle cx="5.4" cy="14.4" r="1.15" fill="%s"/>'
            '</g>' % (x, y, s, c, c, th["green"], th["green"]))


def g_folder(x, y, th, s=1.0):
    """File share: a folder."""
    c, c2 = th["azure"], th["cyan"]
    return ('<g transform="translate(%g,%g) scale(%g)">'
            '<path d="M1.5 4.6 a1.8 1.8 0 0 1 1.8 -1.8 L8 2.8 L10.2 5.4 '
            'L17.2 5.4 a1.8 1.8 0 0 1 1.8 1.8 L19 8 L1.5 8 Z" fill="%s"/>'
            '<path d="M1.5 7.6 L18.9 7.6 L17.6 17.2 a1.8 1.8 0 0 1 -1.8 1.5 '
            'L4.6 18.7 a1.8 1.8 0 0 1 -1.8 -1.5 Z" fill="%s"/>'
            '</g>' % (x, y, s, c, c2))


def g_api(x, y, th, s=1.0):
    """Line-of-business API: angle brackets around a slash."""
    c, c2 = th["azure"], th["cyan"]
    return ('<g transform="translate(%g,%g) scale(%g)" fill="none" '
            'stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round">'
            '<path d="M6.6 5 L1.6 10.4 L6.6 15.8" stroke="%s"/>'
            '<path d="M14.6 5 L19.6 10.4 L14.6 15.8" stroke="%s"/>'
            '<path d="M11.8 3.6 L9.4 17.2" stroke="%s"/>'
            '</g>' % (x, y, s, c, c, c2))


def g_gateway(x, y, th, s=1.0):
    """ExpressRoute gateway: two arrows crossing a boundary."""
    c = th["purple"]
    return ('<g transform="translate(%g,%g) scale(%g)">'
            '<rect x="1.4" y="5.2" width="17.2" height="10.4" rx="2.4" '
            'fill="none" stroke="%s" stroke-width="1.8"/>'
            '<path d="M4.6 9 L12 9 M9.6 6.6 L12 9 L9.6 11.4" stroke="%s" '
            'stroke-width="1.7" fill="none" stroke-linecap="round" '
            'stroke-linejoin="round"/>'
            '<path d="M15.4 12.4 L8 12.4 M10.4 10 L8 12.4 L10.4 14.8" '
            'stroke="%s" stroke-width="1.7" fill="none" stroke-linecap="round" '
            'stroke-linejoin="round"/>'
            '</g>' % (x, y, s, c, c, th["cyan"]))


def g_pe(x, y, th, s=1.0):
    """Private endpoint: a plug into a ring."""
    c = th["azure"]
    return ('<g transform="translate(%g,%g) scale(%g)">'
            '<circle cx="13.4" cy="10" r="5.6" fill="none" stroke="%s" '
            'stroke-width="1.9"/>'
            '<circle cx="13.4" cy="10" r="2" fill="%s"/>'
            '<path d="M0.8 10 L7.6 10" stroke="%s" stroke-width="1.9" '
            'stroke-linecap="round"/>'
            '</g>' % (x, y, s, c, th["cyan"], c))


def badge(x, y, n, th, color=None):
    """Numbered step badge."""
    c = color or th["azure"]
    return ('<g><circle cx="%g" cy="%g" r="11" fill="%s"/>%s</g>'
            % (x, y, c,
               text(x, y + 5, str(n), size=14, fill="#FFFFFF", weight="700",
                    anchor="middle")))


def note(x, y, lines, th, size=13.5, weight="400", fill=None, lh=18,
         anchor="start"):
    f = fill or th["muted"]
    return "\n".join(text(x, y + i * lh, ln, size=size, fill=f, weight=weight,
                        anchor=anchor)
                   for i, ln in enumerate(lines))
