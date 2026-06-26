# Paper Cave — Prompt Library v2
# Card & Stack Manifest System

---

## Vocabulary

**Draggable unit** — anything the user can pick up and move. Either a single
card or a stack. `unitCount` in the manifest counts these, not individual cards.

**Card** — a single draggable unit with one content item.

**Stack** — a single draggable unit containing 2–4 card items grouped together.
Visually rendered as slightly offset cards on top of each other.

**Card item** — an individual content piece inside a stack. Not independently
draggable.

**Content types** — figure | chart | table | animation
Limit: max 5 items of the same contentType per draggable unit.
(This limit meaningfully applies to stacks — individual cards always have 1.)

---

## When to use a stack vs a single card

Use a **stack** when 2–4 items:
- Come from the same section or table in the paper
- Are naturally compared (e.g., two evaluation conditions)
- Form a logical sequence that benefits from being browsed together
- Would each be too thin to stand alone as individual units

Use a **single card** for:
- The primary contribution (always a single card, never a stack)
- Any concept that stands clearly on its own
- Items that are likely to be placed separately in the experience

---

## JSON schema

### Top level

```json
{
  "paperTitle": "string",
  "centralContribution": "string — one sentence",
  "unitCount": 5,
  "units": [ ... ]
}
```

`unitCount` = number of draggable units (cards + stacks combined).

---

### Unit — type: card

```json
{
  "id": "unit_01",
  "type": "card",
  "priority": "primary | secondary",
  "title": "string — max 30 chars",
  "category": "contribution | method | problem | metric | result | limitation | dataset | artifact | relation",
  "summary": "string — max 80 chars, one complete sentence, shown collapsed",
  "contentType": "figure | chart | table | animation",
  "content": { ... },
  "conceptualOrigin": "specific section, figure, or table from the paper",
  "whyThisUnit": "why this concept was selected",
  "styleHint": {
    "categoryColor": "#hex",
    "colorName": "human-readable"
  }
}
```

---

### Unit — type: stack

```json
{
  "id": "unit_02",
  "type": "stack",
  "priority": "secondary",
  "stackLabel": "string — max 30 chars, shown when stack is collapsed",
  "category": "string — dominant category of the items in the stack",
  "whyThisUnit": "why these items are grouped together",
  "styleHint": {
    "categoryColor": "#hex",
    "colorName": "human-readable"
  },
  "items": [
    {
      "index": 1,
      "title": "string — max 30 chars",
      "contentType": "figure | chart | table | animation",
      "content": { ... }
    },
    {
      "index": 2,
      "title": "string — max 30 chars",
      "contentType": "figure | chart | table | animation",
      "content": { ... }
    }
  ]
}
```

Rules for stacks:
- 2 to 4 items per stack
- Max 5 items of the same contentType within the stack
- All items share the stack's category and styleHint
- `priority` is always `"secondary"` for stacks

---

### Content blocks

**figure**
```json
{
  "assetReference": "FIG1",
  "caption": "caption as it appears in the paper",
  "description": "1-2 sentences — what it shows and why it matters"
}
```

**chart**
```json
{
  "chartType": "bar | grouped_bar",
  "title": "string — max 50 chars",
  "description": "what the data shows and why it matters",
  "data": {
    "labels": ["string"],
    "values": [0.0],
    "unit": "string",
    "average": null,
    "threshold": { "value": 0, "label": "string" }
  }
}
```

**table**
```json
{
  "chartType": "table | comparison_table",
  "title": "string — max 50 chars",
  "description": "what the table shows",
  "data": {
    "columns": ["string"],
    "rows": [["string or number"]]
  }
}
```

**animation**
```json
{
  "description": "what process this represents",
  "frameCount": 3,
  "frames": [
    {
      "index": 1,
      "label": "string — max 20 chars",
      "description": "string — max 120 chars",
      "assetReference": "FIG2 or null"
    }
  ],
  "transitionType": "fade | slide",
  "looping": true
}
```

---

### Category color map

```
contribution → #FFB800  golden amber
method       → #00D4FF  cyan blue
problem      → #FF4444  coral red
metric       → #00FF88  neon green
limitation   → #4A5568  bluish grey
dataset      → #8B5CF6  luminous purple
result       → #FFFFFF  bright white
```

---

## Web prompts — copy and paste

