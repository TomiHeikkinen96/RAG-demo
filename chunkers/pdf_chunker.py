from __future__ import annotations

import re
from typing import Optional

from chunkers.base_chunker import BaseChunker


class PDFChunker(BaseChunker):
    def __init__(
        self,
        target_words_min: int = 300,
        target_words_max: int = 800,
        hard_word_limit: int = 1000,
    ) -> None:
        self.target_words_min = target_words_min
        self.target_words_max = target_words_max
        self.hard_word_limit = hard_word_limit

    def chunk(self, text: str) -> list[dict]:
        raise NotImplementedError("Use chunk_pages() for PDF inputs.")

    def chunk_pages(self, pages: list[dict]) -> list[dict]:
        chunks: list[dict] = []
        chunk_index = 0

        for page in pages:
            page_number = int(page["page_number"])
            page_text = page["text"]
            paragraphs = self._extract_paragraphs(page_text)

            for paragraph in paragraphs:
                section_heading = self._guess_section_heading(paragraph)
                for chunk_text in self._split_large_paragraph(paragraph):
                    chunks.append(
                        {
                            "chunk_text": chunk_text,
                            "chunk_index": chunk_index,
                            "page_number": page_number,
                            "section_heading": section_heading,
                            "title": None,
                        }
                    )
                    chunk_index += 1

        return chunks

    def _extract_paragraphs(self, page_text: str) -> list[str]:
        normalized = page_text.replace("\r\n", "\n").replace("\r", "\n")
        raw_parts = re.split(r"\n\s*\n+", normalized)
        paragraphs = [self._normalize_whitespace(part) for part in raw_parts]
        return [paragraph for paragraph in paragraphs if paragraph]

    def _split_large_paragraph(self, paragraph: str) -> list[str]:
        word_count = self._word_count(paragraph)
        if word_count <= self.target_words_max:
            return [paragraph]

        sentences = self._split_into_sentences(paragraph)
        if len(sentences) > 1:
            grouped = self._group_sentences(sentences)
            if grouped:
                return grouped

        return self._split_by_word_length(paragraph)

    def _split_into_sentences(self, text: str) -> list[str]:
        parts = re.split(r"(?<=[.!?])\s+", text)
        return [part.strip() for part in parts if part.strip()]

    def _group_sentences(self, sentences: list[str]) -> list[str]:
        groups: list[str] = []
        current: list[str] = []
        current_words = 0

        for sentence in sentences:
            sentence_words = self._word_count(sentence)
            if current and current_words + sentence_words > self.target_words_max:
                groups.append(" ".join(current).strip())
                current = []
                current_words = 0

            current.append(sentence)
            current_words += sentence_words

        if current:
            groups.append(" ".join(current).strip())

        if any(self._word_count(group) > self.hard_word_limit for group in groups):
            return []

        return groups

    def _split_by_word_length(self, text: str) -> list[str]:
        words = text.split()
        groups: list[str] = []

        for start in range(0, len(words), self.target_words_max):
            groups.append(" ".join(words[start : start + self.target_words_max]))

        return groups

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
        lines = [line.strip() for line in text.splitlines()]
        joined = " ".join(line for line in lines if line)
        return re.sub(r"\s+", " ", joined).strip()

    def _word_count(self, text: str) -> int:
        return len(text.split())
