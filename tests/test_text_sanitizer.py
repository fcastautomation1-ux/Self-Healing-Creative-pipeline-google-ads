import pytest
from creative_pipeline.engines.text_sanitizer import TextSanitizer
from creative_pipeline.models.schemas import CreativeType, TextSanitizeRequest


@pytest.fixture
def sanitizer():
    return TextSanitizer(headline_max=30, description_max=90)


class TestTextSanitizerEmojis:
    @pytest.mark.parametrize(
        "input_text,expected_sub",
        [
            ("Edit Photos 📸", "Edit Photos"),
            ("🚀 Super Fast Tool", "Super Fast Tool"),
            ("Best App Ever! 🎉🔥", "Best App Ever"),
            ("Special Discount 💯 today", "Special Discount today"),
            ("Clean UI ✨", "Clean UI"),
            ("Loved by 10k users ❤️", "Loved by 10k users"),
            ("Instant results ⚡", "Instant results"),
            ("Top rated app 🌟🌟🌟", "Top rated app"),
            ("Get it now 👇", "Get it now"),
            ("🎨 Create art easily", "Create art easily"),
        ],
    )
    def test_strip_emojis_headline(self, sanitizer, input_text, expected_sub):
        req = TextSanitizeRequest(creative_type=CreativeType.HEADLINE, text=input_text)
        res = sanitizer.sanitize(req)
        assert expected_sub in res.cleaned_text
        assert res.was_modified is True
        assert any("Removed emojis" in m for m in res.modifications)


class TestTextSanitizerProhibitedSymbols:
    @pytest.mark.parametrize(
        "input_text,expected",
        [
            ("App #1 in Store", "App 1 in Store"),
            ("Contact us @ support", "Contact us support"),
            ("5* Star Service", "5 Star Service"),
            ("Item ~ Approx", "Item Approx"),
            ("Speed ^ Power", "Speed Power"),
            ("Option A | Option B", "Option A Option B"),
            ("<Top> Quality", "Top Quality"),
            ("best_app_ever", "best app ever"),
            ("Fast + Secure", "Fast Secure"),
            ("Value = Quality", "Value Quality"),
            ("Android / iOS Ready", "Android iOS Ready"),
            ("Back \\ Slash", "Back Slash"),
            ("• Premium Features", "Premium Features"),
            ("★ Five Stars", "Five Stars"),
            ("✔ Verified Solution", "Verified Solution"),
            ("✓ Check This Out", "Check This Out"),
            ("► Watch Demo", "Watch Demo"),
            ("✦ Special Edition", "Special Edition"),
        ],
    )
    def test_strip_prohibited_symbols(self, sanitizer, input_text, expected):
        req = TextSanitizeRequest(creative_type=CreativeType.HEADLINE, text=input_text)
        res = sanitizer.sanitize(req)
        assert res.cleaned_text == expected
        assert any("prohibited symbols" in m for m in res.modifications)


class TestTextSanitizerPunctuation:
    def test_headline_no_exclamation(self, sanitizer):
        req = TextSanitizeRequest(
            creative_type=CreativeType.HEADLINE, text="Install Today!!!"
        )
        res = sanitizer.sanitize(req)
        assert "!" not in res.cleaned_text
        assert res.cleaned_text == "Install Today"
        assert any("exclamation marks" in m for m in res.modifications)

    def test_headline_no_trailing_period(self, sanitizer):
        req = TextSanitizeRequest(
            creative_type=CreativeType.HEADLINE, text="Top Rated App."
        )
        res = sanitizer.sanitize(req)
        assert res.cleaned_text == "Top Rated App"
        assert any("trailing periods" in m for m in res.modifications)

    def test_headline_repeated_question_marks(self, sanitizer):
        req = TextSanitizeRequest(
            creative_type=CreativeType.HEADLINE, text="Need Better Photos???"
        )
        res = sanitizer.sanitize(req)
        assert res.cleaned_text == "Need Better Photos?"

    def test_headline_repeated_hyphens(self, sanitizer):
        req = TextSanitizeRequest(
            creative_type=CreativeType.HEADLINE, text="Fast--Easy--Smart"
        )
        res = sanitizer.sanitize(req)
        assert "--" not in res.cleaned_text
        assert res.cleaned_text == "Fast-Easy-Smart"

    def test_description_max_one_exclamation(self, sanitizer):
        req = TextSanitizeRequest(
            creative_type=CreativeType.DESCRIPTION,
            text="Download now! Edit photos fast! Enjoy results!",
        )
        res = sanitizer.sanitize(req)
        assert res.cleaned_text.count("!") == 1
        assert any("maximum 1 exclamation" in m for m in res.modifications)

    def test_description_no_leading_exclamation(self, sanitizer):
        req = TextSanitizeRequest(
            creative_type=CreativeType.DESCRIPTION,
            text="!Great app for editing your photos on the go.",
        )
        res = sanitizer.sanitize(req)
        assert not res.cleaned_text.startswith("!")


