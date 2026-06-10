# PyProc MCP Branding Assets — Generation Prompts

This file contains the prompts used to generate the PyProc MCP logo and README
header banner.

Generated assets:
- `docs/assets/logo.png`
- `docs/assets/pyproc-mcp-banner.png`

---

## 1. Square Logo (`docs/assets/logo.png`)

```
Create a square logo icon for "PyProc MCP".

Visual concept:
A minimal procurement document/search icon connected to small MCP-style tool
nodes, suggesting AI agents accessing public procurement data. Include a subtle
Indonesia red-white accent without using official government symbols.

Style:
Modern open-source developer tool logo, simple geometric mark, clean,
professional, scalable, works as GitHub avatar and package icon.
Flat design with subtle gradients.

Colors:
- Primary: Deep navy/slate (#1a2332)
- Accent: Electric blue (#3b82f6) for AI/tooling elements
- Subtle accent: Red (#ce1126) and white (#ffffff) — Indonesia-inspired
- Works on both light and dark backgrounds

Output specifications:
- File: docs/assets/logo.png
- Aspect ratio: 1:1 (square)
- Resolution: 1024x1024 or higher
- Transparent background
- No text inside the logo mark
- No government emblems, seals, garuda symbols, or official-looking marks
- No Indonesian coat of arms
- No LKPP/LPSE/SPSE/Inaproc logos or references
```

---

## 2. README Header Banner (`docs/assets/pyproc-mcp-banner.png`)

```
Create a modern open-source software banner for "PyProc MCP", an MCP tool
server for Indonesian public procurement data.

Visual concept:
A clean AI-tooling dashboard symbol combined with procurement/search/data
elements. Include abstract nodes representing LLM tools, a subtle document/
package icon, and a small Indonesian-inspired red-white accent. The visual
should feel trustworthy, technical, transparent, and modern.

Style:
Modern developer-tool branding, minimal, professional, open-source, clean
vector/3D hybrid, suitable for a GitHub README header. Avoid government
emblems, official seals, or anything that implies affiliation with
LKPP/LPSE/SPSE/Inaproc or any government institution.

Colors:
- Background: Deep navy or slate (#1a2332)
- Primary accent: Electric blue (#3b82f6) for AI/tooling
- Subtle accent: Red (#ce1126) and white (#ffffff) — Indonesia-inspired
- Text: White or light gray on dark background

Composition:
Wide README banner layout:
- Left third: Logo mark or abstract procurement/tooling icon
- Center: "PyProc MCP" in bold modern sans-serif type
- Below title (smaller): "Real-time Indonesian procurement data for LLM agents"
- Right: Abstract data-flow lines connecting document icons to LLM/MCP tool nodes
- Bottom-right subtle accent: Small red-white dot or thin line

Typography:
- "PyProc MCP": Bold, modern sans-serif (Inter, Plus Jakarta Sans, or similar)
- Tagline: Lighter weight, smaller size

Output specifications:
- File: docs/assets/pyproc-mcp-banner.png
- Aspect ratio: 3:1 or 4:1 (wide)
- Resolution: 2400x800 or 3200x800
- Clean and readable at GitHub README width (~800px)
- No fake UI text with specific procurement data
- No official government symbols or emblems
- No garuda, no coat of arms
- No text claiming "official" or "government"
```

---

## 3. Visual Constraints (Applies to ALL Assets)

### Must Include:
- Clean, modern, developer-tool aesthetic
- Blue/navy/slate color palette
- AI/tooling visual metaphors (nodes, connections, data flow)
- Document/procurement visual metaphors (pages, search, data)

### Must NOT Include:
- Garuda Pancasila (Indonesian coat of arms)
- Any government seals, emblems, or logos
- LKPP, LPSE, SPSE, or Inaproc logos
- Text implying official government affiliation
- Text claiming "official", "resmi", "pemerintah", or "government"
- Indonesian flag used as a design element (subtle red-white accent only)
- Fake screenshots with real procurement data
- Photographs of government buildings or officials

### Acceptable Indonesia References:
- Subtle red (#ce1126) and white (#ffffff) color accent
- Minimal geometric patterns inspired by Indonesian textile motifs (if very subtle)
- The word "Indonesia" or "Indonesian" in taglines/descriptions only

---

## 4. How to Use These Prompts

1. Generate the logo first using the prompt in Section 1
2. Generate the banner using the prompt in Section 2
3. Place the output files as:
   - `docs/assets/logo.png`
   - `docs/assets/pyproc-mcp-banner.png`
4. Update `README.md` image `<img>` tags to point to these files
5. Remove the "coming soon" or placeholder comments from the README

---

## 5. Placeholder Usage in README

Until the actual images are generated, the README can reference them with
descriptive alt text:

```html
<p align="center">
  <img src="docs/assets/pyproc-mcp-banner.png"
       alt="PyProc MCP — Real-time Indonesian procurement data for LLM agents"
       width="800">
</p>
```

If images are not yet available, use an HTML comment placeholder:

```html
<!--
<p align="center">
  <img src="docs/assets/pyproc-mcp-banner.png" alt="PyProc MCP banner" width="800">
</p>
-->
```
