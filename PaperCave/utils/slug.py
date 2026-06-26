"""
utils/slug.py
Converts arbitrary folder/file names into safe ASCII identifiers (paper_ids).

Rules applied in order:
  1. NFKD unicode normalization → decomposes combined chars (é → e + combining accent)
  2. Encode to ASCII, ignoring non-ASCII bytes → strips accents and other non-ASCII
  3. Lowercase
  4. Replace any run of [spaces, hyphens, dots] with a single underscore
  5. Remove any remaining character that is not [a-z0-9_]
  6. Collapse multiple consecutive underscores into one
  7. Strip leading/trailing underscores
  8. Truncate to max_len characters (default 60)
  9. If the result is empty, return "paper"

Examples:
  "Generative AI for Facial Expressions in 3D Game"
      → "generative_ai_for_facial_expressions_in_3d_game"

  "Um editor de árvores de decisão para construção de jogos"
      → "um_editor_de_arvores_de_decisao_para_construcao_de_jogos"

  "1-s2.0-S111001682401278X-main"
      → "1_s2_0_s111001682401278x_main"

  "ACM_ICSE_Designing_2026"
      → "acm_icse_designing_2026"

  "07586260"
      → "07586260"
"""
import re
import unicodedata


def slugify(name: str, max_len: int = 60) -> str:
    # 1. NFKD → decompose accented characters
    normalized = unicodedata.normalize("NFKD", name)
    # 2. Drop non-ASCII bytes (removes combining accent characters)
    ascii_only = normalized.encode("ascii", errors="ignore").decode("ascii")
    # 3. Lowercase
    lower = ascii_only.lower()
    # 4. Spaces, hyphens, dots → underscore
    underscored = re.sub(r"[ \-\.]+", "_", lower)
    # 5. Remove anything that's not alphanumeric or underscore
    clean = re.sub(r"[^a-z0-9_]", "", underscored)
    # 6. Collapse multiple underscores
    clean = re.sub(r"_+", "_", clean)
    # 7. Strip leading/trailing underscores
    clean = clean.strip("_")
    # 8. Truncate
    clean = clean[:max_len]
    # 9. Fallback
    return clean or "paper"
