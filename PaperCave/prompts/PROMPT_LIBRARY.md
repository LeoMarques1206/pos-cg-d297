# Paper Cave — Prompt Library (v1)

> **Note**: This file describes the v1 Card Manifest format. The pipeline now
> uses the v2 Unit Manifest format (units/stacks, `unit_01` ids, `whyThisUnit`,
> `table`/`text_panel` contentTypes). See `tasks.yaml` and `agents.yaml` for
> the live v2 prompts used by the CrewAI pipeline. This file should be replaced
> with `PROMPT_LIBRARY_V2.md` when available.

Copy-paste prompts for producing and implementing Card Manifests outside the
CrewAI pipeline.

- **Web prompts** (WEB-V1, WEB-V2-STEP1, WEB-V2-STEP2): for use directly in
  Claude / ChatGPT / Gemini with a PDF attached.
- **Unity MCP prompts**: for turning a finished Card Manifest into a Unity scene
  (2D UI cards or 3D world-space cards).

The Card Manifest JSON these prompts produce is implementation-agnostic: the
same output works for both the 2D and 3D Unity implementations.

---

## Card JSON reference (quick)

```json
{
  "paperTitle": "string",
  "centralContribution": "string — one sentence",
  "cardCount": 5,
  "cards": [
    {
      "id": "card_01",
      "title": "string — max 30 characters",
      "category": "contribution | method | problem | metric | result | limitation | dataset | artifact | relation",
      "priority": "primary | secondary",
      "summary": "string — max 80 characters, single line, shown collapsed",
      "contentType": "figure | chart | animation",
      "content": { },
      "conceptualOrigin": "string — specific section, figure, or table",
      "whyThisCard": "string — why this concept was selected",
      "styleHint": { "categoryColor": "hex", "colorName": "string" }
    }
  ]
}
```

**Category color map**

| category | color | name |
|---|---|---|
| contribution | `#FFB800` | golden amber |
| method | `#00D4FF` | cyan blue |
| problem | `#FF4444` | coral red |
| metric | `#00FF88` | neon green |
| limitation | `#4A5568` | bluish grey |
| dataset | `#8B5CF6` | luminous purple |
| result | `#FFFFFF` | bright white |
| artifact | `#00D4FF` | cyan blue |
| relation | `#00D4FF` | cyan blue |

**Text length rules**

| Field | Max length |
|---|---|
| `title` | 30 characters |
| `summary` | 80 characters |
| Chart bar labels | 12 characters |
| Table column headers | 15 characters |
| Table cell values | 20 characters |
| Animation frame label | 20 characters |
| Animation frame description | 120 characters |

---

## WEB-V1 — Single prompt (attach PDF)

```
You are an educational card designer for interactive Unity experiences.

Analyze the attached scientific paper and produce a Card Manifest with
exactly 5 self-contained information cards representing the most important
concepts of the paper.

CARD STRUCTURE:
Each card has a collapsed state (title + summary shown always) and an
expanded state (full content shown on click).

Fields per card:
- id: "card_01" through "card_05"
- title: MAX 30 CHARACTERS
- category: contribution | method | problem | metric | result |
            limitation | dataset | artifact | relation
- priority: "primary" for the central contribution (exactly 1),
            "secondary" for all others
- summary: MAX 80 CHARACTERS — one complete informative sentence
- contentType: "figure" | "chart" | "animation"
- content: expanded content (see types below)
- conceptualOrigin: specific section, figure, or table from the paper
- whyThisCard: why this concept was selected
- styleHint: { "categoryColor": hex, "colorName": name }

CONTENT TYPES:
  figure    → use for real paper figures. Set content.assetReference = "FIG1" etc.
              Only use if the figure exists in the paper.
  chart     → use for quantitative data. Include EXACT paper values in content.data.
  animation → use for dynamic processes. Define 2-4 frames, each with label
              (max 20 chars), description (max 120 chars).

CATEGORY COLORS:
  contribution: #FFB800  method: #00D4FF  problem: #FF4444
  metric: #00FF88  limitation: #4A5568  dataset: #8B5CF6  result: #FFFFFF

RULES:
1. Exactly 1 card must be priority="primary" (the central contribution)
2. At least 1 chart card with real paper values if quantitative data exists
3. At least 1 figure card if paper figures are referenced (FIG1, FIG2...)
4. card_01 must be the primary card

Return ONLY valid JSON in this format:
{
  "paperTitle": "string",
  "centralContribution": "string",
  "cardCount": 5,
  "cards": [ ... ]
}
```