class TestTextSanitizerCapitalization:
    def test_all_caps_headline_to_title_case(self, sanitizer):
        req = TextSanitizeRequest(
            creative_type=CreativeType.HEADLINE, text="BEST PHOTO EDITOR"
        )
        res = sanitizer.sanitize(req)
        assert res.cleaned_text == "Best Photo Editor"
        assert any("ALL-CAPS" in m for m in res.modifications)

    def test_all_caps_description_to_sentence_case(self, sanitizer):
        req = TextSanitizeRequest(
            creative_type=CreativeType.DESCRIPTION,
            text="TRY THE BEST PHOTO APP ON MOBILE TODAY.",
        )
        res = sanitizer.sanitize(req)
        assert res.cleaned_text == "Try the best photo app on mobile today."

    def test_preserve_acronyms(self, sanitizer):
        req = TextSanitizeRequest(
            creative_type=CreativeType.HEADLINE,
            text="NEW AI PHOTO TOOL IN THE US",
            preserve_acronyms=True,
        )
        res = sanitizer.sanitize(req)
        assert "AI" in res.cleaned_text
        assert "US" in res.cleaned_text
        assert res.cleaned_text == "New AI Photo Tool in the US" or "New AI Photo Tool In The US"


class TestTextSanitizerBoundaryTrimmer:
    def test_headline_trim_at_word_boundary(self, sanitizer):
        # 36 chars > 30 max
        input_text = "Advanced High Performance Photo Tool"
        req = TextSanitizeRequest(creative_type=CreativeType.HEADLINE, text=input_text)
        res = sanitizer.sanitize(req)
        assert len(res.cleaned_text) <= 30
        assert not res.cleaned_text.endswith(" ")
        # Should cleanly trim without breaking words
        assert res.cleaned_text == "Advanced High Performance"

    def test_description_trim_at_word_boundary(self, sanitizer):
        long_desc = (
            "Create stunning pictures with our automated lighting adjustments, "
            "filters, background removals and professional export options today."
        )
        req = TextSanitizeRequest(creative_type=CreativeType.DESCRIPTION, text=long_desc)
        res = sanitizer.sanitize(req)
        assert len(res.cleaned_text) <= 90
        assert not res.cleaned_text.endswith(" ")
        # Must not end with broken word or dangling punctuation
        assert res.cleaned_text[-1].isalnum() or res.cleaned_text[-1] in ".!?"


class TestProjectSpecExamples:
    def test_spec_headline_example(self, sanitizer):
        # From project specification:
        # Request: "PHOTO EDITOR #1 📸 BEST APP EVER!!!"
        # Cleaned: "Photo Editor 1 Best App Ever"
        req = TextSanitizeRequest(
            creative_type=CreativeType.HEADLINE,
            text="PHOTO EDITOR #1 📸 BEST APP EVER!!!",
        )
        res = sanitizer.sanitize(req)
        assert res.valid is True
        assert res.cleaned_text == "Photo Editor 1 Best App Ever"
        assert res.char_count == 28
        assert res.max_allowed == 30
        assert res.was_modified is True

    def test_clean_input_remains_unmodified(self, sanitizer):
        clean_headline = "Clean Photo Editor"
        req = TextSanitizeRequest(
            creative_type=CreativeType.HEADLINE, text=clean_headline
        )
        res = sanitizer.sanitize(req)
        assert res.cleaned_text == clean_headline
        assert res.was_modified is False
        assert len(res.modifications) == 0
        assert res.valid is True


