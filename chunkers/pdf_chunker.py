from __future__ import annotations

import re
from typing import Optional

from chunkers.base_chunker import BaseChunker


class PDFChunker(BaseChunker):
    BOILERPLATE_PATTERNS = (
        re.compile(r"^Not Recommended For New Designs(?: \(NRND\))?$", re.IGNORECASE),
        re.compile(r"^GoBack$", re.IGNORECASE),
        re.compile(r"^Contents$", re.IGNORECASE),
        re.compile(r"^List of Tables$", re.IGNORECASE),
        re.compile(r"^List of Figures$", re.IGNORECASE),
        re.compile(r"^Chapter \d+ .*$", re.IGNORECASE),
    )

    def __init__(
        self,
        target_words_min: int = 40,
        target_words_max: int = 120,
        hard_word_limit: int = 180,
        sentence_overlap: int = 1,
        line_group_size: int = 3,
    ) -> None:
        self.target_words_min = target_words_min
        self.target_words_max = target_words_max
        self.hard_word_limit = hard_word_limit
        self.sentence_overlap = sentence_overlap
        self.line_group_size = line_group_size

    def chunk(self, text: str) -> list[dict]:
        raise NotImplementedError("Use chunk_pages() for PDF inputs.")

    def chunk_pages(self, pages: list[dict]) -> list[dict]:
        chunks: list[dict] = []
        chunk_index = 0

        for page in pages:
            page_number = int(page["page_number"])
            page_text = page["text"]
            paragraphs = self._extract_paragraphs(page_text)

            for paragraph_index, paragraph in enumerate(paragraphs):
                section_heading = self._guess_section_heading(paragraph)
                for chunk_text in self._chunk_paragraph(paragraph):
                    if not self._is_informative_chunk(chunk_text):
                        continue
                    chunks.append(
                        {
                            "chunk_text": chunk_text,
                            "chunk_index": chunk_index,
                            "page_number": page_number,
                            "paragraph_index": paragraph_index,
                            "paragraph_text": paragraph,
                            "section_heading": section_heading,
                            "title": None,
                        }
                    )
                    chunk_index += 1

        return chunks

    def _extract_paragraphs(self, page_text: str) -> list[str]:
        normalized = page_text.replace("\r\n", "\n").replace("\r", "\n")
        raw_parts = re.split(r"\n\s*\n+", normalized)
        paragraphs: list[str] = []

        for part in raw_parts:
            paragraph = self._normalize_whitespace(part)
            paragraph = self._strip_boilerplate_lines(paragraph)
            if not paragraph:
                continue
            paragraphs.append(paragraph)

        return paragraphs

    def _chunk_paragraph(self, paragraph: str) -> list[str]:
        if self._looks_like_table_or_list(paragraph):
            return self._chunk_structured_block(paragraph)

        sentences = self._split_into_sentences(paragraph)
        if len(sentences) > 1:
            grouped = self._group_sentences(sentences)
            if grouped:
                return grouped

        return self._split_by_word_length(paragraph, max_words=self.target_words_max)

    def _split_into_sentences(self, text: str) -> list[str]:
        parts = re.split(r"(?<=[.!?])\s+", text)
        return [part.strip() for part in parts if part.strip()]

    def _group_sentences(self, sentences: list[str]) -> list[str]:
        groups: list[str] = []
        current: list[str] = []
        current_words = 0

        for sentence in sentences:
            sentence_words = self._word_count(sentence)
            exceeds_max = current and current_words + sentence_words > self.target_words_max
            meets_min = current_words >= self.target_words_min
            if exceeds_max and meets_min:
                groups.append(" ".join(current).strip())
                current = []
                current_words = 0

            if sentence_words > self.hard_word_limit:
                if current:
                    groups.append(" ".join(current).strip())
                    current = []
                    current_words = 0
                groups.extend(self._split_by_word_length(sentence, max_words=self.target_words_max))
                continue

            current.append(sentence)
            current_words += sentence_words

        if current:
            groups.append(" ".join(current).strip())

        return self._apply_sentence_overlap(groups)

    def _apply_sentence_overlap(self, groups: list[str]) -> list[str]:
        if self.sentence_overlap <= 0 or len(groups) <= 1:
            return groups

        overlapped_groups: list[str] = []
        prior_tail: list[str] = []

        for group in groups:
            group_sentences = self._split_into_sentences(group)
            combined = prior_tail + group_sentences
            overlapped_groups.append(" ".join(combined).strip())
            prior_tail = group_sentences[-self.sentence_overlap :]

        return overlapped_groups

    def _split_by_word_length(self, text: str, max_words: int) -> list[str]:
        words = text.split()
        groups: list[str] = []

        for start in range(0, len(words), max_words):
            groups.append(" ".join(words[start : start + max_words]))

        return groups

    def _looks_like_table_or_list(self, paragraph: str) -> bool:
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if len(lines) < 3:
            return False

        digit_heavy_lines = sum(any(character.isdigit() for character in line) for line in lines)
        short_lines = sum(len(line.split()) <= 12 for line in lines)
        punctuation_count = paragraph.count(".") + paragraph.count("!") + paragraph.count("?")

        return (
            digit_heavy_lines >= max(2, len(lines) // 2)
            or short_lines >= max(3, len(lines) - 1)
            or punctuation_count <= 1
        )

    def _chunk_structured_block(self, paragraph: str) -> list[str]:
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        if not lines:
            return []

        context_lines: list[str] = []
        header_lines: list[str] = []
        data_lines: list[str] = []

        for line in lines:
            if self._is_structured_context_line(line):
                context_lines.append(line)
                continue
            if self._is_structured_header_line(line):
                header_lines.append(line)
                continue
            data_lines.append(line)

        if not data_lines:
            data_lines = header_lines
            header_lines = []

        prefix_parts = context_lines[:2]
        if header_lines:
            prefix_parts.append(" | ".join(header_lines[:2]))
        prefix = " | ".join(part for part in prefix_parts if part)

        groups: list[str] = []
        for start in range(0, len(data_lines), self.line_group_size):
            group_lines = data_lines[start : start + self.line_group_size]
            body = " | ".join(group_lines)
            if prefix:
                groups.append(f"{prefix} | {body}")
            else:
                groups.append(body)

        return groups

    def _is_structured_context_line(self, line: str) -> bool:
        lowered = line.lower()
        return (
            lowered.startswith("table ")
            or lowered.startswith("figure ")
            or lowered.startswith("chapter ")
            or re.match(r"^\d+(\.\d+)+\s", line) is not None
        )

    def _is_structured_header_line(self, line: str) -> bool:
        lowered = line.lower()
        header_keywords = ("parameter", "condition", "min", "typ", "max", "unit", "symbol")
        if any(keyword in lowered for keyword in header_keywords):
            return True
        words = line.split()
        return 2 <= len(words) <= 8 and all(word[:1].isalpha() for word in words)

    def _is_informative_chunk(self, chunk_text: str) -> bool:
        compact = " ".join(chunk_text.split())
        if len(compact) < 30:
            return False

        tokens = compact.split()
        alpha_tokens = [token for token in tokens if any(character.isalpha() for character in token)]
        digit_tokens = [token for token in tokens if any(character.isdigit() for character in token)]

        if len(alpha_tokens) < 4:
            return False

        if alpha_tokens and len(digit_tokens) > len(alpha_tokens) * 2:
            return False

        lowered = compact.lower()
        low_information_patterns = (
            "condition min typ max",
            "parameter condition min typ max unit",
            "list of tables",
            "list of figures",
            "contents",
        )
        if any(pattern in lowered for pattern in low_information_patterns):
            return False

        return True

    def _strip_boilerplate_lines(self, paragraph: str) -> str:
        lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
        filtered_lines: list[str] = []

        for line in lines:
            if any(pattern.match(line) for pattern in self.BOILERPLATE_PATTERNS):
                continue
            if filtered_lines and filtered_lines[-1] == line:
                continue
            filtered_lines.append(line)

        return "\n".join(filtered_lines).strip()

    def _guess_section_heading(self, paragraph: str) -> Optional[str]:
        first_line = paragraph.split("\n", maxsplit=1)[0].strip()
        if not first_line:
            return None

        if len(first_line.split()) <= 12 and first_line == first_line.upper():
            return first_line

        if len(first_line.split()) <= 12 and first_line.endswith(":"):
            return first_line.rstrip(":")

        return None

    def _normalize_whitespace(self, text: str) -> str:
        lines = [re.sub(r"\s+", " ", line.strip()) for line in text.splitlines()]
        return "\n".join(line for line in lines if line).strip()

    def _word_count(self, text: str) -> int:
        return len(text.split())
