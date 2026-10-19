"""Keywords decide relevance with paragraph-level evidence; an LLM can only add, for review."""

from collections.abc import Sequence

from abhiyogah.regwatch.extract import ExtractedText, Paragraph, html_paragraphs, text_paragraphs
from abhiyogah.regwatch.relevance import LlmSuggestion, Topic, classify, keyword_hits
from tests.regwatch.conftest import fixture

SHA = "0" * 64


def doc(paragraphs: list[Paragraph]) -> ExtractedText:
    """An extracted document."""
    return ExtractedText(sha256=SHA, method="text", paragraphs=paragraphs)


class Fake:
    """A scripted suggester."""

    def __init__(self, *suggestions: LlmSuggestion) -> None:
        self.suggestions = list(suggestions)
        self.calls = 0

    def suggest(self, paragraphs: Sequence[Paragraph]) -> list[LlmSuggestion]:
        """The scripted suggestions."""
        self.calls += 1
        return self.suggestions


def suggestion(topic: Topic, *anchors: str) -> LlmSuggestion:
    """A suggestion from a fake model."""
    return LlmSuggestion(
        topic=topic, anchors=list(anchors), model="fake-model", prompt_version="v0"
    )


def test_io_circular_is_relevant_with_cited_paragraphs() -> None:
    """The synthetic IO amendment hits COMPLAINTS and INTERNAL_OMBUDSMAN, anchored."""
    text = doc(html_paragraphs(fixture("circular_io_amendment.html").decode()))
    got = classify(text)
    assert got.relevant
    assert not got.needs_review
    assert Topic.INTERNAL_OMBUDSMAN in got.topics
    assert Topic.COMPLAINTS in got.topics
    anchors = {h.anchor for h in got.hits if h.topic is Topic.INTERNAL_OMBUDSMAN}
    assert all(text.find(a).text for a in anchors)


def test_each_topic_has_working_keywords() -> None:
    """One sentence per topic is found, and only that topic."""
    cases = {
        Topic.COMPLAINTS: "Grievance redress under RB-IOS.",
        Topic.CUSTOMER_SERVICE: "Master Direction on Customer Service in banks.",
        Topic.FRAUD: "Reporting of frauds by banks.",
        Topic.KYC: "Periodic updation of KYC.",
        Topic.PAYMENT_TAT: "Harmonisation of Turn Around Time for failed transactions.",
        Topic.INTERNAL_OMBUDSMAN: "Appointment of Internal Ombudsman.",
    }
    for topic, sentence in cases.items():
        assert classify(doc(text_paragraphs(sentence))).topics == [topic], sentence


def test_acronyms_need_their_case_and_whole_words() -> None:
    """'tat', 'kyc' inside words, and 'io' in lower case are not hits."""
    paras = text_paragraphs("Statutory ratio; the kycx field; io-bound; a TAT applies.")
    assert [(h.topic, h.term) for h in keyword_hits(paras)] == [(Topic.PAYMENT_TAT, "TAT")]


def test_unrelated_document_is_not_relevant() -> None:
    """Currency chest timings touch no watched topic."""
    got = classify(doc(text_paragraphs("1. Revised timings for currency chest operations.")))
    assert not got.relevant
    assert got.topics == []
    assert not got.needs_review


def test_llm_can_add_a_topic_but_it_goes_to_review() -> None:
    """A topic only the model saw is included and flagged for a human."""
    text = doc(text_paragraphs("1. Revised timings for currency chest operations."))
    got = classify(text, Fake(suggestion(Topic.CUSTOMER_SERVICE, "p1")))
    assert got.relevant
    assert got.topics == [Topic.CUSTOMER_SERVICE]
    assert got.needs_review
    assert got.suggestions[0].model == "fake-model"


def test_llm_cannot_remove_a_keyword_topic() -> None:
    """A model that suggests nothing leaves the keyword topics in place."""
    text = doc(text_paragraphs("1. Reporting of frauds by banks."))
    fake = Fake()
    got = classify(text, fake)
    assert fake.calls == 1
    assert got.topics == [Topic.FRAUD]
    assert not got.needs_review


def test_llm_agreeing_with_keywords_needs_no_review() -> None:
    """Agreement is not a reason to look twice."""
    text = doc(text_paragraphs("1. Reporting of frauds by banks."))
    assert not classify(text, Fake(suggestion(Topic.FRAUD, "p1"))).needs_review


def test_llm_citing_a_missing_paragraph_goes_to_review() -> None:
    """A citation to an anchor the document lacks is flagged."""
    text = doc(text_paragraphs("1. Reporting of frauds by banks."))
    assert classify(text, Fake(suggestion(Topic.FRAUD, "p99"))).needs_review