### WEB-V1 — Single prompt (attach PDF)

```
You are an educational card designer for interactive Unity experiences.

Analyze the attached scientific paper and produce a Card Manifest with
exactly 5 draggable units. A unit is either a single card or a stack
(2–4 card items grouped together as one draggable piece).

VOCABULARY:
- Draggable unit: a card (single item) or a stack (2-4 items grouped).
- unitCount counts draggable units, not individual cards.
- A stack is appropriate when items naturally belong together
  (same section, compared conditions, logical sequence).
- The primary contribution must always be a single card, never a stack.

CONTENT TYPES (per item):
  figure    — real paper figure. content.assetReference = "FIG1", "FIG2", etc.
              Only use if the figure actually exists in the paper.
  chart     — quantitative data with bars. Include EXACT paper values in content.data.
  table     — tabular data. Include EXACT paper values in content.data.
  animation — sequential process. 2–4 frames, each with label (≤20 chars)
              and description (≤120 chars).

LIMIT: max 5 items of the same contentType within any single unit.

FIELD CONSTRAINTS:
  title / stackLabel: max 30 characters
  summary:            max 80 characters (single cards only, one complete sentence)
  chart bar labels:   max 12 characters
  table column headers: max 15 characters
  table cell values:  max 20 characters

RULES:
1. Exactly 1 unit must have priority="primary" — always a single card,
   always the paper's central contribution, always id="unit_01"
2. All other units have priority="secondary"
3. At least 1 unit must use contentType="figure" if paper figures exist
4. At least 1 unit must use contentType="chart" or "table" if
   quantitative data exists in the paper — with real values in content.data
5. Variety of contentType across units

CATEGORY COLORS:
  contribution: #FFB800  method: #00D4FF  problem: #FF4444
  metric: #00FF88  limitation: #4A5568  dataset: #8B5CF6  result: #FFFFFF

Return ONLY valid JSON:
{
  "paperTitle": "string",
  "centralContribution": "string",
  "unitCount": 5,
  "units": [
    {
      "id": "unit_01",
      "type": "card",
      "priority": "primary",
      "title": "string (≤30 chars)",
      "category": "string",
      "summary": "string (≤80 chars)",
      "contentType": "string",
      "content": { ... },
      "conceptualOrigin": "string",
      "whyThisUnit": "string",
      "styleHint": { "categoryColor": "hex", "colorName": "string" }
    },
    {
      "id": "unit_02",
      "type": "stack",
      "priority": "secondary",
      "stackLabel": "string (≤30 chars)",
      "category": "string",
      "whyThisUnit": "string",
      "styleHint": { "categoryColor": "hex", "colorName": "string" },
      "items": [
        {
          "index": 1,
          "title": "string (≤30 chars)",
          "contentType": "string",
          "content": { ... }
        }
      ]
    }
  ]
}
```

---

### WEB-V2-STEP1 — Extraction (attach PDF)

```
You are a scientific paper analyst specializing in identifying conceptual
elements that can be materialized as interactive educational card units.

Read the attached paper and extract between 8 and 10 conceptual elements.

For each element identify:
- name: short descriptive name
- category: problem | method | dataset | metric | result | contribution |
            limitation | character | artifact | relation
- description: what it is in this paper (1-2 sentences)
- relevanceScore: 1-10 — centrality to the paper's main contribution
- justification: why it matters for understanding the paper
- groupingHint: if this element naturally groups with another extracted
  element (same section, compared conditions), note the other element's
  name here. Leave null otherwise.

Order elements from most to least relevant.

Return ONLY valid JSON:
{
  "paperTitle": "string",
  "centralContribution": "the main contribution in 1 sentence",
  "elements": [
    {
      "name": "string",
      "category": "string",
      "description": "string",
      "relevanceScore": 0,
      "justification": "string",
      "groupingHint": "name of related element or null"
    }
  ]
}
```

---

### WEB-V2-STEP2 — Card and stack generation (same conversation, no PDF needed)

