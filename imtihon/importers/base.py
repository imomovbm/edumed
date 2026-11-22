"""The data an importer produces, and the interface every file format implements."""
from dataclasses import dataclass, field

ERROR = 'error'
WARNING = 'warning'


@dataclass
class ParsedOption:
    text: str
    is_correct: bool
    line: int | None = None


@dataclass
class Problem:
    message: str
    level: str = ERROR
    number: int | None = None      # question number (1-based), None for file-level problems
    line: int | None = None        # line in the file

    @property
    def is_error(self):
        return self.level == ERROR


@dataclass
class ParsedQuestion:
    number: int
    text: str
    options: list = field(default_factory=list)   # list[ParsedOption]
    line: int | None = None
    problems: list = field(default_factory=list)  # list[Problem]

    @property
    def has_errors(self):
        return any(p.is_error for p in self.problems)

    @property
    def correct_count(self):
        return sum(1 for o in self.options if o.is_correct)


@dataclass
class ParseResult:
    questions: list = field(default_factory=list)  # list[ParsedQuestion]
    problems: list = field(default_factory=list)   # list[Problem], file level and per question
    text: str | None = None                        # the decoded text (shown in the editor)
    encoding: str | None = None
    format_name: str = ''

    @property
    def errors(self):
        return [p for p in self.problems if p.is_error]

    @property
    def warnings(self):
        return [p for p in self.problems if not p.is_error]

    @property
    def ok(self):
        return bool(self.questions) and not self.errors

    def add(self, problem, question=None):
        self.problems.append(problem)
        if question is not None:
            question.problems.append(problem)


class BaseParser:
    """One test file format. Subclasses set ``extensions`` and implement ``parse_text``."""

    name = ''
    extensions = ()

    def parse_text(self, text):
        """Turn decoded text into a :class:`ParseResult` (problems included, never raises)."""
        raise NotImplementedError
