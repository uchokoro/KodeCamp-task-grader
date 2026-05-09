from pydantic import BaseModel, Field
from typing import Literal, Any, Callable
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser


class CritiqueResult(BaseModel):
    status: Literal["PASS", "REVISE"] = Field(
        description="'PASS' if the content meets all criteria, 'REVISE' if improvements are needed."
    )
    rationale: str = Field(
        description="Detailed explanation of why the content passed or what specifically needs to be fixed."
    )


class ReflectionLoopExecutor:
    def __init__(self, model: Any, max_rounds: int = 1):
        self.model = model
        self.max_rounds = max_rounds
        self.parser = PydanticOutputParser(pydantic_object=CritiqueResult)

    def _run_reflection(
        self, role: str, task_type: str, context: str, criteria: str, output: Any
    ):
        prompt = ChatPromptTemplate.from_template(
            "Role: {role}\n"
            "Task: Review the {task_type} for: {context}\n\n"
            "CURRENT OUTPUT:\n{current_output}\n\n"
            "AUDIT CRITERIA:\n{criteria}\n\n"
            "{format_instructions}"
        )
        # LCEL Chain: Prompt -> Model -> Pydantic Parser
        chain = prompt | self.model | self.parser
        return chain.invoke(
            {
                "role": role,
                "task_type": task_type,
                "context": context,
                "criteria": criteria,
                "current_output": str(output),
                "format_instructions": self.parser.get_format_instructions(),
            }
        )

    def execute_rubric_gen(self, build_func: Callable, **kwargs) -> Any:
        print(f"\n{'=' * 20} RUBRIC AUDIT MODE {'=' * 20}")

        _RUBRIC_CRITERIA = (
            "1. Task Coverage: Does the rubric capture ALL relevant requirements mentioned in the assignment text?\n"
            "2. Redundancy & Overlap: Are there criteria that grade the same skill? Ensure each criterion is mutually exclusive.\n"
            "3. Bloom's Taxonomy: Are the verbs used in the descriptors measurable and appropriate for the academic level?\n"
            "4. Score Logic: Is the point distribution across criteria logical and weighted correctly relative to importance?\n"
            "5. Clarity: Are achievement levels (e.g., 'Exemplary' vs 'Proficient') distinct enough for consistent grading?"
        )

        current_extra = kwargs.get("additional_requirements", "")
        final_rubric = None

        for r in range(self.max_rounds + 1):
            print(f"[Round {r}] Generating Rubric...")
            kwargs["additional_requirements"] = current_extra
            final_rubric = build_func(**kwargs)

            if r == self.max_rounds:
                break

            critique = self._run_reflection(
                "Senior Curriculum Architect",
                "rubric",
                str(kwargs.get("assignment")),
                _RUBRIC_CRITERIA,
                final_rubric,
            )

            print(f"[VERDICT]: {critique.status}")
            print(f"[RATIONALE]: {critique.rationale}")

            if critique.status == "PASS":
                break

            # Feed rationale back into the generation function
            current_extra = f"{kwargs.get('additional_requirements')}\n\nREVISION REQUIRED:\n{critique.rationale}"

        return final_rubric

    def execute_grading(self, evaluator_method: Callable, **kwargs) -> Any:
        trainee = kwargs.get("trainee_name", "Trainee")
        print(f"\n{'=' * 20} GRADING AUDIT: {trainee} {'=' * 20}")

        _GRADING_CRITERIA = (
            "1. Score-Rationale Coherence: Does the written feedback justify the specific numerical score awarded? "
            "Ensure no 'grade inflation' (praise without points) or 'grade deflation'.\n"
            "2. Rubric Fidelity: Is the score assigned strictly based on the rubric's definitions for that level?\n"
            "3. Evidence-Based: Does the rationale cite specific parts of the student's submission?\n"
            "4. Accuracy: Does the awarded score correctly reflect the student's performance on that specific criterion?"
        )

        current_notes = kwargs.get("other_notes", "")
        final_eval = None

        for r in range(self.max_rounds + 1):
            print(f"[Round {r}] Evaluating Submission...")
            kwargs["other_notes"] = current_notes
            final_eval = evaluator_method(**kwargs)

            if r == self.max_rounds:
                break

            critique = self._run_reflection(
                "Senior Academic Auditor",
                "grading evaluation",
                f"Submission by {trainee}",
                _GRADING_CRITERIA,
                final_eval,
            )

            print(f"[VERDICT]: {critique.status}")
            print(f"[RATIONALE]: {critique.rationale}")

            if critique.status == "PASS":
                break

            # Feed rationale back into the evaluator
            current_notes = f"{kwargs.get('other_notes')}\n\nADJUSTMENT REQUIRED:\n{critique.rationale}"

        return final_eval
