"""
models/schemas.py
Pydantic schemas for all agent outputs.

v5 (Unit system — matches Prompt Library v2):
  - Unit replaces Card: supports type="card" | type="stack"
  - Stacks have 2-4 items; individual cards are always single units
  - contentType adds "table" and "text_panel"
  - id format: unit_01, unit_02, ...
  - UnitManifest / ReviewedUnitManifest replace CardManifest / ReviewedCardManifest
  - Old Card/CardManifest/ReviewedCardManifest kept as aliases for backward compat
    with existing 07_reviewer_output.json files from v4 runs.
"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Any, Dict, List, Literal, Optional


# ── Classifier output (v2 legacy) ─────────────────────────────────────────────

class PaperProfile(BaseModel):
    paperTitle: str
    domain: str
    centralContribution: Literal[
        "framework", "algorithm", "evaluation", "system", "survey", "game"
    ]
    hasImplementation: bool
    hasMeasurableMetrics: bool
    isAboutGames: bool
    implementsGame: bool
    gameStructure: Literal[
        "exploration", "sequential", "comparative", "parametric",
        "observational", "none"
    ]
    interactionPotential: Literal["high", "medium", "low"]
    keyConcepts: List[str] = Field(max_length=5)
    suggestedTemplate: Literal["T1", "T2", "T3", "T4", "T5"]
    templateRationale: str

    @model_validator(mode="after")
    def enforce_game_structure(self) -> "PaperProfile":
        if not self.implementsGame:
            self.gameStructure = "none"
        return self


# ── Designer output (v2 legacy) ────────────────────────────────────────────────

class NarrativeFrame(BaseModel):
    openingContext: str
    centralChallenge: str
    resolution: str


class Objective(BaseModel):
    index: int
    description: str
    mappedConcept: str = Field(description="which paper concept this step represents")
    completionTrigger: str = Field(description="condition that marks progress to the next step")


class KeyObject(BaseModel):
    type: str
    role: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    interactionNote: str = ""


class MediaWindowOutline(BaseModel):
    mode: Literal["image", "lottie", "chart"]
    contentDescription: str


class AreaOutline(BaseModel):
    areaId: str
    label: str
    purpose: str
    keyObjects: List[KeyObject]
    mediaWindows: List[MediaWindowOutline] = []


class DesignPlan(BaseModel):
    templateId: Literal["T1", "T2", "T3", "T4", "T5"]
    templateRationale: str
    perspective: Literal["first_person", "third_person", "top_down"]
    perspectiveRationale: str
    narrativeFrame: NarrativeFrame
    objectives: List[Objective] = Field(min_length=1, max_length=3)
    areaOutline: List[AreaOutline] = Field(min_length=1, max_length=3)
    designNotes: str = ""


# ── Image pipeline schemas (v3) ────────────────────────────────────────────────

class ImageContext(BaseModel):
    """Metadata of an image extracted from the PDF by the Reader."""
    raw_filename: str
    page: int
    caption: str = ""
    context_before: str = ""
    context_after: str = ""
    width_px: int = 0
    height_px: int = 0


class SelectedImage(BaseModel):
    """Image chosen by the Image Selector (legacy — Image Selector removed in v5)."""
    filename: str
    raw_filename: str
    caption: str = ""
    selection_justification: str


class ImageSelection(BaseModel):
    """Output of the Image Selector (legacy)."""
    selected: List[SelectedImage] = Field(max_length=3)


class ImageInsight(BaseModel):
    """Vision Analyst output for one figure."""
    filename: str
    description: str
    relevance: str
    mode: Literal["visual", "text_inferred"]
    visualType: Literal["photo_or_screenshot", "chart_or_graph", "diagram_or_flowchart", "table_image"]


class ImageInsights(BaseModel):
    """Full Vision Analyst output."""
    insights: List[ImageInsight]


CONTENT_TYPES = Literal["figure", "chart", "table", "animation", "text_panel"]
CATEGORIES    = Literal[
    "graphical_representation", "abstract", "contribution",
    "image", "graph", "table"
]


class ConceptualElement(BaseModel):
    name: str
    category: CATEGORIES
    description: str
    relevanceScore: int = Field(ge=1, le=10)
    justification: str
    groupingHint: Optional[str] = None


class ExtractionResult(BaseModel):
    paperTitle: str
    centralContribution: str
    elements: List[ConceptualElement] = Field(min_length=8, max_length=10)


# ── Shared content block (v4 / v5) ────────────────────────────────────────────

class CardStyleHint(BaseModel):
    categoryColor: str = Field(description="Hex color for this category")
    colorName: str     = Field(description="Human-readable color name")


class AnimationFrame(BaseModel):
    index: int
    label: str       = Field(max_length=20)
    description: str = Field(max_length=120)
    assetReference: Optional[str] = None


class CardContent(BaseModel):
    """
    Union-style content block. Fields used depend on contentType:
      figure      → assetReference, caption, description
      chart       → chartType, title, description, data
      table       → chartType ("table"/"comparison_table"), title, description, data
      animation   → description, frameCount, frames, transitionType, looping
      text_panel  → description
    """
    # figure / animation fields
    assetReference: Optional[str]  = None
    caption:        Optional[str]  = None

    # shared description (required for all types)
    description: str = ""

    # chart / table fields
    chartType: Optional[Literal["bar", "grouped_bar", "table", "comparison_table"]] = None
    title:     Optional[str]            = None
    data:      Optional[Dict[str, Any]] = None

    # animation fields
    frameCount:     Optional[int]                = None
    frames:         Optional[List[AnimationFrame]] = None
    transitionType: Optional[Literal["fade", "slide"]] = None
    looping:        Optional[bool]               = None

    @model_validator(mode="after")
    def validate_description_present(self) -> "CardContent":
        if not self.description:
            raise ValueError("CardContent.description must not be empty")
        return self


# ── v5 Unit system (Prompt Library v2) ────────────────────────────────────────


class StackItem(BaseModel):
    """An individual item inside a stack unit."""
    index:       int
    title:       str = Field(max_length=30)
    contentType: CONTENT_TYPES
    content:     CardContent


class Unit(BaseModel):
    """
    A draggable unit in the Paper Cave experience.
    type="card"  → single card with one content item.
    type="stack" → 2-4 card items grouped as one draggable piece.
    """
    id:       str
    type:     Literal["card", "stack"] = "card"
    priority: Literal["primary", "secondary"]

    # card fields
    title:           Optional[str]         = Field(None, max_length=30)
    category:        Optional[CATEGORIES]  = None
    summary:         Optional[str]         = None

    @field_validator("summary", mode="before")
    @classmethod
    def truncate_summary(cls, v):
        """Truncate summary to 80 chars instead of raising a validation error."""
        if v and len(v) > 80:
            return v[:77] + "..."
        return v
    contentType:     Optional[CONTENT_TYPES] = None
    content:         Optional[CardContent] = None
    conceptualOrigin: Optional[str]        = None
    whyThisUnit:     str                   = ""

    # stack fields
    stackLabel: Optional[str] = Field(None, max_length=30)
    items:      Optional[List[StackItem]] = None

    styleHint: CardStyleHint

    @model_validator(mode="after")
    def validate_by_type(self) -> "Unit":
        if self.type == "card":
            if not self.title:
                raise ValueError(f"Unit '{self.id}' (card) must have a title")
            if not self.contentType:
                raise ValueError(f"Unit '{self.id}' (card) must have a contentType")
            if self.content is None:
                raise ValueError(f"Unit '{self.id}' (card) must have content")
            if self.contentType == "figure" and not self.content.assetReference:
                raise ValueError(
                    f"Unit '{self.id}' has contentType='figure' but "
                    f"content.assetReference is null. Only use figure when a FIG*.png exists."
                )
            if self.contentType == "chart" and not self.content.data:
                raise ValueError(
                    f"Unit '{self.id}' has contentType='chart' but content.data is null."
                )
            if self.contentType == "table" and not self.content.data:
                raise ValueError(
                    f"Unit '{self.id}' has contentType='table' but content.data is null."
                )
            if self.contentType == "animation":
                frames = self.content.frames or []
                if len(frames) < 2:
                    raise ValueError(
                        f"Unit '{self.id}' has contentType='animation' but fewer than 2 frames."
                    )
        elif self.type == "stack":
            if not self.stackLabel:
                raise ValueError(f"Unit '{self.id}' (stack) must have a stackLabel")
            if not self.category:
                raise ValueError(f"Unit '{self.id}' (stack) must have a category")
            items = self.items or []
            if len(items) < 2 or len(items) > 4:
                raise ValueError(
                    f"Unit '{self.id}' (stack) must have 2-4 items, got {len(items)}"
                )
        return self

    @property
    def display_name(self) -> str:
        """Human-readable name for logging/scoring."""
        return self.title or self.stackLabel or self.id


class UnitManifest(BaseModel):
    """Mapper output — v5 unit system."""
    paperTitle:          str
    centralContribution: str
    unitCount:           int = Field(ge=2, le=20)
    units:               List[Unit]

    @model_validator(mode="after")
    def validate_unit_count_matches(self) -> "UnitManifest":
        if len(self.units) != self.unitCount:
            raise ValueError(
                f"unitCount={self.unitCount} but {len(self.units)} units provided"
            )
        return self

    @model_validator(mode="after")
    def validate_exactly_one_primary(self) -> "UnitManifest":
        primaries = [u for u in self.units if u.priority == "primary"]
        if len(primaries) != 1:
            raise ValueError(
                f"Exactly 1 unit must have priority='primary'. Found: {len(primaries)}"
            )
        return self


# ── Reviewer output (v3/v4/v5) ────────────────────────────────────────────────

class ObjectScore(BaseModel):
    suggestedName:   str
    score:           float = Field(ge=0.0, le=1.0)
    confidence:      Literal["high", "medium", "low"]
    feedback:        str


class ReviewResult(BaseModel):
    attempt:         int
    approved:        bool
    objectScores:    List[ObjectScore]
    overallFeedback: str


class ImplementationNotes(BaseModel):
    """Paths and hints for the Unity developer."""
    paperFiguresPath: str = "Assets/PaperCaveData/{paper_id}/images/"
    manifestPath:     str = "Assets/PaperCaveData/{paper_id}/manifest.json"
    styleGuide:       str = "See INTEGRATION_PLAN_V2.md Section 3 — Card Defaults"
    sceneLayout:      str = (
        "Place priority='primary' unit at (0, 0, 0). "
        "Arrange secondary units in an arc. "
        "Use PaperCaveManifestLoader via Tools > PaperCave > Build Cards From Manifest..."
    )


class ReviewedUnitManifest(BaseModel):
    """Final pipeline output — best unit manifest assembled from all Mapper attempts."""
    paperTitle:                    str
    centralContribution:           str
    unitCount:                     int
    units:                         List[Unit]
    objectScores:                  List[ObjectScore]
    totalAttempts:                 int
    assembledFromMultipleAttempts: bool
    implementationNotes:           ImplementationNotes = Field(
        default_factory=ImplementationNotes
    )


# ── v4 backward compatibility aliases ─────────────────────────────────────────
# These allow --from-step to load outputs from previous v4 runs.
# New code should use Unit / UnitManifest / ReviewedUnitManifest.

class Card(BaseModel):
    """v4 Card schema — kept for loading legacy 07_reviewer_output.json files."""
    id:              str
    title:           str
    category:        str
    priority:        Literal["primary", "secondary"]
    summary:         str
    contentType:     Literal["figure", "chart", "table", "animation", "text_panel"]
    content:         CardContent
    conceptualOrigin: str = ""
    whyThisCard:     str  = ""
    styleHint:       CardStyleHint

    def to_unit(self) -> Unit:
        """Convert a legacy Card to a Unit for use in the new pipeline."""
        return Unit(
            id=self.id.replace("card_", "unit_"),
            type="card",
            priority=self.priority,
            title=self.title,
            category=self.category,
            summary=self.summary,
            contentType=self.contentType,
            content=self.content,
            conceptualOrigin=self.conceptualOrigin,
            whyThisUnit=self.whyThisCard,
            styleHint=self.styleHint,
        )


class CardManifest(BaseModel):
    """v4 CardManifest — kept for loading legacy outputs."""
    paperTitle:          str
    centralContribution: str
    cardCount:           int
    cards:               List[Card]

    def to_unit_manifest(self) -> UnitManifest:
        return UnitManifest(
            paperTitle=self.paperTitle,
            centralContribution=self.centralContribution,
            unitCount=self.cardCount,
            units=[c.to_unit() for c in self.cards],
        )


class ReviewedCardManifest(BaseModel):
    """v4 ReviewedCardManifest — kept for loading legacy outputs."""
    paperTitle:                    str
    centralContribution:           str
    cardCount:                     int
    cards:                         List[Card]
    objectScores:                  List[ObjectScore]
    totalAttempts:                 int
    assembledFromMultipleAttempts: bool
    implementationNotes:           ImplementationNotes = Field(
        default_factory=ImplementationNotes
    )

    def to_reviewed_unit_manifest(self) -> ReviewedUnitManifest:
        return ReviewedUnitManifest(
            paperTitle=self.paperTitle,
            centralContribution=self.centralContribution,
            unitCount=self.cardCount,
            units=[c.to_unit() for c in self.cards],
            objectScores=self.objectScores,
            totalAttempts=self.totalAttempts,
            assembledFromMultipleAttempts=self.assembledFromMultipleAttempts,
            implementationNotes=self.implementationNotes,
        )