class TestAdditionalEdgeCases:
    def test_currency_and_percent_preserved(self, sanitizer):
        req = TextSanitizeRequest(
            creative_type=CreativeType.HEADLINE,
            text="Save $50 on Pro Edition",
        )
        res = sanitizer.sanitize(req)
        assert "$50" in res.cleaned_text
        assert "Save $50 on Pro Edition" == res.cleaned_text

    def test_percent_preserved(self, sanitizer):
        req = TextSanitizeRequest(
            creative_type=CreativeType.HEADLINE,
            text="50% Off Today Only",
        )
        res = sanitizer.sanitize(req)
        assert "50% Off Today Only" == res.cleaned_text

    def test_exact_limit_not_trimmed(self, sanitizer):
        # Exactly 30 characters
        text_30 = "1234567890 1234567890 12345678"
        assert len(text_30) == 30
        req = TextSanitizeRequest(creative_type=CreativeType.HEADLINE, text=text_30)
        res = sanitizer.sanitize(req)
        assert len(res.cleaned_text) == 30
        assert not any("Trimmed text" in m for m in res.modifications)

    def test_apostrophe_contractions_preserved(self, sanitizer):
        req = TextSanitizeRequest(
            creative_type=CreativeType.HEADLINE,
            text="Don't Miss Today's Deals",
        )
        res = sanitizer.sanitize(req)
        assert res.cleaned_text == "Don't Miss Today's Deals"

    def test_hyphenated_words_preserved(self, sanitizer):
        req = TextSanitizeRequest(
            creative_type=CreativeType.HEADLINE,
            text="AI-Powered Photo Filter",
        )
        res = sanitizer.sanitize(req)
        assert "AI-Powered" in res.cleaned_text

    def test_multiple_spaces_collapsed(self, sanitizer):
        req = TextSanitizeRequest(
            creative_type=CreativeType.HEADLINE,
            text="Photo    Editor     Pro",
        )
        res = sanitizer.sanitize(req)
        assert res.cleaned_text == "Photo Editor Pro"
        assert res.was_modified is True

    def test_space_before_punctuation_cleaned(self, sanitizer):
        req = TextSanitizeRequest(
            creative_type=CreativeType.DESCRIPTION,
            text="High quality filters , fast processing , and easy export .",
        )
        res = sanitizer.sanitize(req)
        assert "filters, fast processing, and easy export." in res.cleaned_text

    def test_description_with_single_valid_exclamation(self, sanitizer):
        req = TextSanitizeRequest(
            creative_type=CreativeType.DESCRIPTION,
            text="Transform your photos with one click! Discover top presets today.",
        )
        res = sanitizer.sanitize(req)
        assert res.cleaned_text.count("!") == 1
        assert "Transform your photos with one click!" in res.cleaned_text

    def test_headline_strips_both_trailing_period_and_exclamation(self, sanitizer):
        req = TextSanitizeRequest(
            creative_type=CreativeType.HEADLINE,
            text="Get It Now!.",
        )
        res = sanitizer.sanitize(req)
        assert res.cleaned_text == "Get It Now"

    def test_single_long_word_hard_trimmed(self, sanitizer):
        long_word = "SupercalifragilisticexpialidociousTool"
        req = TextSanitizeRequest(creative_type=CreativeType.HEADLINE, text=long_word)
        res = sanitizer.sanitize(req)
        assert len(res.cleaned_text) <= 30


class TestBulkTextSanitization:
    def test_bulk_headlines_from_excel(self, sanitizer):
        from creative_pipeline.models.schemas import BulkTextSanitizeRequest

        raw_excel_rows = [
            "PHOTO EDITOR #1 📸 BEST APP EVER!!!",
            "Remove BG - Change Background",
            "erase background online now at home",
            "Free photo background changer",
            "Automatic Background Removal",
        ]
        req = BulkTextSanitizeRequest(
            creative_type=CreativeType.HEADLINE,
            texts=raw_excel_rows,
        )
        res = sanitizer.sanitize_bulk(req)

        assert res.total_items == 5
        assert res.compliant_items == 5
        # First row should be healed
        assert res.results[0].cleaned_text == "Photo Editor 1 Best App Ever"
        assert res.results[0].char_count <= 30
        assert "📸" not in res.results[0].cleaned_text
        assert "#" not in res.results[0].cleaned_text
        # Every item must be compliant and <= 30 chars
        for item in res.results:
            assert len(item.cleaned_text) <= 30
            assert item.valid is True

    def test_bulk_skips_empty_lines(self, sanitizer):
        from creative_pipeline.models.schemas import BulkTextSanitizeRequest

        rows = ["Valid Headline", "  ", "", "\t", "Another Great Feature"]
        req = BulkTextSanitizeRequest(creative_type=CreativeType.HEADLINE, texts=rows)
        res = sanitizer.sanitize_bulk(req)
        assert res.total_items == 2

