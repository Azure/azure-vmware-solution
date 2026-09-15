# Diagram sources

The SVGs in this folder are generated, not hand-drawn. They follow the visual language of the
[Azure VMware Solution master diagrams](https://github.com/Azure/azure-vmware-solution/tree/main/azure-vmware-master-diagrams):
Segoe UI, a solid Azure-blue boundary for Azure, a dashed blue rectangle for a VNet, a solid black
rectangle for an AVS private cloud, purple for ExpressRoute, and green for the data path.

| File | Used in |
|---|---|
| `architecture.svg` | [README](../../../README.md) — *How it works* |
| `gen1-gen2.svg` | [README](../../../README.md) — *AVS Gen 1 and Gen 2* |
| `request-flow.svg` | [README](../../../README.md) — *Security model*, and [blog.md](../../blog.md) |
| `workload-pattern.svg` | [blog.md](../../blog.md) — *Solution overview* |
| `topology.svg` | [blog.md](../../blog.md) — *Network topology* |

Each diagram has a `-dark` twin. Both are referenced from a `<picture>` element so GitHub serves
the right one for the reader's theme.

## Regenerating

```bash
cd docs/media/diagrams
python generate_diagrams.py     # rewrites all ten SVGs
```

`_svgkit.py` holds the palette and the shape/glyph primitives — edit the `LIGHT` and `DARK`
dictionaries there to change colours in one place. `generate_diagrams.py` holds one function per
diagram. No dependencies beyond the standard library.

> Keep the two themes' accent colours distinct from one another; `request_flow()` asserts on the
> number of unique arrow colours when it builds its arrowhead markers.