---

## WEB-V2-STEP1 — Extraction (attach PDF)

```
You are a scientific paper analyst specializing in identifying conceptual
elements that can be materialized as interactive educational cards.

Read the attached paper and extract between 8 and 10 conceptual elements.

For each element identify:
- name: short descriptive name
- category: problem | method | dataset | metric | result | contribution |
            limitation | character | artifact | relation
- description: what it is in the context of this paper (1-2 sentences)
- relevanceScore: 1-10 indicating centrality to the paper's contribution
- justification: why it matters for someone trying to understand the paper

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
      "justification": "string"
    }
  ]
}
```

---

## WEB-V2-STEP2 — Card generation (same conversation, no PDF needed)

```
Based on the elements you extracted, produce a Card Manifest with exactly
5 self-contained information cards for an interactive Unity experience.

GUIDING PRINCIPLE: Each card must be independently understandable. A person
who picks up any single card should be able to explain what it represents
in the paper and why it matters.

════════════════════════════════
CONTENT TYPES
════════════════════════════════

figure    — for real paper figures. Set content.assetReference = "FIG1" etc.
            ALWAYS prefer this when a relevant figure exists.
            Never use if no figure is available.

chart     — for quantitative data from the paper.
            ALWAYS include EXACT paper values in content.data.
            Supported: bar, grouped_bar, table, comparison_table.

animation — for sequential processes and pipelines.
            2 to 4 frames. Each frame: label (≤20 chars), description (≤120 chars).
            transitionType: "fade" or "slide". looping: true or false.

════════════════════════════════
CATEGORY COLORS
════════════════════════════════

contribution: #FFB800 (golden amber)   method: #00D4FF (cyan blue)
problem: #FF4444 (coral red)           metric: #00FF88 (neon green)
limitation: #4A5568 (bluish grey)      dataset: #8B5CF6 (luminous purple)
result: #FFFFFF (bright white)

════════════════════════════════
CRITICAL CONSTRAINTS
════════════════════════════════

title   → MAX 30 CHARACTERS. Count every character including spaces.
summary → MAX 80 CHARACTERS. One complete informative sentence.

════════════════════════════════
SELECTION RULES
════════════════════════════════

1. Exactly 1 card with priority="primary" (the central contribution)
2. card_01 must always be the primary card
3. At least 1 chart card if quantitative data exists in the paper
4. At least 1 figure card if paper figures exist (FIG1, FIG2...)
5. Variety of contentType — avoid 4+ cards of the same type

Return ONLY valid JSON:
{
  "paperTitle": "string",
  "centralContribution": "string",
  "cardCount": 5,
  "cards": [
    {
      "id": "card_01",
      "title": "string (≤30 chars)",
      "category": "string",
      "priority": "primary | secondary",
      "summary": "string (≤80 chars)",
      "contentType": "figure | chart | animation",
      "content": { ... },
      "conceptualOrigin": "section, figure, or table from the paper",
      "whyThisCard": "string",
      "styleHint": { "categoryColor": "hex", "colorName": "string" }
    }
  ]
}
```

---

## Unity MCP prompt — 2D UI version

