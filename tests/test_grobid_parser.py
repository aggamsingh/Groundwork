"""GROBID TEI parsing tests.

These run without the GROBID container: `parse_tei` is pure, so the XML handling
is testable in isolation from the service. Only the HTTP layer needs a container,
and that is exercised by the bake-off rather than the unit suite.
"""

from __future__ import annotations

import unittest

from survey.ingest.grobid_parser import parse_tei
from survey.ingest.model import ParseError

TEI_DOC = """<?xml version="1.0" encoding="UTF-8"?>
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <titleStmt>
        <title level="a" type="main">Semantic Communication with Adaptive
        Universal Transformer</title>
      </titleStmt>
      <publicationStmt>
        <date type="published" when="2021-11-29">29 Nov 2021</date>
      </publicationStmt>
      <sourceDesc>
        <biblStruct>
          <monogr>
            <title level="j">IEEE Wireless Communications Letters</title>
            <imprint>
              <date type="published" when="2021-11-29">29 Nov 2021</date>
            </imprint>
          </monogr>
          <idno type="DOI">10.1109/LWC.2021.3128643</idno>
          <idno type="arXiv">arXiv:2108.09119v3</idno>
        </biblStruct>
      </sourceDesc>
    </fileDesc>
    <profileDesc>
      <abstract><div><p>With the development of deep learning, NLP makes it
      possible to analyse language.</p></div></abstract>
    </profileDesc>
  </teiHeader>
  <text>
    <body>
      <div>
        <head n="I">INTRODUCTION</head>
        <p>Semantic communication transmits meaning rather than
        <ref type="bibr" target="#b0">[1]</ref> bits.</p>
        <p>Second paragraph here.</p>
      </div>
      <div>
        <head n="2.1">System Model</head>
        <p>The channel is modelled as AWGN.</p>
      </div>
    </body>
    <back>
      <div type="references">
        <listBibl>
          <biblStruct>
            <analytic>
              <title level="a" type="main">Deep Learning Enabled Semantic
              Communication Systems</title>
            </analytic>
            <monogr><imprint><date when="2021"/></imprint></monogr>
            <idno type="DOI">10.1109/TSP.2021.3071210</idno>
          </biblStruct>
          <biblStruct>
            <analytic><title level="a" type="main">Attention Is All You Need</title></analytic>
          </biblStruct>
        </listBibl>
      </div>
    </back>
  </text>
</TEI>
"""


class TestParseTei(unittest.TestCase):
    def setUp(self) -> None:
        self.paper = parse_tei(TEI_DOC, "test-paper")

    def test_header_fields(self) -> None:
        self.assertEqual(
            self.paper.title,
            "Semantic Communication with Adaptive Universal Transformer",
        )
        self.assertEqual(self.paper.year, 2021)
        self.assertEqual(self.paper.doi, "10.1109/LWC.2021.3128643")
        self.assertEqual(self.paper.arxiv_id, "arXiv:2108.09119v3")
        self.assertEqual(self.paper.venue, "IEEE Wireless Communications Letters")

    def test_abstract_becomes_its_own_section(self) -> None:
        self.assertIn("deep learning", (self.paper.abstract or "").lower())
        self.assertEqual(self.paper.sections[0].kind, "abstract")

    def test_section_numbers_are_prefixed_to_headings(self) -> None:
        headings = [s.heading for s in self.paper.sections]
        self.assertIn("I INTRODUCTION", headings)
        self.assertIn("2.1 System Model", headings)

    def test_depth_comes_from_the_section_number(self) -> None:
        sub = next(s for s in self.paper.sections if s.heading == "2.1 System Model")
        self.assertEqual(sub.depth, 1)

    def test_inline_refs_do_not_truncate_a_paragraph(self) -> None:
        # TEI marks citations up inline. Using .text instead of itertext() would
        # silently cut the sentence at "[1]" and lose the rest.
        intro = next(s for s in self.paper.sections if s.heading == "I INTRODUCTION")
        self.assertIn("bits", intro.paragraphs[0].text)
        self.assertEqual(len(intro.paragraphs), 2)

    def test_references_are_structured(self) -> None:
        # The whole point of GROBID over the baseline: title and DOI as fields.
        titles = [r.title for r in self.paper.references]
        self.assertIn("Deep Learning Enabled Semantic Communication Systems", titles)
        self.assertIn("Attention Is All You Need", titles)
        first = self.paper.references[0]
        self.assertEqual(first.doi, "10.1109/TSP.2021.3071210")


class TestFailureModes(unittest.TestCase):
    def test_malformed_xml_raises_parse_error(self) -> None:
        with self.assertRaises(ParseError):
            parse_tei("<TEI><unclosed>", "test-paper")

    def test_namespace_is_required(self) -> None:
        # TEI without the namespace yields no content. This must not silently
        # look like a paper with nothing in it.
        paper = parse_tei("<TEI><text><body><div><p>hi</p></div></body></text></TEI>", "x")
        self.assertEqual(paper.sections, [])


if __name__ == "__main__":
    unittest.main()
