QA pages by code
==================


Read in order -- each page assumes the ones before it:

Generates four of the five QA pages under ``docs/source/qa/`` directly from
``tests/qa/catalogue.toml`` / ``tests/qa/known_gaps.txt`` and a real pytest collection pass, so none
of their numbers are typed by hand:

0. :doc:`coverage_by_feature` -- coverage by feature in catalogue order.
1. :doc:`feature_catalogue` -- every epic/feature/requirement, in catalogue order.
2. :doc:`test_cases`-- every real test, numbered ``TC-<TYPE>-NNN`` within its layer, plus one placeholder row per documented gap (CLAUDE.md SS7: a QA page that only shows shipped work is not
  a real QA artifact).
3. :doc:`traceability` -- one row per requirement: its test cases (by TC id, not raw node id),
  status, and coverage.
4. :doc:`coverage_by_feature` -- requirement coverage rolled up per feature.

Run by hand (no CI in this project, CLAUDE.md SS11's own disclosed gap):
``python -m utils.generate_qa_docs``. The fifth QA page, ``test_results.rst`` (actual pass/fail/
duration from a real run), is generated separately by
:mod:`utils.generate_test_results_rst`, since it needs a junit.xml a real pytest run produced --
this script only ever collects, never runs, tests.


.. toctree::
   :maxdepth: 2
   :numbered:

   coverage_by_feature
   feature_catalogue
   test_cases
   test_results
   traceability
   coverage_by_feature