```
Based on the elements you extracted, produce a Card Manifest with exactly
5 draggable units for an interactive Unity experience.

VOCABULARY:
- Draggable unit: a card (single item) or a stack (2–4 items grouped).
- unitCount counts draggable units, not individual items.
- Use groupingHint from the extraction to guide stack decisions.

WHEN TO USE A STACK:
  Group items into a stack when they:
  - Come from the same section or table in the paper
  - Are naturally compared (two evaluation conditions, two modules)
  - Form a logical sequence worth browsing together
  - Would each be too thin to stand alone as individual units

WHEN TO USE A SINGLE CARD:
  - The primary contribution (always a single card, never a stack)
  - Any concept that stands clearly on its own
  - Items likely to be placed separately in the experience

CONTENT TYPES:
  figure    — for real paper figures. content.assetReference = "FIG1" etc.
              ALWAYS prefer this when a relevant figure exists.
  chart     — for bar/grouped bar data. Include EXACT paper values.
  table     — for tabular data. Include EXACT paper values.
  animation — for dynamic processes. 2–4 frames with label (≤20 chars)
              and description (≤120 chars).

LIMIT: max 5 items of the same contentType within any single unit.

FIELD CONSTRAINTS:
  title / stackLabel: ≤30 characters — count carefully
  summary (single cards): ≤80 characters — one complete informative sentence
  chart bar labels:   ≤12 characters — abbreviate if needed
  table column headers: ≤15 characters
  table cell values:  ≤20 characters

RULES:
1. Exactly 1 unit must be priority="primary" — always a single card,
   always the central contribution, always id="unit_01"
2. All other units are priority="secondary"
3. At least 1 figure unit/item if paper figures exist
4. At least 1 chart or table unit/item if quantitative data exists —
   with real paper values in content.data
5. Variety of contentType across units

CATEGORY COLORS:
  contribution: #FFB800  method: #00D4FF  problem: #FF4444
  metric: #00FF88  limitation: #4A5568  dataset: #8B5CF6  result: #FFFFFF

FEW-SHOT EXAMPLE — RAG facial animation paper (5 units, 1 stack):

{
  "paperTitle": "Generative AI for Facial Expressions in 3D Game Characters",
  "centralContribution": "RAG pipeline linking Unity, OpenFace, Redis and LLM to animate NPC faces without manual scripting",
  "unitCount": 5,
  "units": [
    {
      "id": "unit_01",
      "type": "card",
      "priority": "primary",
      "title": "RAG Animation System",
      "category": "contribution",
      "summary": "RAG pipeline connecting Unity plugin, OpenFace, Redis and LLM to generate NPC facial animations",
      "contentType": "figure",
      "content": {
        "assetReference": "FIG1",
        "caption": "POC system architecture for dynamic 3D character facial animation",
        "description": "The 5-component pipeline that is the paper's central contribution. Unity plugin sends blend shape images to the RAG App, OpenFace maps them to FACS Action Units, Redis stores mappings, and the LLM Animator generates animation timelines on demand."
      },
      "conceptualOrigin": "Section III — System Architecture, Fig. 1",
      "whyThisUnit": "This is the paper's contribution — the architecture that makes LLM-driven facial animation possible for any 3D character.",
      "styleHint": { "categoryColor": "#FFB800", "colorName": "golden amber" }
    },
    {
      "id": "unit_02",
      "type": "card",
      "priority": "secondary",
      "title": "Blend Shape → AU Mapping",
      "category": "method",
      "summary": "OpenFace converts blend shape images into FACS Action Unit scores — making the system character-agnostic",
      "contentType": "animation",
      "content": {
        "description": "The 4-step registration process that works for any 3D character with facial blend shapes.",
        "frameCount": 4,
        "frames": [
          { "index": 1, "label": "Capture", "description": "FacialCameraRig renders each blend shape at maximum activation.", "assetReference": null },
          { "index": 2, "label": "Analyze", "description": "OpenFace processes each image and outputs AU scores with confidence.", "assetReference": null },
          { "index": 3, "label": "Map", "description": "RAG App builds the blend shape-to-AU map. E.g.: eCTRLNoseWrinkle → AU5, confidence 0.316.", "assetReference": null },
          { "index": 4, "label": "Store", "description": "Morph model stored in Redis with unique modelID for fast retrieval.", "assetReference": null }
        ],
        "transitionType": "slide",
        "looping": false
      },
      "conceptualOrigin": "Section IV-A — Requirements Analysis and Model Preparation",
      "whyThisUnit": "This process is what makes the system work for any character — understanding it explains the generalizability claim.",
      "styleHint": { "categoryColor": "#00D4FF", "colorName": "cyan blue" }
    },
    {
      "id": "unit_03",
      "type": "stack",
      "priority": "secondary",
      "stackLabel": "Evaluation Results",
      "category": "metric",
      "whyThisUnit": "Fidelity scores and generation duration come from the same results section and are naturally read together — one tells quality, the other tells speed.",
      "styleHint": { "categoryColor": "#00FF88", "colorName": "neon green" },
      "items": [
        {
          "index": 1,
          "title": "Fidelity by Emotion",
          "contentType": "chart",
          "content": {
            "chartType": "bar",
            "title": "Animation Fidelity by Emotion (Likert 0–5)",
            "description": "3 testers rated 7 emotions. Overall average 2.99 — promising but not production-ready. Anger scored highest (3.87), contempt lowest (2.29).",
            "data": {
              "labels": ["Anger", "Happy", "Surprise", "Sadness", "Disgust", "Fear", "Contempt"],
              "values": [3.87, 3.41, 3.34, 2.89, 2.58, 2.52, 2.29],
              "unit": "Likert (0–5)",
              "average": 2.99,
              "threshold": null
            }
          }
        },
        {
          "index": 2,
          "title": "Generation Duration",
          "contentType": "table",
          "content": {
            "chartType": "table",
            "title": "Animation Generation Duration",
            "description": "Average 8.2s means the system is viable for level loading or pre-generation, not live gameplay.",
            "data": {
              "columns": ["Metric", "Value"],
              "rows": [
                ["Minimum", "3.4 s"],
                ["Maximum", "25.3 s"],
                ["Mean", "8.2 s"],
                ["Typical range", "3.4–9.4 s"],
                ["Best character", "Ja-Long: 3.71"],
                ["Worst character", "Asuna: 2.30"]
              ]
            }
          }
        }
      ]
    },
    {
      "id": "unit_04",
      "type": "card",
      "priority": "secondary",
      "title": "Generated Expressions",
      "category": "result",
      "summary": "7 characters tested across 7 emotions — concrete visual proof the pipeline works",
      "contentType": "figure",
      "content": {
        "assetReference": "FIG3",
        "caption": "Sample frames of various 3D facial expressions generated by the system",
        "description": "The actual output of the system across 7 characters and emotions. Quality variation (Asuna: 2.30 vs Ja-Long: 3.71) is partly explained by blend shape count (52 vs 146)."
      },
      "conceptualOrigin": "Section V-C — Demo App Development, Fig. 3",
      "whyThisUnit": "Seeing real output makes the abstract pipeline concrete and grounds the fidelity scores.",
      "styleHint": { "categoryColor": "#FFFFFF", "colorName": "bright white" }
    },
    {
      "id": "unit_05",
      "type": "card",
      "priority": "secondary",
      "title": "Not Yet Real-Time",
      "category": "limitation",
      "summary": "8.2s average generation — viable for loading screens, not live gameplay",
      "contentType": "table",
      "content": {
        "chartType": "table",
        "title": "Key Limitations",
        "description": "The authors explicitly recommend using the system during level loading phases or pre-generating expression libraries. Real-time use requires further optimization.",
        "data": {
          "columns": ["Limitation", "Detail"],
          "rows": [
            ["Latency", "3.4–25.3s per animation"],
            ["Mapping quality", "Fewer blend shapes → lower fidelity"],
            ["Recommended use", "Level loading / pre-generation"]
          ]
        }
      },
      "conceptualOrigin": "Section VI — Results; Section VIII — Conclusions",
      "whyThisUnit": "Understanding this limitation prevents overstating the contribution and clarifies the intended use case.",
      "styleHint": { "categoryColor": "#4A5568", "colorName": "bluish grey" }
    }
  ]
}

Return ONLY valid JSON following the structure above.
No additional text, no markdown.
```