```
Create a Unity scene called "PaperCave_Cards_2D" implementing the Card
Manifest below as interactive 2D UI cards using Unity UI (Canvas).

PAPER FIGURES:
Assets/PaperFigures/ contains: FIG1.png, FIG2.png, FIG3.png, FIG4.png
Reference figures by their assetReference field value + ".png".

════════════════════════════════════════════════════════
SCENE SETUP
════════════════════════════════════════════════════════

1. Create a Canvas (Screen Space — Overlay, 1920x1080 reference resolution)
2. Add an EventSystem
3. Set background color to #0A1628 (dark blue)
4. Add a horizontal LayoutGroup or free-position the cards with generous spacing

════════════════════════════════════════════════════════
CARD PREFAB RULES
════════════════════════════════════════════════════════

Each card is a Panel with two child GameObjects:
  - CollapsedView  (active by default)
  - ExpandedView   (inactive by default, enabled on click)

A Button component on the root Panel toggles between views.
The card must also be draggable — add a basic drag handler script.

COLLAPSED VIEW layout (always visible):
  - Category badge: small colored label (use styleHint.categoryColor),
    10pt font, category text in UPPERCASE
  - Title: 14pt font, white, bold. MAX 30 CHARS — truncate with ellipsis if longer
  - Summary: 11pt font, white at 80% opacity. MAX 80 CHARS — wrap to 2 lines max

EXPANDED VIEW layout (shown on click):
  Render content based on contentType:

  figure →
    - Image component displaying the file at assetReference + ".png"
    - Caption text below: 10pt, white at 70% opacity, italic, max 2 lines
    - Description text below: 11pt, white, max 4 lines

  chart →
    Based on content.chartType:
    bar / grouped_bar:
      - Render vertical bars as UI RectTransforms scaled to value
      - Bar color: styleHint.categoryColor
      - Labels below bars: 9pt, white. MAX 12 CHARS PER LABEL — abbreviate if needed
      - Y-axis values on left: 9pt, white at 70% opacity
      - If threshold exists: horizontal line with label
      - If average exists: dashed horizontal line
    table / comparison_table:
      - GridLayoutGroup with alternating row opacity (100% / 60%)
      - Header row: bold, 10pt, styleHint.categoryColor background
      - Data cells: 9pt, white
      - Column headers: MAX 15 CHARS — abbreviate if needed
      - Cell values: MAX 20 CHARS per cell
    Description text below chart: 10pt, white at 80% opacity, max 3 lines

  animation →
    - Show one frame at a time with Previous/Next buttons
    - Frame label: 12pt, bold, white, centered at top
    - If frame has assetReference: show image; otherwise show description text
    - Description text: 11pt, white, centered, max 3 lines
    - Frame counter: "1 / N" in 9pt, white at 60% opacity
    - transitionType="fade": alpha tween between frames (0.2s)
    - transitionType="slide": RectTransform slide (0.2s)
    - If looping=true and no user input: auto-advance every 3 seconds

CARD SIZING:
  - primary card: 320 x 420 px
  - secondary cards: 260 x 360 px
  - Collapsed height: 80 px (all cards)
  - Expanded height: full card height

CARD BORDER:
  Outline component with color = styleHint.categoryColor, width = 2px

════════════════════════════════════════════════════════
DRAG BEHAVIOR
════════════════════════════════════════════════════════

Add a script implementing IDragHandler and IBeginDragHandler:
- OnBeginDrag: bring card to front (SetAsLastSibling)
- OnDrag: follow pointer position
- Cards do not snap to any grid — free positioning

════════════════════════════════════════════════════════
CARD MANIFEST
════════════════════════════════════════════════════════

{PASTE CARD MANIFEST JSON HERE}
```

---

## Unity MCP prompt — 3D world-space version

