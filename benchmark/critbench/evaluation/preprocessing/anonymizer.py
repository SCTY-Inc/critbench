"""Anonymization for removing provenance bias from judge evaluation.

Strips model identifiers and randomizes presentation order to prevent:
- Self-enhancement bias (judges favoring their own model family)
- Provenance bias (preferring outputs labeled as "expert" vs "AI")

Reference: LitBench research on provenance cues in creative evaluation.
"""
from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class AnonymizationResult:
    """Result of anonymization process."""

    anonymized_content: str
    mapping: Dict[str, str]  # original -> anonymized
    reverse_mapping: Dict[str, str]  # anonymized -> original
    redactions: List[str]  # What was redacted


class Anonymizer:
    """Anonymizes content to remove provenance cues."""

    # Model family patterns to detect and anonymize
    MODEL_PATTERNS = [
        # OpenAI
        (r'\b(gpt-?4\.?[0-9]*|gpt-?3\.?5|chatgpt|openai)\b', 'Model'),
        # Anthropic
        (r'\b(claude|anthropic|sonnet|opus|haiku)\b', 'Model'),
        # Google
        (r'\b(gemini|bard|palm|google\s+ai)\b', 'Model'),
        # Meta
        (r'\b(llama|meta\s+ai)\b', 'Model'),
        # Generic
        (r'\b(ai\s+model|language\s+model|llm)\b', 'assistant'),
    ]

    # Provider/company patterns
    PROVIDER_PATTERNS = [
        (r'\b(openai|anthropic|google|meta|microsoft)\b', 'Provider'),
    ]

    # Version/identifier patterns
    VERSION_PATTERNS = [
        (r'\b\d{8}\b', '[DATE]'),  # Date stamps like 20250514
        (r'\bv\d+(\.\d+)*\b', '[VERSION]'),
        (r'\b\d+\.\d+\.\d+\b', '[VERSION]'),
    ]

    def __init__(
        self,
        anonymize_models: bool = True,
        anonymize_providers: bool = True,
        anonymize_versions: bool = True,
        shuffle_order: bool = True,
        seed: Optional[int] = None,
    ):
        self.anonymize_models = anonymize_models
        self.anonymize_providers = anonymize_providers
        self.anonymize_versions = anonymize_versions
        self.shuffle_order = shuffle_order
        self.rng = random.Random(seed)

        self._counter = 0
        self._mapping: Dict[str, str] = {}

    def _get_anon_id(self, original: str, prefix: str = "Model") -> str:
        """Get or create anonymized ID for an original value."""
        key = original.lower()
        if key not in self._mapping:
            self._counter += 1
            # Use letter-based IDs (A, B, C, ...)
            letter = chr(ord('A') + (self._counter - 1) % 26)
            self._mapping[key] = f"{prefix} {letter}"
        return self._mapping[key]

    def anonymize(self, content: str) -> AnonymizationResult:
        """Anonymize content by replacing model/provider references.

        Args:
            content: Text content to anonymize

        Returns:
            AnonymizationResult with anonymized content and mappings
        """
        result = content
        redactions = []
        mapping = {}

        # Anonymize model names
        if self.anonymize_models:
            for pattern, replacement in self.MODEL_PATTERNS:
                for match in re.finditer(pattern, result, re.IGNORECASE):
                    original = match.group(0)
                    anon_id = self._get_anon_id(original, replacement)
                    mapping[original] = anon_id
                    redactions.append(f"Model reference: {original}")
                result = re.sub(pattern, lambda m: self._get_anon_id(m.group(0), replacement),
                               result, flags=re.IGNORECASE)

        # Anonymize provider names
        if self.anonymize_providers:
            for pattern, replacement in self.PROVIDER_PATTERNS:
                for match in re.finditer(pattern, result, re.IGNORECASE):
                    original = match.group(0)
                    anon_id = self._get_anon_id(original, replacement)
                    mapping[original] = anon_id
                    redactions.append(f"Provider reference: {original}")
                result = re.sub(pattern, lambda m: self._get_anon_id(m.group(0), replacement),
                               result, flags=re.IGNORECASE)

        # Anonymize versions
        if self.anonymize_versions:
            for pattern, replacement in self.VERSION_PATTERNS:
                for match in re.finditer(pattern, result):
                    redactions.append(f"Version reference: {match.group(0)}")
                result = re.sub(pattern, replacement, result)

        reverse_mapping = {v: k for k, v in mapping.items()}

        return AnonymizationResult(
            anonymized_content=result,
            mapping=mapping,
            reverse_mapping=reverse_mapping,
            redactions=redactions,
        )

    def anonymize_transcript(
        self,
        transcript: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
        """Anonymize a full transcript.

        Args:
            transcript: List of turn dicts with "content" key

        Returns:
            Tuple of (anonymized transcript, mapping)
        """
        anonymized = []
        full_mapping = {}

        for turn in transcript:
            new_turn = turn.copy()
            if "content" in turn:
                result = self.anonymize(turn["content"])
                new_turn["content"] = result.anonymized_content
                full_mapping.update(result.mapping)
            anonymized.append(new_turn)

        return anonymized, full_mapping

    def shuffle_responses(
        self,
        responses: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[int]]:
        """Shuffle response order to prevent position bias.

        Args:
            responses: List of response dicts

        Returns:
            Tuple of (shuffled responses, original indices)
        """
        if not self.shuffle_order:
            return responses, list(range(len(responses)))

        indices = list(range(len(responses)))
        self.rng.shuffle(indices)

        shuffled = [responses[i] for i in indices]
        return shuffled, indices

    def reset(self) -> None:
        """Reset anonymization state."""
        self._counter = 0
        self._mapping.clear()


def anonymize_content(content: str, **kwargs) -> str:
    """Convenience function to anonymize content.

    Args:
        content: Text to anonymize
        **kwargs: Options for Anonymizer

    Returns:
        Anonymized content string
    """
    anonymizer = Anonymizer(**kwargs)
    result = anonymizer.anonymize(content)
    return result.anonymized_content


def anonymize_transcript(
    transcript: List[Dict[str, Any]],
    **kwargs,
) -> List[Dict[str, Any]]:
    """Convenience function to anonymize a transcript.

    Args:
        transcript: Transcript to anonymize
        **kwargs: Options for Anonymizer

    Returns:
        Anonymized transcript
    """
    anonymizer = Anonymizer(**kwargs)
    anonymized, _ = anonymizer.anonymize_transcript(transcript)
    return anonymized
