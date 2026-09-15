#!/usr/bin/env python3
"""Build the architecture diagrams used by README.md.

The visual language follows the official Azure VMware Solution master diagram
deck (Azure/azure-vmware-solution -> azure-vmware-master-diagrams.pptx):

  * a thin solid Azure-blue boundary for "Microsoft Azure"
  * dashed Azure-blue boundaries for virtual networks and delegated subnets
  * a solid high-contrast boundary for the AVS private cloud
  * purple for ExpressRoute, green for the data path, Segoe UI throughout

Each diagram is written twice, light and dark, so the README can serve the
right one with <picture media="(prefers-color-scheme: dark)">.

Usage:  python generate_diagrams.py [output_dir]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _svgkit import (DARK, LIGHT, badge, g_agent, g_api, g_azure, g_cloud,
                     g_container, g_db, g_folder, g_gateway, g_host, g_key,
                     g_pe, g_shield, g_user, g_vnet, line, note, path, rect,
                     svg_open, text)


def legend_item(x, y, n, head, lines, th, colour=None, w=200):
    """A numbered legend entry: badge, bold heading, then detail lines."""
    out = [badge(x + 11, y + 11, n, th, colour),
           text(x + 30, y + 16, head, 12.5, th["text"], "700")]
    for i, ln in enumerate(lines):
        out.append(text(x + 30, y + 36 + i * 15, ln, 11, th["muted"]))
    return "\n".join(out)


# ===========================================================================
#  1. Architecture - how a question reaches a database inside AVS
# ===========================================================================

def architecture(th):
    W, H = 1120, 672
    o = [svg_open(W, H, th)]
    a = o.append

    # ---- outer Microsoft Azure boundary ----
    a(rect(152, 40, 944, 452, th["azure"], rx=6, sw=1.6))
    a(g_azure(170, 50, th, 0.85))
    a(text(196, 67, "Microsoft Azure", 15, th["text"], "600"))

    # ---- the person asking ----
    a(g_user(44, 168, th, 1.9))
    a(text(62, 248, "You", 15, th["text"], "600", anchor="middle"))
    a(note(62, 268, ["Foundry playground,", "your app, or the API"], th,
           size=12, lh=16, anchor="middle"))

    # ---- Azure AI Foundry agent ----
    a(rect(176, 120, 168, 182, th["card_line"], th["card"], rx=8, sw=1.4))
    a(g_agent(192, 136, th, 1.0))
    a(text(192, 190, "Azure AI Foundry", 14.5, th["text"], "600"))
    a(text(192, 208, "managed agent", 12.5, th["muted"]))
    a(line(192, 222, 328, 222, th["card_line"], 1))
    a(text(192, 242, "The model chooses", 12, th["muted"]))
    a(text(192, 258, "which tool to call:", 12, th["muted"]))
    a(text(192, 278, "list_sources · get_schema", 11.5, th["azure"], "600"))
    a(text(192, 293, "run_query", 11.5, th["azure"], "600"))

    # ---- your virtual network ----
    a(rect(392, 96, 316, 334, th["vnet"], rx=8, sw=1.6, dash="7 5"))
    a(g_vnet(408, 106, th, 0.85))
    a(text(440, 122, "Your virtual network", 14, th["azure"], "600"))

    # delegated subnet
    a(rect(410, 146, 282, 148, th["vnet"], th["blue_soft"], rx=6, sw=1.2,
           dash="4 4"))
    a(text(424, 166, "Delegated subnet  ·  Microsoft.App", 11.5, th["muted"]))
    a(rect(424, 176, 254, 104, th["card_line"], th["card"], rx=7, sw=1.4))
    a(g_container(438, 190, th, 0.95))
    a(text(470, 206, "MCP server", 14.5, th["text"], "600"))
    a(text(438, 232, "Azure Container Apps", 12, th["muted"]))
    a(text(438, 252, "Checks the token, then runs", 11.5, th["muted"]))
    a(text(438, 268, "one read-only SELECT.", 11.5, th["muted"]))

    # key vault
    a(rect(410, 322, 230, 88, th["card_line"], th["card"], rx=7, sw=1.4))
    a(g_key(424, 336, th, 0.9))
    a(text(454, 352, "Key Vault", 14, th["text"], "600"))
    a(text(424, 376, "Database passwords.", 12, th["muted"]))
    a(text(424, 393, "Never in code or config.", 12, th["muted"]))

    # ---- AVS private cloud ----
    a(rect(756, 96, 328, 334, th["avs"], rx=8, sw=1.8))
    a(g_cloud(772, 106, th, 0.85))
    a(text(802, 118, "Azure VMware Solution", 14, th["text"], "600"))
    a(text(802, 135, "private cloud", 12.5, th["muted"]))

    a(g_host(776, 152, th, 0.85))
    a(text(802, 170, "ESXi hosts  ·  vSAN  ·  NSX-T", 12, th["muted"]))

    # NSX segment holding the database VMs
    a(rect(772, 192, 296, 218, th["vnet"], rx=6, sw=1.2, dash="4 4"))
    a(text(786, 212, "NSX-T segment", 11.5, th["muted"]))

    for i, (name, sub) in enumerate((("SalesDB", "orders and revenue"),
                                     ("InventoryDB", "stock on hand"))):
        y = 226 + i * 88
        a(rect(786, y, 268, 74, th["card_line"], th["card_alt"], rx=6, sw=1.3))
        a(g_db(800, y + 16, th, 0.95))
        a(text(834, y + 30, name, 13.5, th["text"], "600"))
        a(text(834, y + 48, sub, 11.5, th["muted"]))
        a(text(834, y + 64, "SQL Server on a VM you own", 11, th["muted"]))

    # ---- flows: badges only, described in the legend below ----
    a(line(96, 192, 166, 192, th["muted"], 2, marker="ah-muted"))
    a(badge(131, 170, 1, th, th["muted"]))

    a(path("M344 196 L 414 214", th["green"], 2.6, dash="1 7",
           marker="ah-green"))
    a(badge(379, 178, 2, th, th["green"]))

    a(path("M500 284 L 500 318", th["azure"], 2, marker="ah-azure"))
    a(badge(500, 301, 3, th))
    a(text(518, 306, "managed identity", 11.5, th["muted"]))

    a(path("M678 228 L 750 228", th["purple"], 2.6, marker="ah-purple"))
    a(badge(714, 206, 4, th, th["purple"]))

    # results travel back the same way
    a(path("M860 434 Q 860 462 852 462 L 276 462 Q 268 462 268 454 L 268 306",
           th["muted"], 1.8, dash="6 5", marker="ah-muted"))
    a(badge(564, 462, 5, th, th["muted"]))

    # ---- numbered legend ----
    items = (
        (1, "You ask", ["A question in plain English.", "No SQL required."],
         th["muted"]),
        (2, "The agent calls a tool",
         ["Over HTTPS with an Entra token,", "which the server verifies."],
         th["green"]),
        (3, "The server unlocks",
         ["It reads the database password", "from Key Vault as itself."],
         th["azure"]),
        (4, "One read-only query",
         ["A single SELECT, sent over your", "private path into AVS."],
         th["purple"]),
        (5, "The answer comes back",
         ["Row-capped results return the", "same way; the model writes it up."],
         th["muted"]),
    )
    for i, (n, head, lines, colour) in enumerate(items):
        a(legend_item(28 + i * 217, 524, n, head, lines, th, colour))
        if i < 4:
            a(line(28 + i * 217 + 204, 522, 28 + i * 217 + 204, 584,
                   th["card_line"], 1))

    a(rect(20, 606, 1080, 46, th["card_line"], th["card_alt"], rx=8, sw=1.2))
    a(g_shield(40, 616, th, 0.85))
    a(text(74, 626, "The agent never holds a database credential, and your "
                    "databases are never exposed to the internet.", 12.5,
           th["text"], "700"))
    a(text(74, 644, "It can only call the three tools above, and the login "
                    "they use is read-only.", 11.5, th["muted"]))

    a("</svg>")
    return "\n".join(o)


# ===========================================================================
#  2. AVS Gen 1 vs Gen 2 - where the MCP server plugs in
# ===========================================================================

def avs_stack(x, y, w, h, sub, th):
    """The AVS private cloud box, drawn the way the master deck draws it."""
    out = [rect(x, y, w, h, th["avs"], rx=8, sw=1.8),
           g_cloud(x + 14, y + 12, th, 0.78),
           text(x + 40, y + 23, "AVS private cloud", 13, th["text"], "600"),
           text(x + 40, y + 39, sub, 11.5, th["muted"])]
    for i, it in enumerate(("ESXi hosts", "vSAN", "NSX-T", "vCenter")):
        iy = y + 56 + i * 26
        out.append(g_host(x + 16, iy, th, 0.62))
        out.append(text(x + 40, iy + 11, it, 11.5, th["muted"]))
    seg = y + h - 86
    out.append(rect(x + 12, seg, w - 24, 72, th["vnet"], rx=5, sw=1.2,
                    dash="4 4"))
    out.append(text(x + 24, seg + 18, "NSX-T segment", 11, th["muted"]))
    out.append(g_db(x + 24, seg + 28, th, 0.8))
    out.append(text(x + 50, seg + 44, "Your database VMs", 11.5, th["text"],
                    "600"))
    return "\n".join(out)


def vnet_side(x, w, th, gen2=False):
    """The customer VNet column: MCP server + Key Vault."""
    out = [rect(x, 116, w, 314, th["vnet"], rx=8, sw=1.6, dash="7 5"),
           g_vnet(x + 16, 126, th, 0.8),
           text(x + 44, 141, "Your virtual network", 13, th["azure"], "600")]
    cx = x + 18
    out.append(rect(cx, 162, 220, 92, th["card_line"], th["card"], rx=7, sw=1.4))
    out.append(g_container(cx + 14, 176, th, 0.85))
    out.append(text(cx + 42, 191, "MCP server", 13.5, th["text"], "600"))
    out.append(text(cx + 14, 216, "Azure Container Apps,", 11.5, th["muted"]))
    out.append(text(cx + 14, 232, "in a delegated subnet", 11.5, th["muted"]))
    out.append(rect(cx, 270, 220, 62, th["card_line"], th["card"], rx=7, sw=1.4))
    out.append(g_key(cx + 14, 282, th, 0.8))
    out.append(text(cx + 42, 297, "Key Vault", 13, th["text"], "600"))
    out.append(text(cx + 14, 320, "database passwords", 11.5, th["muted"]))
    if gen2:
        out.append(text(cx, 368, "No gateway needed.", 12, th["green"], "700"))
        out.append(text(cx, 386, "Same VNet, direct path", 11.5, th["muted"]))
        out.append(text(cx, 402, "to the private cloud.", 11.5, th["muted"]))
    else:
        out.append(text(cx, 368, "Needs an ExpressRoute", 12, th["text"], "700"))
        out.append(text(cx, 386, "gateway in this VNet to", 11.5, th["muted"]))
        out.append(text(cx, 402, "reach the private cloud.", 11.5, th["muted"]))
    return "\n".join(out)


def gen1_gen2(th):
    W, H = 1120, 556
    o = [svg_open(W, H, th)]
    a = o.append

    a(rect(20, 34, 1080, 418, th["azure"], rx=6, sw=1.6))
    a(g_azure(38, 44, th, 0.85))
    a(text(64, 61, "Microsoft Azure", 15, th["text"], "600"))

    # ---------------- Generation 1 ----------------
    a(text(44, 96, "Generation 1", 15, th["text"], "700"))
    a(text(150, 96, "private cloud sits outside your VNet", 12.5, th["muted"]))
    a(vnet_side(44, 256, th))
    a(avs_stack(380, 150, 176, 246, "Generation 1", th))
    a(path("M300 272 L 374 272", th["purple"], 2.6, marker="ah-purple"))
    a(text(337, 252, "ExpressRoute", 11, th["purple"], "700", anchor="middle"))
    a(text(337, 236, "via D-MSEE", 10.5, th["muted"], anchor="middle"))

    a(line(590, 92, 590, 430, th["card_line"], 1.4, dash="5 5"))

    # ---------------- Generation 2 ----------------
    a(text(620, 96, "Generation 2", 15, th["text"], "700"))
    a(text(726, 96, "private cloud lives inside a VNet you own", 12.5,
           th["muted"]))
    a(vnet_side(620, 456, th, gen2=True))
    a(avs_stack(890, 150, 176, 246, "Generation 2", th))
    a(path("M858 272 L 884 272", th["green"], 2.6, dash="1 6",
           marker="ah-green"))

    # ---------------- takeaway ----------------
    a(rect(20, 476, 1080, 62, th["card_line"], th["card_alt"], rx=8, sw=1.2))
    a(g_shield(40, 490, th, 0.85))
    a(text(74, 500, "The same kit works on either generation.", 13,
           th["text"], "700"))
    a(text(74, 520, "The MCP server only needs a delegated subnet in a VNet "
                    "that can reach your database VMs. Generation 1 gets there "
                    "over an ExpressRoute connection you create;", 11.5,
           th["muted"]))
    a(text(74, 536, "Generation 2 is already in a VNet, so there is nothing to "
                    "connect. Nothing else in this guide changes.", 11.5,
           th["muted"]))

    a("</svg>")
    return "\n".join(o)


# ===========================================================================
#  3. Request flow - what happens, and where the controls sit
# ===========================================================================

def request_flow(th):
    W, H = 1120, 506
    o = [svg_open(W, H, th)]
    a = o.append

    lanes = (("You", g_user), ("Foundry agent", g_agent),
             ("MCP server", g_container), ("Key Vault", g_key),
             ("Databases in AVS", g_db))
    xs = [96, 310, 552, 776, 990]

    for (lbl, glyph), x in zip(lanes, xs):
        a(glyph(x - 11, 16, th, 0.95))
        a(text(x, 64, lbl, 12.5, th["text"], "600", anchor="middle"))
        a(line(x, 78, x, 412, th["card_line"], 1.3, dash="4 5"))

    G, P, A, M = th["green"], th["purple"], th["azure"], th["muted"]
    mk = {G: "ah-green", P: "ah-purple", A: "ah-azure", M: "ah-muted"}
    assert len(mk) == 4, "theme accent colours must be distinct"

    steps = (
        (106, 0, 1, "\"Which products should we reorder?\"", M, False),
        (140, 1, 2, "list_sources", G, True),
        (174, 2, 1, "the sources it is allowed to read", M, False),
        (208, 1, 2, "get_schema  ·  run_query", G, True),
        (242, 2, 3, "fetch the password", A, False),
        (276, 2, 4, "one read-only SELECT", P, True),
        (310, 4, 2, "rows, capped", M, False),
        (344, 2, 1, "results", M, False),
        (378, 1, 0, "a grounded answer, naming its sources", M, False),
    )
    for y, i, j, label, colour, strong in steps:
        x1, x2 = xs[i], xs[j]
        d = 1 if x2 > x1 else -1
        a(line(x1 + 6 * d, y, x2 - 10 * d, y, colour, 2,
               dash="1 6" if strong else None, marker=mk[colour]))
        a(text((x1 + x2) / 2.0, y - 9, label, 11.5,
               colour if strong else th["muted"], "700" if strong else "400",
               anchor="middle"))

    # ---- the two controls that make this safe ----
    a(rect(20, 430, 532, 60, th["purple"], th["purple_soft"], rx=8, sw=1.3))
    a(g_shield(38, 444, th, 0.85))
    a(text(72, 454, "Every call carries a token, checked every time", 12.5,
           th["text"], "700"))
    a(text(72, 474, "signature  ·  issuer  ·  audience  ·  calling application",
           11.5, th["muted"]))

    a(rect(568, 430, 532, 60, th["green"], th["green_soft"], rx=8, sw=1.3))
    a(g_db(586, 444, th, 0.85))
    a(text(620, 454, "Every query is a single read-only SELECT", 12.5,
           th["text"], "700"))
    a(text(620, 474, "write keywords blocked  ·  row cap  ·  read-only "
                     "database login", 11.5, th["muted"]))

    a("</svg>")
    return "\n".join(o)


# ===========================================================================
#  4. Workload pattern - one agent, many bridges
# ===========================================================================

def workload_pattern(th):
    W, H = 1120, 604
    o = [svg_open(W, H, th)]
    a = o.append

    G, P = th["green"], th["purple"]

    # ---- the people asking ----
    a(g_user(36, 250, th, 1.7))
    a(text(53, 320, "Business users", 13, th["text"], "600", anchor="middle"))
    a(note(53, 340, ["Teams, Copilot,", "your own app"], th, size=11, lh=15,
           anchor="middle"))

    # ---- outer Microsoft Azure boundary (AVS is an Azure service: inside) ----
    a(rect(124, 34, 968, 470, th["azure"], rx=6, sw=1.6))
    a(g_azure(142, 44, th, 0.8))
    a(text(166, 60, "Microsoft Azure", 14, th["text"], "600"))

    # ---- the one agent ----
    a(rect(146, 214, 152, 150, th["card_line"], th["card"], rx=8, sw=1.4))
    a(g_agent(162, 230, th, 0.95))
    a(text(162, 282, "Azure AI Foundry", 13, th["text"], "600"))
    a(text(162, 300, "One managed agent", 12, th["muted"]))
    a(note(162, 322, ["It speaks MCP.", "It does not know", "SQL from a file share."],
           th, size=10.5, lh=14))

    # ---- the VNet holding the bridges ----
    a(rect(336, 92, 262, 384, th["vnet"], rx=8, sw=1.6, dash="7 5"))
    a(g_vnet(352, 102, th, 0.75))
    a(text(378, 116, "Your virtual network", 12.5, th["azure"], "600"))
    a(text(352, 138, "MCP servers on Container Apps", 11, th["muted"]))

    bridges = ((150, g_container, "SQL Server", "list · schema · query", True),
               (248, g_folder, "File shares", "search · read", False),
               (346, g_api, "Line-of-business APIs", "call · summarise", False))
    for by, glyph, name, tools, live in bridges:
        a(rect(352, by, 230, 80, th["card_line"], th["card"], rx=7, sw=1.3))
        a(glyph(368, by + 16, th, 0.85))
        a(text(396, by + 31, name, 12.5, th["text"], "600"))
        a(text(368, by + 54, tools, 11, th["muted"]))
        if live:
            a(rect(478, by + 10, 94, 19, th["green"], th["green_soft"], rx=9.5,
                   sw=1.1))
            a(text(525, by + 23, "built in this kit", 10, th["green"], "700",
                   anchor="middle"))
        else:
            a(text(368, by + 70, "same shape, new data source", 10,
                   th["muted"], opacity="0.85"))
        # agent -> bridge
        a(line(298, 289, 346, by + 40, G, 1.9, dash="1 6", marker="ah-green"))

    a(text(222, 392, "MCP over HTTPS", 11.5, G, "700", anchor="middle"))
    a(text(222, 408, "+ Entra token", 10.5, th["muted"], anchor="middle"))

    # ---- the AVS private cloud ----
    a(rect(632, 92, 436, 384, th["avs"], rx=8, sw=1.8))
    a(g_cloud(650, 104, th, 0.8))
    a(text(678, 120, "Azure VMware Solution", 13.5, th["text"], "600"))
    a(text(678, 137, "Your private cloud - the VMs you already run", 11,
           th["muted"]))

    loads = ((166, g_db, "SQL Server VMs",
              "Sales, inventory, finance - the systems of record"),
             (264, g_folder, "File servers",
              "Contracts, drawings, scanned documents"),
             (362, g_api, "Line-of-business apps",
              "ERP, MES, claims - whatever runs the business"))
    for ly, glyph, name, sub in loads:
        a(rect(654, ly, 396, 76, th["card_line"], th["card_alt"], rx=7, sw=1.2))
        a(glyph(672, ly + 16, th, 0.85))
        a(text(700, ly + 31, name, 12.5, th["text"], "600"))
        a(text(672, ly + 56, sub, 11, th["muted"]))
        # bridge -> workload, over the private path
        a(line(592, ly + 24, 648, ly + 38, P, 1.9, marker="ah-purple"))

    a(text(615, 84, "ExpressRoute - private, never the internet", 11, P, "700",
           anchor="middle"))

    # ---- the takeaway ----
    a(rect(20, 522, 1080, 62, th["purple"], th["purple_soft"], rx=8, sw=1.3))
    a(g_shield(40, 538, th, 0.9))
    a(text(76, 548, "One agent, one contract, many workloads.", 13,
           th["text"], "700"))
    a(text(76, 568, "Each bridge is a small server that exposes one data "
                    "source as MCP tools. Adding a workload means adding a "
                    "bridge - not rebuilding the agent, and not moving the "
                    "data out of AVS.", 11.5, th["muted"]))

    a("</svg>")
    return "\n".join(o)


# ===========================================================================
#  5. Network topology - the private path, address by address
# ===========================================================================

def topology(th):
    W, H = 1120, 640
    o = [svg_open(W, H, th)]
    a = o.append

    P = th["purple"]

    # ---- outer Microsoft Azure boundary ----
    a(rect(24, 34, 1072, 486, th["azure"], rx=6, sw=1.6))
    a(g_azure(42, 44, th, 0.8))
    a(text(66, 60, "Microsoft Azure", 14, th["text"], "600"))

    # ---- Foundry: a managed service, outside your VNet ----
    a(rect(46, 82, 240, 92, th["card_line"], th["card"], rx=8, sw=1.4))
    a(g_agent(64, 96, th, 0.9))
    a(text(92, 112, "Azure AI Foundry", 13, th["text"], "600"))
    a(text(64, 136, "Managed by Microsoft, outside", 11, th["muted"]))
    a(text(64, 152, "your VNet - so it reaches in.", 11, th["muted"]))

    # ---- the hub VNet ----
    a(rect(46, 194, 550, 306, th["vnet"], rx=8, sw=1.6, dash="7 5"))
    a(g_vnet(62, 204, th, 0.75))
    a(text(88, 218, "avs-hub-vnet", 13, th["azure"], "600"))
    a(text(176, 218, "10.40.0.0/16", 12, th["muted"]))

    # delegated subnet
    a(rect(64, 238, 280, 150, th["vnet"], rx=6, sw=1.2, dash="4 4"))
    a(text(78, 258, "aca-subnet   10.40.8.0/23", 11.5, th["azure"], "600"))
    a(text(78, 274, "delegated to Microsoft.App", 10.5, th["muted"]))
    a(rect(78, 286, 252, 86, th["card_line"], th["card"], rx=7, sw=1.3))
    a(g_container(94, 300, th, 0.85))
    a(text(122, 315, "MCP server on Container Apps", 12, th["text"], "600"))
    a(text(94, 338, "Internal ingress only - a private IP,", 10.5, th["muted"]))
    a(text(94, 353, "no public endpoint, managed identity.", 10.5, th["muted"]))

    # private endpoint
    a(rect(360, 238, 218, 74, th["card_line"], th["card_alt"], rx=7, sw=1.2))
    a(g_pe(376, 252, th, 0.85))
    a(text(404, 267, "Private endpoint", 12, th["text"], "600"))
    a(text(376, 290, "How Foundry reaches the server", 10.5, th["muted"]))
    a(path("M166 174 Q 166 206 230 206 L 449 206 Q 469 206 469 230",
           th["azure"], 1.8, dash="5 5", marker="ah-azure"))

    # key vault
    a(rect(360, 326, 218, 62, th["card_line"], th["card_alt"], rx=7, sw=1.2))
    a(g_key(376, 338, th, 0.8))
    a(text(404, 353, "Key Vault", 12, th["text"], "600"))
    a(text(376, 374, "Private endpoint, RBAC only", 10.5, th["muted"]))

    # ExpressRoute gateway
    a(rect(64, 404, 514, 80, th["purple"], th["purple_soft"], rx=7, sw=1.3))
    a(g_gateway(82, 420, th, 0.9))
    a(text(110, 435, "ExpressRoute gateway", 12.5, th["text"], "600"))
    a(text(82, 458, "GatewaySubnet 10.40.1.0/24  -  connected to the AVS "
                    "private cloud", 11, th["muted"]))
    a(text(82, 474, "with an authorisation key. Traffic never touches the "
                    "public internet.", 10.5, P, "700"))

    # ---- AVS private cloud ----
    a(rect(700, 82, 376, 418, th["avs"], rx=8, sw=1.8))
    a(g_cloud(718, 94, th, 0.8))
    a(text(746, 110, "Azure VMware Solution", 13.5, th["text"], "600"))
    a(text(746, 127, "private cloud", 11, th["muted"]))

    a(rect(720, 146, 336, 96, th["card_line"], th["card_alt"], rx=7, sw=1.2))
    a(text(738, 168, "Management network   10.10.0.0/22", 11.5, th["text"],
           "600"))
    for i, it in enumerate(("vCenter", "NSX-T mgr", "HCX")):
        a(g_host(738 + i * 106, 182, th, 0.6))
        a(text(760 + i * 106, 195, it, 10.5, th["muted"]))
    a(text(738, 228, "Untouched by this kit - the agent never talks to it.",
           10.5, th["muted"]))

    a(rect(720, 258, 336, 222, th["vnet"], rx=7, sw=1.3, dash="4 4"))
    a(text(738, 280, "NSX-T segment   10.20.10.0/24", 11.5, th["azure"], "600"))
    a(text(738, 296, "A routed workload segment, reached over ExpressRoute",
           10.5, th["muted"]))

    for i, (nm, ip) in enumerate((("SalesDB", "10.20.10.21"),
                                  ("InventoryDB", "10.20.10.22"))):
        vy = 314 + i * 80
        a(rect(738, vy, 300, 68, th["card_line"], th["card"], rx=6, sw=1.2))
        a(g_db(754, vy + 14, th, 0.85))
        a(text(782, vy + 29, nm, 12.5, th["text"], "600"))
        a(text(754, vy + 52, "%s  ·  port 1433  ·  read-only login"
               % ip, 10.5, th["muted"]))

    # ---- the private path ----
    a(path("M578 444 L 620 444 Q 648 444 648 416 L 648 398 Q 648 370 676 370 "
           "L 694 370", P, 2.4, marker="ah-purple"))
    a(text(648, 330, "ExpressRoute", 11.5, P, "700", anchor="middle"))
    a(text(648, 346, "private peering", 10.5, th["muted"], anchor="middle"))

    # ---- what this buys you ----
    a(rect(20, 542, 1080, 78, th["card_line"], th["card_alt"], rx=8, sw=1.2))
    a(g_shield(40, 556, th, 0.9))
    items = (("No public endpoint",
              "The MCP server has a private IP only."),
             ("No credential in the agent",
              "The password lives in Key Vault."),
             ("No data egress",
              "Your databases stay on your VMs in AVS."))
    for i, (head, sub) in enumerate(items):
        x = 80 + i * 344
        a(text(x, 566, head, 12, th["text"], "700"))
        a(text(x, 585, sub, 11, th["muted"]))
        if i < 2:
            a(line(x + 318, 552, x + 318, 606, th["card_line"], 1))
    a(text(80, 606, "Addresses shown are from the lab this kit was validated "
                    "in - substitute your own.", 10.5, th["muted"],
           opacity="0.9"))

    a("</svg>")
    return "\n".join(o)

    # ---- what this buys you ----
    a(rect(20, 542, 1080, 78, th["card_line"], th["card_alt"], rx=8, sw=1.2))
    a(g_shield(40, 556, th, 0.9))
    items = (("No public endpoint",
              "The MCP server has a private IP only."),
             ("No credential in the agent",
              "The password lives in Key Vault."),
             ("No data egress",
              "Your databases stay on your VMs in AVS."))
    for i, (head, sub) in enumerate(items):
        x = 80 + i * 344
        a(text(x, 566, head, 12, th["text"], "700"))
        a(text(x, 585, sub, 11, th["muted"]))
        if i < 2:
            a(line(x + 318, 552, x + 318, 606, th["card_line"], 1))
    a(text(80, 606, "Addresses shown are from the lab this kit was validated "
                    "in - substitute your own.", 10.5, th["muted"],
           opacity="0.9"))

    a("</svg>")
    return "\n".join(o)


# ===========================================================================

def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(
        os.path.abspath(__file__))
    if not os.path.isdir(out):
        os.makedirs(out)

    for name, fn in (("architecture", architecture),
                     ("gen1-gen2", gen1_gen2),
                     ("request-flow", request_flow),
                     ("workload-pattern", workload_pattern),
                     ("topology", topology)):
        for th, suffix in ((LIGHT, ""), (DARK, "-dark")):
            p = os.path.join(out, "%s%s.svg" % (name, suffix))
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(fn(th) + "\n")
            print("wrote %-26s %5d bytes, %3d lines"
                  % (os.path.basename(p), os.path.getsize(p),
                     fn(th).count("\n") + 1))


if __name__ == "__main__":
    main()