---

## Unity MCP prompt — 2D UI version

```
Create a Unity scene called "PaperCave_Cards_2D" from the Card Manifest below.

PAPER FIGURES:
Assets/PaperFigures/ — reference by assetReference value + ".png"
(FIG1.png, FIG2.png, FIG3.png, FIG4.png)

════════════════════════════════════════════════════════
SCENE SETUP
════════════════════════════════════════════════════════

- Canvas: Screen Space Overlay, 1920×1080 reference
- EventSystem
- Background: #0A1628

════════════════════════════════════════════════════════
UNIT TYPES
════════════════════════════════════════════════════════

SINGLE CARD (type: "card"):
  Root Panel with:
  - CollapsedView  (active by default)
  - ExpandedView   (inactive, enabled on click)
  - Button on root Panel toggles between views
  - Drag handler (IDragHandler, IBeginDragHandler)
    OnBeginDrag: SetAsLastSibling
    OnDrag: follow pointer
    No snap on release

STACK (type: "stack"):
  Root object containing N card panels offset like a physical stack:
  - card[0] at (0, 0)   — front (topmost, visible)
  - card[1] at (4, -4)  — slightly down-right behind card[0]
  - card[2] at (8, -8)  — further behind (if 3 items)
  - card[3] at (12,-12) — furthest behind (if 4 items)
  Each card panel behind the front is visible at reduced opacity (60%)
  and does not respond to click independently.
  Clicking the stack root advances to the next item (cycles through items).
  Stack is dragged as one unit — drag handler on root only.
  StackLabel is shown in CollapsedView on the front card panel.

════════════════════════════════════════════════════════
COLLAPSED VIEW (single card or stack front)
════════════════════════════════════════════════════════

- Category badge: 10pt UPPERCASE, styleHint.categoryColor background, white text
- Title / StackLabel: 14pt bold white. MAX 30 CHARS — truncate with "…"
- Summary (single card only): 11pt white at 80% opacity.
  MAX 80 CHARS — wrap to 2 lines maximum
- Stack item counter (stacks only): "1 / N" in 9pt white at 60% opacity

Collapsed height: 80px (all units)

════════════════════════════════════════════════════════
EXPANDED VIEW (click to open)
════════════════════════════════════════════════════════

Render based on contentType:

figure →
  Image component (paper figure PNG)
  Caption: 10pt italic white at 70%, max 2 lines
  Description: 11pt white, max 4 lines

chart →
  Vertical bars as UI RectTransforms scaled to value
  Bar color: styleHint.categoryColor
  Labels below bars: 9pt white. MAX 12 CHARS — abbreviate if longer
  Y-axis values: 9pt white at 70%
  Threshold line if present: white dashed horizontal RectTransform with label
  Average line if present: amber dashed horizontal RectTransform
  Description: 10pt white at 80%, max 3 lines

table →
  GridLayoutGroup
  Header row: bold 10pt, styleHint.categoryColor background
  Data rows: 9pt white, alternating opacity (100% / 60%)
  Column headers: MAX 15 CHARS  |  Cell values: MAX 20 CHARS
  Description: 10pt white at 80%, max 3 lines

animation →
  One frame at a time. Previous / Next buttons at bottom.
  Frame label: 12pt bold white centered
  If assetReference: Image component; otherwise description TextMeshPro
  Description: 11pt white centered, max 3 lines
  Frame counter: "1 / N" in 9pt white at 60%
  Fade: alpha tween 0.2s  |  Slide: RectTransform tween 0.2s
  If looping=true and no input: auto-advance every 3s

════════════════════════════════════════════════════════
SIZING
════════════════════════════════════════════════════════

primary card:    320 × 420 px
secondary units: 260 × 360 px
Border (Outline component): styleHint.categoryColor, width 2px

════════════════════════════════════════════════════════
CARD MANIFEST
════════════════════════════════════════════════════════

{PASTE CARD MANIFEST JSON HERE}
```