```
Create a Unity scene called "PaperCave_Cards_3D" implementing the Card
Manifest below as interactive 3D card objects in world space.

PAPER FIGURES:
Assets/PaperFigures/ contains: FIG1.png, FIG2.png, FIG3.png, FIG4.png
Reference figures by their assetReference field value + ".png".

════════════════════════════════════════════════════════
SCENE SETUP
════════════════════════════════════════════════════════

1. Main Camera at position (0, 1.6, -6), looking toward origin
2. Ambient light: directional, color #1A2A4A, intensity 0.4
3. Add a Point Light at (0, 3, 0), color white, intensity 1.0
4. Background color: #0A1628 (dark blue)
5. Add a World Space Canvas on each card (see below)

════════════════════════════════════════════════════════
CARD OBJECT RULES
════════════════════════════════════════════════════════

Each card is a 3D GameObject with:
  - A Quad as the card face (front only — backface culling enabled)
  - A World Space Canvas child for UI content
  - A thin box Collider for click detection
  - A Rigidbody (isKinematic=true) for physics-based drag

CARD DIMENSIONS (world units):
  - primary card:    1.6 x 2.2 x 0.02
  - secondary cards: 1.3 x 1.8 x 0.02

CARD MATERIAL:
  Front face: dark blue (#0A1628) base material
  Edge/border: emissive material using styleHint.categoryColor, intensity 1.5
  Create a thin border by adding 4 thin elongated quads around the card edge

COLLAPSED STATE (default):
  The World Space Canvas shows:
  - Category badge: small plane with colored material (styleHint.categoryColor)
    and TextMeshPro label in UPPERCASE, 8pt equivalent
  - Title: TextMeshPro, 12pt equivalent, white, bold
    MAX 30 CHARS — if longer, truncate with ellipsis
  - Summary: TextMeshPro, 9pt equivalent, white at 80% opacity
    MAX 80 CHARS — wrap to 2 lines maximum

EXPANDED STATE (on click — card scales up 1.4x and floats forward 0.5 units):
  The canvas switches to expanded content based on contentType:

  figure →
    - RawImage component showing the figure PNG
    - Caption TextMeshPro below: 8pt equivalent, italic, white at 70%
    - Description TextMeshPro: 9pt equivalent, white, max 4 lines

  chart →
    bar / grouped_bar:
      - Render bars as scaled thin Quads, color = styleHint.categoryColor
      - Labels as small TextMeshPro objects below each bar: 7pt equivalent
        MAX 12 CHARS PER LABEL — abbreviate if needed
      - If threshold: horizontal thin Quad (white, semi-transparent)
      - Description TextMeshPro below: 8pt equivalent, max 3 lines
    table / comparison_table:
      - TextMeshPro with rich text formatting
      - Header row: bold, categoryColor hex in <color> tag
      - Data rows: normal weight, white
      - Column headers: MAX 15 CHARS  |  Cell values: MAX 20 CHARS

  animation →
    - One frame visible at a time
    - Frame label: TextMeshPro centered top, 10pt equivalent, bold
    - If frame has assetReference: RawImage; otherwise: description TextMeshPro
    - Description: 9pt equivalent, centered, max 3 lines
    - Two small 3D button planes (Previous / Next) at card bottom
    - Frame counter: "1 / N", 7pt equivalent, white at 60% opacity
    - Auto-advance every 3s if looping=true and no interaction

POINT LIGHT ON PRIMARY CARD:
  Add a Point Light child to card_01 (primary),
  color = #FFB800, intensity 0.8, range 2.0
  This highlights the most important card in 3D space

════════════════════════════════════════════════════════
LAYOUT
════════════════════════════════════════════════════════

Position cards in a slight arc facing the camera:
- card_01 (primary): position (0, 0, 0) — center
- card_02: position (-2.0, -0.3, 0.2), slight Y rotation toward center
- card_03: position (2.0, -0.3, 0.2), slight Y rotation toward center
- card_04: position (-1.0, -1.8, 0.3)
- card_05: position (1.0, -1.8, 0.3)

For more than 5 cards, continue the arc pattern outward.

DRAG BEHAVIOR:
  On mouse/pointer down: card detaches from arc position
  On drag: card follows pointer in world space (raycast to a plane at z=0)
  On release: card stays at new position (no snap)
  Dragging brings card forward in Z (z = -0.5) while held

════════════════════════════════════════════════════════
CARD MANIFEST
════════════════════════════════════════════════════════

{PASTE CARD MANIFEST JSON HERE}
```
