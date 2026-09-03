import re
import unicodedata
from typing import List, Optional, Set, Tuple

from creative_pipeline.config import settings
from creative_pipeline.models.schemas import (
    BulkTextSanitizeRequest,
    BulkTextSanitizeResponse,
    CreativeType,
    TextSanitizeRequest,
    TextSanitizeResponse,
)


class TextSanitizer:
    """Module 1: Text Auto-Fixer ('Copy Doctor') for Google Ads assets."""

    # Emojis and miscellaneous symbols regex pattern
    EMOJI_PATTERN = re.compile(
        "["
        "\U00010000-\U0010FFFF"  # Supplementary Planes (emojis, pictographs)
        "\u2600-\u27BF"          # Miscellaneous Symbols and Dingbats
        "\u2300-\u23FF"          # Miscellaneous Technical
        "\u2B50"                 # Star
        "\uFE00-\uFE0F"          # Variation Selectors
        "\u200D"                 # Zero Width Joiner
        "\u200B-\u200D"          # Zero width spaces
        "\u25A0-\u25FF"          # Geometric Shapes
        "\u2190-\u21FF"          # Arrows
        "]+",
        flags=re.UNICODE,
    )

    # Prohibited symbols in Google Ads copy
    # Note: Bullets, stars, checks, brackets, slashes, hash, at, etc.
    PROHIBITED_SYMBOLS_PATTERN = re.compile(
        r"[@#*~^|<>\_\+=\\\/•★✔✓►▶▲▼◆✦§¤¡¿`~]"
    )

    # Common acronyms that should remain uppercase
    KNOWN_ACRONYMS: Set[str] = {
        "US", "USA", "UK", "EU", "AI", "ML", "3D", "4K", "HD", "VR", "AR",
        "UI", "UX", "SEO", "PPC", "ROI", "B2B", "B2C", "API", "SDK", "PRO",
        "VIP", "GPS", "PDF", "PC", "MAC", "iOS", "CTA", "CRM", "SaaS", "CMS"
    }

    def __init__(
        self,
        headline_max: int = settings.HEADLINE_MAX_LENGTH,
        description_max: int = settings.DESCRIPTION_MAX_LENGTH,
    ):
        self.headline_max = headline_max
        self.description_max = description_max

    def sanitize(self, request: TextSanitizeRequest) -> TextSanitizeResponse:
        """Sanitizes and heals input text according to Google Ads policies."""
        original = request.text
        text = original
        modifications: List[str] = []

        max_allowed = request.max_length or (
            self.headline_max
            if request.creative_type == CreativeType.HEADLINE
            else self.description_max
        )

        # 1. Strip Prohibited Symbols
        text, removed_symbols = self._strip_prohibited_symbols(text)
        if removed_symbols:
            modifications.append(
                f"Removed prohibited symbols: {' '.join(sorted(set(removed_symbols)))}"
            )

        # 2. Strip Emojis and pictographs
        text, removed_emojis = self._strip_emojis(text)
        if removed_emojis:
            modifications.append(f"Removed emojis: {''.join(removed_emojis)}")

        # 3. Fix Repetitive & Illegal Punctuation
        text, punct_mods = self._fix_punctuation(text, request.creative_type)
        modifications.extend(punct_mods)

        # 4. Normalize Capitalization (Excessive ALL-CAPS)
        text, cap_mods = self._normalize_capitalization(
            text, request.creative_type, request.preserve_acronyms
        )
        modifications.extend(cap_mods)

        # 5. Clean whitespace before length check
        text = self._normalize_whitespace(text)

        # 6. Intelligent Word-Boundary Trimmer
        if len(text) > max_allowed:
            text, trim_mod = self._trim_to_word_boundary(text, max_allowed)
            if trim_mod:
                modifications.append(trim_mod)

        # Final cleanup of trailing/leading punctuation resulting from trims
        text = self._clean_boundary_punctuation(text, request.creative_type)

        was_modified = text != original
        char_count = len(text)
        valid = char_count > 0 and char_count <= max_allowed

        return TextSanitizeResponse(
            valid=valid,
            original_text=original,
            cleaned_text=text,
            was_modified=was_modified,
            modifications=modifications,
            char_count=char_count,
            max_allowed=max_allowed,
        )

    def _strip_emojis(self, text: str) -> Tuple[str, List[str]]:
        removed = self.EMOJI_PATTERN.findall(text)
        cleaned = self.EMOJI_PATTERN.sub(" ", text)
        return cleaned, removed

    def _strip_prohibited_symbols(self, text: str) -> Tuple[str, List[str]]:
        removed = self.PROHIBITED_SYMBOLS_PATTERN.findall(text)
        # Replace prohibited symbols with space so adjacent words don't merge
        cleaned = self.PROHIBITED_SYMBOLS_PATTERN.sub(" ", text)
        return cleaned, removed

    def _fix_punctuation(
        self, text: str, creative_type: CreativeType
    ) -> Tuple[str, List[str]]:
        mods: List[str] = []

        # Normalize repeated question marks: ??? -> ?
        if re.search(r"\?{2,}", text):
            text = re.sub(r"\?{2,}", "?", text)
            mods.append("Normalized repeated question marks to single '?'")

        # Normalize repeated hyphens/dashes: -- -> -
        if re.search(r"-{2,}", text):
            text = re.sub(r"-{2,}", "-", text)
            mods.append("Normalized repeated hyphens to single '-'")

        # Normalize multiple periods/ellipses: .... -> ...
        if re.search(r"\.{4,}", text):
            text = re.sub(r"\.{4,}", "...", text)
            mods.append("Normalized excessive dots")

        if creative_type == CreativeType.HEADLINE:
            # Google Ads Editorial: No exclamation marks in headlines
            if "!" in text:
                text = text.replace("!", "")
                mods.append("Removed exclamation marks (prohibited in headlines)")

            # Trailing periods prohibited in headlines
            if text.rstrip().endswith("."):
                text = text.rstrip()
                while text.endswith("."):
                    text = text[:-1]
                mods.append("Strips trailing periods (prohibited in headlines)")

        elif creative_type == CreativeType.DESCRIPTION:
            # Descriptions: Max ONE exclamation mark in entire description, never at start
            excl_count = text.count("!")
            if excl_count > 1:
                # Keep only the first occurrence or normalize
                # Often people put '!!!' at the end; collapse multiple '!' to single '!'
                text = re.sub(r"!{2,}", "!", text)
                # If still multiple across different sentences, keep first
                if text.count("!") > 1:
                    parts = text.split("!")
                    # Keep first exclamation, convert subsequent to periods
                    text = parts[0] + "!" + ".".join(parts[1:])
                mods.append("Enforced maximum 1 exclamation mark in description")

            # Cannot start with exclamation mark
            if text.lstrip().startswith("!"):
                text = text.lstrip()[1:]
                mods.append("Removed leading exclamation mark")

        return text, mods

    def _normalize_capitalization(
        self, text: str, creative_type: CreativeType, preserve_acronyms: bool
    ) -> Tuple[str, List[str]]:
        mods: List[str] = []
        words = text.split()
        if not words:
            return text, mods

        # Check for excessive ALL CAPS (e.g. >= 50% words in ALL CAPS with > 1 char)
        upper_words = [
            w for w in words
            if w.isupper() and len(re.sub(r"\W+", "", w)) > 1
        ]
        
        has_excessive_caps = len(upper_words) >= 2 or (
            len(words) <= 3 and len(upper_words) >= 1 and any(len(w) > 3 for w in upper_words)
        )

        if has_excessive_caps:
            new_words = []
            for i, word in enumerate(words):
                clean_word = re.sub(r"[^\w]", "", word)
                
                # Check if this word is a recognized acronym to preserve
                if preserve_acronyms and clean_word.upper() in self.KNOWN_ACRONYMS:
                    new_words.append(word)
                    continue

                if word.isupper() and len(clean_word) > 1:
                    if creative_type == CreativeType.HEADLINE:
                        # Convert to Title Case for headline
                        new_words.append(word.capitalize())
                    else:
                        # Convert to lowercase unless it's first word or follows a period
                        if i == 0 or (i > 0 and new_words[i - 1].endswith((".", "!", "?"))):
                            new_words.append(word.capitalize())
                        else:
                            new_words.append(word.lower())
                else:
                    new_words.append(word)

            rebuilt = " ".join(new_words)
            if rebuilt != text:
                text = rebuilt
                case_target = (
                    "Title Case" if creative_type == CreativeType.HEADLINE else "Sentence Case"
                )
                mods.append(f"Converted ALL-CAPS to {case_target}")

        return text, mods

    def _normalize_whitespace(self, text: str) -> str:
        # Collapse multi-spaces and strip leading/trailing spaces
        text = re.sub(r"\s+", " ", text).strip()
        # Clean space before punctuation: 'word , other' -> 'word, other'
        text = re.sub(r"\s+([,.?!:;])", r"\1", text)
        return text

    def _trim_to_word_boundary(
        self, text: str, max_allowed: int
    ) -> Tuple[str, Optional[str]]:
        if len(text) <= max_allowed:
            return text, None

        orig_len = len(text)
        candidate = text[:max_allowed]

        # Find the last space within candidate
        last_space_idx = candidate.rfind(" ")
        if last_space_idx != -1:
            trimmed = candidate[:last_space_idx].rstrip(" ,;:-")
        else:
            # If no space (single very long word), hard truncate
            trimmed = candidate

        mod = f"Trimmed text to fit max length from {orig_len} to {len(trimmed)} chars"
        return trimmed, mod

    def _clean_boundary_punctuation(
        self, text: str, creative_type: CreativeType
    ) -> str:
        text = text.strip()
        # Strip illegal leading punctuation
        text = re.sub(r"^[\s,.?!:;\-]+", "", text).strip()

        # For headlines, strip trailing periods and hyphens
        if creative_type == CreativeType.HEADLINE:
            text = re.sub(r"[\s,.!:\-]+$", "", text).strip()
        else:
            # For descriptions, strip trailing hyphens or commas
            text = re.sub(r"[\s,:\-]+$", "", text).strip()

        return text

    def sanitize_bulk(self, request: BulkTextSanitizeRequest) -> BulkTextSanitizeResponse:
        """Sanitizes a batch of raw texts (e.g., pasted lines from an Excel or Google Sheets column)."""
        results: List[TextSanitizeResponse] = []
        for line in request.texts:
            cleaned_line = line.strip()
            if not cleaned_line:
                continue
            item_req = TextSanitizeRequest(
                creative_type=request.creative_type,
                text=cleaned_line,
                preserve_acronyms=request.preserve_acronyms,
                max_length=request.max_length,
            )
            results.append(self.sanitize(item_req))

        compliant = sum(1 for r in results if r.valid)
        modified = sum(1 for r in results if r.was_modified)

        return BulkTextSanitizeResponse(
            total_items=len(results),
            compliant_items=compliant,
            modified_items=modified,
            results=results,
        )