---

## Unity MCP prompt — 3D world-space version

```
Create a Unity scene called "PaperCave_Cards_3D" from the Card Manifest below.

PAPER FIGURES:
Assets/PaperFigures/ — reference by assetReference value + ".png"

════════════════════════════════════════════════════════
SCENE SETUP
════════════════════════════════════════════════════════

- Camera: position (0, 1.6, -6), looking at origin
- Ambient directional light: #1A2A4A, intensity 0.4
- Point light at (0, 3, 0): white, intensity 1.0
- Background: #0A1628

════════════════════════════════════════════════════════
UNIT TYPES
════════════════════════════════════════════════════════

SINGLE CARD (type: "card"):
  - Quad (card face) + World Space Canvas child
  - Box Collider for click detection
  - Rigidbody (isKinematic=true) for drag
  On click: scale up 1.4x, move forward 0.5 units in Z, toggle content

STACK (type: "stack"):
  - Root empty GameObject
  - N child Quads representing stacked cards:
    card[0] at local (0, 0, 0)     — front
    card[1] at local (0.05, -0.05, 0.02)  — slightly behind
    card[2] at local (0.10, -0.10, 0.04)  — further behind
    card[3] at local (0.15, -0.15, 0.06)  — furthest behind
    Cards behind front: opacity 0.6 on their material
  - Box Collider and Rigidbody on root — drag entire stack as one unit
  - Clicking advances to next item in the stack (cycles)
  - World Space Canvas on front card only
  - StackLabel shown in collapsed state on front card canvas

════════════════════════════════════════════════════════
CARD DIMENSIONS (world units)
════════════════════════════════════════════════════════

primary card:    1.6 × 2.2 × 0.02
secondary units: 1.3 × 1.8 × 0.02

Card material: #0A1628 base, emissive border using styleHint.categoryColor
Create border as 4 thin elongated quads around card edge, emissive intensity 1.5

PRIMARY CARD POINT LIGHT:
Add Point Light child to unit_01: color #FFB800, intensity 0.8, range 2.0

════════════════════════════════════════════════════════
COLLAPSED STATE (canvas on front card face)
════════════════════════════════════════════════════════

- Category badge: small colored plane + TextMeshPro UPPERCASE, 8pt equiv
- Title / StackLabel: 12pt equiv bold white. MAX 30 CHARS — truncate with "…"
- Summary (single cards): 9pt equiv white at 80%.
  MAX 80 CHARS — wrap to 2 lines max
- Item counter (stacks): "1 / N" in 7pt equiv white at 60%

════════════════════════════════════════════════════════
EXPANDED STATE (click to open — card scales 1.4x, moves forward 0.5 in Z)
════════════════════════════════════════════════════════

figure →
  RawImage showing the figure PNG
  Caption: 8pt equiv italic white at 70%, max 2 lines
  Description: 9pt equiv white, max 4 lines

chart →
  Bars as scaled thin Quads, color = styleHint.categoryColor
  Labels below bars: 7pt equiv. MAX 12 CHARS — abbreviate if longer
  Threshold: horizontal thin white semi-transparent Quad with TextMeshPro label
  Average: dashed amber horizontal Quad
  Description: 8pt equiv white at 80%, max 3 lines

table →
  TextMeshPro with rich text
  Header: <b>, styleHint.categoryColor via <color> tag
  Rows: alternating normal / 60% opacity
  Column headers: MAX 15 CHARS  |  Cell values: MAX 20 CHARS

animation →
  One frame at a time with Previous/Next as small 3D button planes
  Frame label: 10pt equiv bold white centered at top
  If assetReference: RawImage; else: description TextMeshPro
  Description: 9pt equiv white centered, max 3 lines
  Frame counter: "1 / N", 7pt equiv white at 60%
  Fade: alpha tween 0.2s  |  Slide: position tween 0.2s
  Auto-advance every 3s if looping=true and no input

════════════════════════════════════════════════════════
LAYOUT (arc facing camera)
════════════════════════════════════════════════════════

unit_01 (primary): (0, 0, 0)
unit_02: (-2.0, -0.3, 0.2)  slight Y rotation toward center
unit_03: (2.0, -0.3, 0.2)   slight Y rotation toward center
unit_04: (-1.0, -1.8, 0.3)
unit_05: (1.0, -1.8, 0.3)

For more than 5 units: continue arc outward maintaining the pattern.

DRAG BEHAVIOR:
  OnPointerDown: detach from arc position
  OnDrag: follow pointer in world space (raycast to Z=0 plane)
          card moves to Z=-0.5 while held
  OnRelease: stays at new position, no snap

════════════════════════════════════════════════════════
CARD MANIFEST
════════════════════════════════════════════════════════

{PASTE CARD MANIFEST JSON HERE}
```

---

## Text size rules — quick reference

| Field | Limit | Applies to |
|---|---|---|
| title / stackLabel | 30 chars | all units |
| summary | 80 chars | single cards only |
| chart bar labels | 12 chars | chart content |
| table column headers | 15 chars | table content |
| table cell values | 20 chars | table content |
| animation frame label | 20 chars | animation frames |
| animation frame description | 120 chars | animation frames |
| items per stack | 2–4 | stacks |
| same contentType per unit | max 5 | stacks (practical limit) |
