"""
Tests for Tabbycat Extractor module.
"""

import pytest
from atomos.extractor.tabbycat import (
    TabbycatExtractor,
    SpeechRecord,
    TeamBallot,
    AdjudicatorBallot,
    DebateRecord,
)


class TestTabbycatExtractorParsing:
    def test_extract_tables_data_basic(self):
        extractor = TabbycatExtractor()
        html = """
        <html>
        <script>
        window.vueData = {
          tablesData: [{"head": [{"key": "Rk"}, {"key": "team"}], "data": [["1", "RC A"]]}]
        };
        </script>
        </html>
        """
        tables = extractor.extract_tables_data(html)
        assert len(tables) == 1
        assert tables[0]["head"][0]["key"] == "Rk"
        assert tables[0]["data"][0][1] == "RC A"

    def test_extract_tables_data_with_nested_brackets_and_strings(self):
        extractor = TabbycatExtractor()
        html = """
        <script>
        window.vueData = {
          tablesData: [
            {
              "data": [
                {"popover": {"text": "Hello [bracket in text] and \\"escaped quotes\\""}}
              ]
            }
          ]
        };
        </script>
        """
        tables = extractor.extract_tables_data(html)
        assert len(tables) == 1
        assert "bracket in text" in tables[0]["data"][0]["popover"]["text"]

    def test_parse_single_adjudicator_scoresheet(self):
        extractor = TabbycatExtractor()
        sample_html = """
        <div class="card">
          <div class="card-body">
            <h4 class="card-title">Motion</h4>
            This House would ban private tutoring
          </div>
        </div>
        <div class="card mt-3">
          <div class="card-body pb-1">
            <h4 class="card-title">Scoresheet</h4>
            <div class="row pl-3 pt-3 p-0">
              <div class="col-6 list-group mb-3">
                <li class="list-group-item">
                  <strong>1st</strong> Speaker P1
                  <span class="badge mr-2 badge-secondary float-right">72</span>
                  <ul>
                    <li><strong>Content</strong><span class="badge">28</span></li>
                    <li><strong>Style</strong><span class="badge">29</span></li>
                    <li><strong>Strategy</strong><span class="badge">15</span></li>
                  </ul>
                </li>
                <li class="list-group-item">
                  <strong>2nd</strong> Speaker P2
                  <span class="badge mr-2 badge-secondary float-right">74</span>
                </li>
                <li class="list-group-item">
                  <strong>3rd</strong> Speaker P3
                  <span class="badge mr-2 badge-secondary float-right">71</span>
                </li>
                <li class="list-group-item">
                  <strong>Reply</strong> Speaker P1
                  <span class="badge mr-2 badge-secondary float-right">36</span>
                </li>
                <li class="list-group-item active">
                  <strong>Total for Team Prop (Proposition)</strong>
                  <span class="badge badge-primary float-right">253</span>
                </li>
              </div>

              <div class="col-6 list-group mb-3">
                <li class="list-group-item">
                  <strong>1st</strong> Speaker O1
                  <span class="badge mr-2 badge-secondary float-right">70</span>
                </li>
                <li class="list-group-item">
                  <strong>2nd</strong> Speaker O2
                  <span class="badge mr-2 badge-secondary float-right">70</span>
                </li>
                <li class="list-group-item">
                  <strong>3rd</strong> Speaker O3
                  <span class="badge mr-2 badge-secondary float-right">70</span>
                </li>
                <li class="list-group-item">
                  <strong>Reply</strong> Speaker O2
                  <span class="badge mr-2 badge-secondary float-right">35</span>
                </li>
                <li class="list-group-item active">
                  <strong>Total for Team Opp (Opposition)</strong>
                  <span class="badge badge-primary float-right">245</span>
                </li>
              </div>
            </div>
          </div>
        </div>
        """
        debate = extractor.parse_scoresheet_html(sample_html, "123", "http://test")
        assert debate.motion == "This House would ban private tutoring"
        assert len(debate.ballots) == 1
        b = debate.ballots[0]
        assert b.adjudicator_name == "Scoresheet"
        assert b.proposition.team_name == "Team Prop"
        assert b.proposition.total_score == 253.0
        assert len(b.proposition.speeches) == 4
        assert b.proposition.speeches[0].speaker_name == "Speaker P1"
        assert b.proposition.speeches[0].content == 28.0
        assert b.opposition.team_name == "Team Opp"
        assert b.opposition.total_score == 245.0

    def test_parse_paneled_multi_adjudicator_scoresheet(self):
        extractor = TabbycatExtractor()
        sample_html = """
        <div class="card mt-3">
          <div class="card-body pb-1">
            <h4 class="card-title">From Judge Alpha (InstA)</h4>
            <div class="row pl-3 pt-3 p-0">
              <div class="col-6 list-group mb-3">
                <li class="list-group-item"><strong>1st</strong> P1<span class="badge float-right">75</span></li>
                <li class="list-group-item"><strong>2nd</strong> P2<span class="badge float-right">75</span></li>
                <li class="list-group-item"><strong>3rd</strong> P3<span class="badge float-right">75</span></li>
                <li class="list-group-item"><strong>Reply</strong> P1<span class="badge float-right">38</span></li>
                <li class="list-group-item active"><strong>Total for PropTeam (Proposition)</strong><span class="badge">263</span></li>
              </div>
              <div class="col-6 list-group mb-3">
                <li class="list-group-item"><strong>1st</strong> O1<span class="badge float-right">70</span></li>
                <li class="list-group-item"><strong>2nd</strong> O2<span class="badge float-right">70</span></li>
                <li class="list-group-item"><strong>3rd</strong> O3<span class="badge float-right">70</span></li>
                <li class="list-group-item"><strong>Reply</strong> O1<span class="badge float-right">35</span></li>
                <li class="list-group-item active"><strong>Total for OppTeam (Opposition)</strong><span class="badge">245</span></li>
              </div>
            </div>
          </div>
        </div>
        <div class="card mt-3">
          <div class="card-body pb-1">
            <h4 class="card-title">From Judge Beta (InstB)</h4>
            <div class="row pl-3 pt-3 p-0">
              <div class="col-6 list-group mb-3">
                <li class="list-group-item"><strong>1st</strong> P1<span class="badge float-right">74</span></li>
                <li class="list-group-item"><strong>2nd</strong> P2<span class="badge float-right">74</span></li>
                <li class="list-group-item"><strong>3rd</strong> P3<span class="badge float-right">74</span></li>
                <li class="list-group-item"><strong>Reply</strong> P1<span class="badge float-right">37</span></li>
                <li class="list-group-item active"><strong>Total for PropTeam (Proposition)</strong><span class="badge">259</span></li>
              </div>
              <div class="col-6 list-group mb-3">
                <li class="list-group-item"><strong>1st</strong> O1<span class="badge float-right">71</span></li>
                <li class="list-group-item"><strong>2nd</strong> O2<span class="badge float-right">71</span></li>
                <li class="list-group-item"><strong>3rd</strong> O3<span class="badge float-right">71</span></li>
                <li class="list-group-item"><strong>Reply</strong> O1<span class="badge float-right">35.5</span></li>
                <li class="list-group-item active"><strong>Total for OppTeam (Opposition)</strong><span class="badge">248.5</span></li>
              </div>
            </div>
          </div>
        </div>
        """
        debate = extractor.parse_scoresheet_html(sample_html, "999", "http://test")
        assert len(debate.ballots) == 2
        # Judge Alpha
        j1 = debate.ballots[0]
        assert j1.adjudicator_name == "Judge Alpha"
        assert j1.institution == "InstA"
        assert j1.proposition.total_score == 263.0
        assert j1.opposition.total_score == 245.0
        # Judge Beta
        j2 = debate.ballots[1]
        assert j2.adjudicator_name == "Judge Beta"
        assert j2.institution == "InstB"
        assert j2.proposition.total_score == 259.0
        assert j2.opposition.total_score == 248.5
