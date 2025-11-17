from collections.abc import Mapping
from typing import Any, Iterable, get_args
from string import Formatter
from .rubric import Rubric


class PromptBuilder:
    """
    Utility class for incrementally constructing LLM prompt strings
    from a base template.

    Supports:
    - Direct placeholder injection via simple string replacement (e.g.
      {score_scale_values}, {score_scale_ranges}, {other_enumerated_notes}),
    - Pre-filling default format kwargs (e.g. {rubric}),
    - Final .format() to produce the fully rendered prompt string,
    - Validation of remaining placeholders against expected keys.
    """

    def __init__(
        self, base_template: str, default_format_kwargs: dict[str, Any] | None = None
    ) -> None:
        """
        Initialize the builder with a base prompt template.

        Parameters
        ----------
        base_template : str
            The raw prompt template containing placeholders such as
            {score_scale_values}, {score_scale_ranges}, {other_enumerated_notes},
            and other standard str.format-style fields.
        default_format_kwargs : dict[str, Any], optional
            Default keyword arguments to be used when formatting the template.
            These are merged with any kwargs passed to `build()`,
            with `build()` arguments taking precedence.
        """
        self._template = base_template
        self._default_format_kwargs: dict[str, Any] = default_format_kwargs or {}

    @property
    def template(self) -> str:
        """Return the current state of the template (before final .format())."""
        return self._template

    def with_placeholder(self, placeholder: str, value: str) -> "PromptBuilder":
        """
        Replace a specific placeholder in the template with the given value.

        This uses a direct string replacement instead of str.format(),
        so it does not affect other {fields} that are meant to be filled later.

        Parameters
        ----------
        placeholder : str
            The exact placeholder string to replace (e.g. "{other_enumerated_notes}").
        value : str
            The text that will replace the placeholder in the template.

        Returns
        -------
        PromptBuilder
            The builder instance (self), allowing method chaining.
        """
        self._template = self._template.replace(placeholder, value)
        return self

    def with_additional_notes(
        self,
        notes_to_inject: str = "",
        additional_notes_placeholder: str = "{other_enumerated_notes}",
    ) -> "PromptBuilder":
        """
        Inject additional enumerated notes or constraints into the template.

        This is a convenience wrapper around `with_placeholder` for the
        {other_enumerated_notes} placeholder.
        """
        return self.with_placeholder(additional_notes_placeholder, notes_to_inject)

    def with_score_scale_metadata(
        self,
        literal_type: Any,
        scale_descriptions: Mapping[str, str],
        values_placeholder: str = "{score_scale_values}",
        ranges_placeholder: str = "{score_scale_ranges}",
    ) -> "PromptBuilder":
        """
        Inject score scale literal values and their range descriptions into
        the template.
        """
        literal_values = get_args(literal_type)

        if not literal_values:
            raise ValueError(f"No literal values found for {literal_type!r}")

        missing = [v for v in literal_values if v not in scale_descriptions]

        if missing:
            raise ValueError(
                f"Missing descriptions for score scales: {missing}. "
                "Update your scale_descriptions mapping."
            )

        # Extract the literal values into a string like '"0-1", "0-5", "0-10", "percentage"'
        values_str = ", ".join(f'"{v}"' for v in literal_values)

        # Range description
        lines = [
            'For each criterion, choose "score" as an integer consistent with "score_scale":'
        ]

        for v in literal_values:
            desc = scale_descriptions[v]
            lines.append(f'- "{v}" \u2192 {desc}')

        ranges_str = "\n    ".join(lines)

        self._template = self._template.replace(values_placeholder, values_str)
        self._template = self._template.replace(ranges_placeholder, ranges_str)
        return self

    def _extract_placeholders(self) -> set[str]:
        """
        Extract all placeholder field names currently present in the template.

        This uses string.Formatter.parse to find {field_name} occurrences that
        would be processed by str.format().
        """
        placeholders: set[str] = set()
        for literal_text, field_name, format_spec, conversion in Formatter().parse(
            self._template
        ):
            if field_name:  # ignore None / literal chunks
                placeholders.add(field_name)

        return placeholders

    def validate_placeholders(
        self,
        provided_keys: Iterable[str] = (),
    ) -> set[str]:
        """
        Validate that all remaining {placeholders} in the template are covered
        by either default_format_kwargs or the given provided_keys.

        This is useful to detect typos such as {knowlege_area} before calling
        `build()`. It does not mutate the template or perform any formatting;
        it only reports which placeholders would be missing.

        Parameters
        ----------
        provided_keys : Iterable[str], optional
            The set/list of keys you intend to pass to `build()` (e.g.
            ["knowledge_area", "cohort_specifics", "track_name", ...]).

        Returns
        -------
        set[str]
            A set of placeholder names that are currently in the template but
            are not covered by default_format_kwargs or provided_keys. An empty
            set means everything looks consistent.

        Examples
        --------
        missing = builder.validate_placeholders(
            provided_keys={"knowledge_area", "cohort_specifics", ...}
        )
        if missing:
            raise ValueError(f"Missing values for placeholders: {missing}")
        """
        placeholders = self._extract_placeholders()
        known = set(self._default_format_kwargs.keys()).union(set(provided_keys))
        missing = placeholders - known
        return missing

    def build(self, **format_kwargs: Any) -> str:
        """
        Finalize the prompt string by applying str.format() to the current template.

        Default kwargs (e.g. auto-rendered rubric) are merged with explicit ones,
        and explicit kwargs take precedence.

        Parameters
        ----------
        **format_kwargs : Any
            Keyword arguments passed directly to str.format() for the template.

        Returns
        -------
        str
            The fully rendered prompt string ready to be sent to the LLM.

        Raises
        ------
        KeyError
            If some placeholders in the template are not provided in
            the merged kwargs.
        """
        merged = {**self._default_format_kwargs, **format_kwargs}
        return self._template.format(**merged)

    @staticmethod
    def _render_rubric(rubric: Rubric) -> str:
        """
        Render a Rubric instance into a human-readable text block suitable for
        insertion into the {rubric} placeholder in the prompt template.
        """
        lines: list[str] = []

        # Title and description
        if rubric.title:
            lines.append(rubric.title)

        if rubric.description:
            if lines:
                lines.append("")  # blank line before description
            lines.append(rubric.description)

        # Overall scoring info
        lines.append("")
        lines.append(
            f"Overall max score: {rubric.overall_max_score} "
            f"(passing: {rubric.min_passing_score} or higher)."
        )

        # Criteria
        lines.append("")
        lines.append("Criteria:")
        for c in rubric.criteria:
            # First line: name + id + weight + scale
            lines.append(
                f'- [{c.id}] {c.name} (weight: {c.weight}, scale: "{c.scale}")'
            )
            # description on the next line
            if c.description:
                lines[
                    -1
                ] += ":"  # colon at the end of the criterion heading text before the description line
                lines.append(f"  {c.description}")

        return "\n".join(lines)

    @classmethod
    def from_rubric(
        cls,
        base_template: str,
        rubric: Rubric,
        score_scale_literal: Any,
        scale_descriptions: Mapping[str, str],
        additional_notes: str = "",
    ) -> "PromptBuilder":
        """
        Construct a PromptBuilder pre-configured for a given rubric.

        This convenience constructor:
        - starts from the given base_template,
        - injects score scale literals and their range descriptions into the
          template using `with_score_scale_metadata`,
        - injects any additional notes into {other_enumerated_notes},
        - pre-fills the {rubric} placeholder with a rendered representation
          of the provided Rubric instance.

        Parameters
        ----------
        base_template : str
            The base LLM prompt template string.
        rubric : Rubric
            The rubric definition associated with the task.
        score_scale_literal : Any
            A typing.Literal type that enumerates the allowed score scales
            (e.g. ScoreScale).
        scale_descriptions : Mapping[str, str]
            Mapping from each score scale literal value to a description of
            its numeric range/usage.
        additional_notes : str, optional
            Extra notes or constraints to inject into the
            {other_enumerated_notes} placeholder.

        Returns
        -------
        PromptBuilder
            A PromptBuilder instance ready for final formatting via `build()`.
        """
        # Initialize builder with base template
        builder = cls(base_template)

        # Inject score scale metadata (values + ranges)
        builder.with_score_scale_metadata(score_scale_literal, scale_descriptions)

        # Inject additional notes, if any
        if additional_notes:
            builder.with_additional_notes(additional_notes)

        # Pre-fill the {rubric} placeholder with a rendered rubric string
        rubric_text = cls._render_rubric(rubric)
        builder._default_format_kwargs["rubric"] = rubric_text

        return builder
