08 — Beyond hand-written queries: Graph representation learning as a higher abstraction layer
====================================================================================================

Why this page exists
-------------------------

:doc:`07-knowledge-graph-results` gave the failure-mode graph real, working root-cause queries --
but all three are Cypher someone had to already think to write. They can confirm a suspected
pattern ("does model X echo more than model Y") but cannot surface a pattern nobody thought to look
for. This page is the theoretical grounding for the next layer up: using the graph's own *structure*
-- not hand-picked Cypher -- to generate candidate patterns, flag structural outliers, and predict
risk for combinations never actually run. That's the concrete meaning behind "give the system a
sense for it" -- not a vague aspiration, but a named, 20-to-60-year-old academic subfield per
technique below, each with a real paper cited, not invented for this page.

This was a **design document for future work, not yet built** when first written -- same status as
:doc:`05-cicd`'s "current absence + concrete target pipeline" framing. Nothing on this page requires
a new dependency: every GDS procedure named below was confirmed **live, on the actual local
install**, not assumed from documentation (see *Confirmed available now* below).

**Update, 2026-09-05 (same day, later): Stage 4 shipped.** The failure-mode graph was promoted the
same day into the layered architecture (the agent instructions' SS1's "Fourth entry"), explicitly to leave room
to grow toward this page's techniques without a later redesign -- Stage 4 (structural embeddings +
Leiden communities) is the first to graduate: :meth:`core.domain.interfaces.GraphRepository.behavioral_communities`
/ :meth:`core.adapters.neo4j_repo.Neo4jGraphRepo.behavioral_communities`, exposed as a real button
on ``/knowledge_graph``. See the *Staged plan* section below for exactly what shipped vs. what's
still open.

The gap, precisely
-----------------------

The existing corpus-level analysis (the agent instructions SS3b, :doc:`../architecture`'s clustering pipeline)
already does real unsupervised structure-finding -- UMAP + HDBSCAN over the *linguistic feature
matrix* (cognitive load, lexical density, etc.). The failure-mode graph (:doc:`07-knowledge-graph-results`)
adds a second, independent data source: *relational* structure -- which archetype/bias/model/RAG-chunk
nodes are connected to which cascade outcomes. Nothing today combines these two views. That's the
actual gap: two independently valid ways of asking "what's similar to what" that have never been
cross-checked against each other.

Four techniques, each grounded in a real, cited source
------------------------------------------------------------

**1. Structural node embeddings (FastRP, GDS-native).** Represent every node (Archetype, Bias,
Model, CascadeOutcome, KnowledgeChunk) as a vector derived purely from its position in the graph --
not from any linguistic feature. The foundational method for this is node2vec (biased random
walks + skip-gram) [Grover2016]_. This project's actual choice is **FastRP**, not node2vec directly:
Neo4j's own benchmarking reports FastRP as "up to 75,000 times faster than Node2Vec with equivalent
accuracy" [Neo4jFastRP]_, and FastRP's own theoretical grounding (very sparse random projection,
backed by the Johnson-Lindenstrauss lemma) is a real, separate, cited result [Chen2019]_ -- not a
Neo4j marketing claim taken on faith. This specific tradeoff -- 5 orders of magnitude cheaper for
"equivalent accuracy" -- is exactly what the agent instructions' own standing "weak machine" constraint calls
for, the same reasoning that picked ``all-MiniLM-L6-v2``/``nli-MiniLM2-L6-H768`` over larger models
elsewhere in this project.

**2. Community detection (Leiden, not Louvain).** Cluster the embedded graph into "behavioral
communities" -- groups of archetype/bias/model/outcome nodes that are more densely connected to
each other than to the rest of the graph. The obvious default, Louvain [Blondel2008]_, has a real,
measured defect: its own successor paper found Louvain "may yield arbitrarily badly connected
communities... in experimental analysis, up to 25% of the communities are badly connected and up to
16% are disconnected" [Traag2019]_. Leiden fixes this with a provable well-connectedness guarantee
and is the direct GDS-native replacement -- picking Leiden over Louvain here is itself a real,
citable measurement-validity decision, the same kind of threshold-inversion-caliber finding this
project already has a track record of making (see :doc:`04-llm-analytics`'s Layer 1 story), not a
default accepted without checking.

**3. Cross-validating the two clustering views (methodological triangulation).** Once Leiden
produces graph-structural communities, compare them against the existing UMAP/HDBSCAN
feature-based clusters over the *same* corpus. This is not a novel idea invented for this
project -- it is the multitrait-multimethod matrix, Campbell & Fiske's 1959 foundational argument
that a construct's validity is strengthened when *independent measurement methods* converge, and
that divergence between methods is itself informative, not noise to explain away
[CampbellFiske1959]_. Concretely: agreement between the two clusterings (measurable via e.g.
normalized mutual information) is real convergent evidence that a behavioral grouping reflects
something structural, not an artifact of one particular metric space; disagreement flags archetypes
that look similar linguistically but sit in different relational neighborhoods (or vice versa) --
a genuinely new finding neither method alone could produce.

**A smaller-scale version of this triangulation already happened, 2026-09-05, between Stages 4 and
5 (not yet the full UMAP/HDBSCAN cross-check described above, which is still open):** Stage 4's
Leiden run and Stage 5's node-similarity run are two independent GDS algorithms over the same
projected graph, and they agreed -- Leiden placed Neutral/Detached/Expressive archetypes and qwen/
tinyllama models in one community; node similarity independently scored those same nodes at
~0.9999 similarity to each other. Two different algorithms landing on the same grouping from the
same underlying topology is a real, if modest, instance of exactly the convergent-evidence argument
this technique is named for.

**4. Structural anomaly / analogy detection (node similarity).** Run ``gds.knn.stream`` over the
FastRP embeddings to answer two symmetric questions directly: "what is this archetype/bias/model
structurally most like" (an automatic analogy -- the literal mechanism behind "this reminds me
of..."), and, at the low-similarity extreme, "what does this resemble nothing else in the corpus"
-- a real structural anomaly, in the sense formalized by the graph-anomaly-detection literature
[Akoglu2015]_. This is a meaningfully different anomaly signal than a simple high-failure-rate flag:
a node can have an entirely ordinary pass rate while still having a structurally unusual *pattern*
of which cascade stages it reaches, which nothing in the current failure-mode queries would surface.

**Correction, 2026-09-05 (found while implementing Stage 4, not assumed correct from this page's
own first draft):** this technique originally named ``gds.nodeSimilarity`` as the procedure that
consumes FastRP's embedding vectors. Checked directly against the live install's own procedure
signatures (``SHOW PROCEDURES``), not from memory: ``gds.nodeSimilarity`` computes Jaccard/overlap
similarity over *shared relationships* (a purely topological measure, no embedding input at all);
``gds.knn`` is the actual procedure that takes an embedding-valued node property and computes
cosine/Euclidean similarity between vectors. Corrected above and in the *Confirmed available now*
table -- the same "verify the exact procedure signature before writing code against it" discipline
this project already applies everywhere else (e.g. this page's own Stage 4 write-up below).

**5. Link prediction for untried combinations.** Given the graph of (archetype, bias, model) triples
already run, predict which *untried* combinations are likely to land on a negative
``CascadeOutcome`` -- before spending real Ollama time generating them. Link prediction is a
20-year-old, well-established subfield, not a speculative idea: Liben-Nowell & Kleinberg's
foundational formalization asks exactly this question ("given a snapshot of a network, which new
connections are likely to form") using pure topology [LibenNowell2007]_; modern knowledge-graph-
specific approaches (embedding-based link prediction, surveyed comprehensively as of 2024
[Wang2024]_) extend this to typed, multi-relational graphs -- exactly this project's schema
(``CONDITIONED_ON``/``GENERATED_BY``/``REACHED`` are distinct relation types, not one flat edge).
This is the most literal reading of "give the system a sense for it": a real predicted-risk score
for a combination that has never actually been generated.

Confirmed available now, not assumed
------------------------------------------

Checked directly against the live local install (the same one :doc:`07-knowledge-graph-results`
fixed and verified), not taken from documentation alone:

.. list-table::
   :widths: 55 20 25
   :header-rows: 1

   * - Procedure
     - Available
     - Use above
   * - ``gds.fastRP.stream``
     - ✅ yes
     - Technique 1 (structural embeddings)
   * - ``gds.node2vec.stream``
     - ✅ yes (available, but FastRP is the recommended default -- see above)
     - Technique 1, alternative
   * - ``gds.leiden.stream``
     - ✅ yes
     - Technique 2 (community detection)
   * - ``gds.nodeSimilarity.stream``
     - ✅ yes (but see the Technique 4 correction above -- topological Jaccard/overlap, not
       embedding-based; not what this page originally implied)
     - N/A -- not the right procedure for Technique 4
   * - ``gds.knn.stream``
     - ✅ yes -- confirmed 2026-09-05 while implementing Stage 4
     - Technique 4 (analogy / anomaly, over FastRP embeddings)
   * - ``gds.beta.pipeline.linkPrediction.create``
     - ✅ yes (pipeline API)
     - Technique 5 (link prediction)
   * - ``gds.linkPrediction.train`` / ``gds.alpha.linkprediction.adamicAdar``
     - ❌ not registered on this GDS version
     - Use the pipeline API above instead, not these older/alpha names

A staged plan, building on Stages 1-3 already shipped
------------------------------------------------------------

Each stage below gets a **real validation step**, not "ran the algorithm, eyeballed the output" --
matching the same discipline :func:`core.services.cluster_discovery.compute_fit_indices` already
applies to the existing UMAP/HDBSCAN pipeline.

- **Stage 4 -- structural embeddings + Leiden communities. Partially shipped, 2026-09-05.**
  Real, corrected implementation note: ``gds.leiden.stream`` does not accept a raw embedding
  vector as input (there is no GDS procedure that runs community detection directly "on" an
  embedding space) -- Leiden runs on real graph topology/weights instead. What actually shipped:
  Archetype/Bias/Model/CascadeOutcome nodes are never directly connected in the base schema (they
  only meet through a shared ``Response``), so a real, weighted ``CO_OCCURS_WITH`` relationship is
  materialized first (shared-response co-occurrence count), then ``gds.leiden.stream`` runs on
  that topology, and ``gds.fastRP.stream`` runs separately over the same projection -- real
  structural embeddings, available for Stage 5/6 below, not yet consumed by anything.
  *Validated with*: GDS's own reported modularity (real, not eyeballed -- ``gds.leiden.stats``),
  surfaced directly in the ``/knowledge_graph`` UI alongside the community table, including an
  honest disclosure when the number is unflattering (a small, densely-connected 25-node graph
  measured 0.023 modularity on real synced data -- reported as-is, not hidden). **Still open, not
  done here:** the normalized-mutual-information cross-check against the existing UMAP/HDBSCAN
  cluster assignments (Technique 3) -- a substantially separate feature needing a join between two
  independent systems' per-response cluster/community labels for the same run, not a small
  addition to this method.
- **Stage 5 -- node similarity for analogy/anomaly. Shipped, 2026-09-05.**
  :meth:`core.domain.interfaces.GraphRepository.structural_similarity` /
  :meth:`core.adapters.neo4j_repo.Neo4jGraphRepo.structural_similarity`, a 5th button on
  ``/knowledge_graph``. Real, corrected implementation: ``gds.fastRP.mutate`` writes the
  embedding as an in-memory node property, then ``gds.knn.stream`` (not ``gds.nodeSimilarity`` --
  see the Technique 4 correction above) computes cosine similarity over those vectors.
  *Validated with*: a real spot-check against the live synced graph before writing any tests --
  the top pairs found Neutral/Detached/Expressive archetypes and qwen/tinyllama models as near-
  identical (~0.9999 similarity), the exact same grouping Stage 4's Leiden run independently
  placed in one community, real convergent evidence between two independent methods (Technique 3's
  triangulation argument, demonstrated concretely rather than left as a citation); the single most
  anomalous node was the ``personalization`` bias, whose best match to anything else scored 0.0 --
  reported as-is in the UI, not smoothed over.
- **Stage 6 -- link prediction for untried combinations. Attempted, 2026-09-05, real negative
  result -- documented honestly, not shipped.** Two real, escalating attempts, not a single quick
  try: a composite ``ArchetypeBiasCombo`` node (Archetype x Bias, since GDS Link Prediction predicts
  pairwise edges and this project's real risk unit is a 3-way triple), a real, data-driven ``RISKY``
  label (median split on real per-triple Judge-FAIL rate, not an arbitrary threshold), FastRP
  embeddings, HADAMARD features, a logistic-regression candidate, and a real train/test split via
  ``gds.beta.pipeline.linkPrediction``.

  **Attempt 1** (the failure-mode graph's existing 500-response run, plus a small 75-response
  feasibility batch adding one new real bias value across 3 of the 5 archetypes, deliberately
  leaving the other 2 untried for that bias so a genuine "unseen but structurally-informed" target
  existed): 10 ``ArchetypeBiasCombo`` nodes, 15 real ``RISKY`` edges. Training ran without error and
  reported a real held-out test AUCPR (0.75-0.83, varying between runs since GDS's own split is
  stochastic) -- but every single ``predict.stream`` output, across all 35 candidate pairs, came
  back as **exactly** ``0.5`` probability. The model had collapsed to predicting the base rate for
  everything; 15 positive examples (about 8-9 after the test split) is too little for the classifier
  to learn anything.

  **Attempt 2** (a real, substantially larger follow-up: 200 more real Ollama-generated responses
  across 4 more real bias values, fully crossing all 5 archetypes and all 5 models -- 275 new real
  responses total across both attempts, not a synthetic top-up): 30 ``ArchetypeBiasCombo`` nodes, 55
  real ``RISKY`` edges, nearly 4x Attempt 1's positive-edge count. Training metrics looked
  materially better and more stable this time (train/validation AUCPR ~0.89, test AUCPR 0.68) --
  but the real predictions were still functionally flat: 95 candidate pairs spanned only 11 distinct
  probability values, all within **0.4996-0.4998**, a spread of ~0.0002. A real bug in the
  verification script itself was found and fixed along the way (``predict.stream``'s ``node1``/
  ``node2`` did not come back in ``sourceNodeLabel``/``targetNodeLabel`` order -- confirmed by
  checking ``labels()`` directly, not assumed), which changed *which* combinations the top
  predictions named but did not change the underlying finding: still no real discrimination.

  **Root cause, not just "needs more data" (already tried tripling the positive-edge count and it
  didn't move the needle) -- a real structural mismatch between this problem and graph-topology
  embeddings:** every ``ArchetypeBiasCombo`` node has a ``TRIED_WITH`` edge to nearly every ``Model``
  node -- the graph topology is close to uniform across combos, differing only in the sparse
  ``RISKY`` label layered on top. FastRP embeds *structural position*, and structural position
  barely varies here. What actually drives real risk in this data, visible directly in the raw
  per-triple fail rates without any graph ML at all, is overwhelmingly **which model** (``llama3``/
  ``phi3`` fail far more than ``qwen``/``tinyllama``/``mistral``, holding archetype and bias
  constant) -- a signal already fully captured by which ``Model`` node an edge points to, not by
  anything a structural embedding can add. This is a real, evidence-backed conclusion, not
  abandoned prematurely: graph-topology-based link prediction is not the right tool for *this*
  specific risk signal, on *this* graph's shape. **Not shipped as a UI feature** -- a page showing a
  model with no real discriminative power would be exactly the kind of hollow, impressive-looking
  result this project's own measurement-validity discipline exists to catch, not produce. If this
  is revisited, the more promising direction suggested by the diagnosis above is a plain classifier
  over explicit (archetype, bias, model) categorical features rather than a graph-embedding
  approach -- a genuinely different attempt, not a bigger version of the same one.

Honest scope note
----------------------

**Superseded, 2026-09-05:** this page originally stated everything here stays inside the agent instructions
SS1's Neo4j quarantine, with no promotion into ``core.domain``/``core.adapters`` at all. That's no
longer true at all, as of the same day: the failure-mode graph was promoted first (explicitly to
leave room for this page's techniques to grow into real, tested code), Stages 4 and 5 both
graduated into real, shipped code the same day (Leiden communities, node-similarity analogy/
anomaly), and later the same day the *rest* of the legacy Neo4j subsystem (the original Archetype/
Bias co-occurrence graph, the PageRank scripts, Hypothesis Testing, Uncertainty Analysis) was
migrated too -- there is no longer any untouched Neo4j code in this repository at all. Stage 6
(link prediction) was attempted, twice, with real escalating data, and closed as a real, documented
negative result rather than shipped -- see its own entry above for the full finding.
And a direct caution on the "intuition" framing itself: everything above produces a *score* --
similarity, community assignment, predicted-risk probability -- not a verdict. Treating a
structural-anomaly flag or a link-prediction score as ground truth without the validation step
listed for its stage would repeat exactly the mistake this project already caught once for Layer 1
(an unvalidated intuition about what "should" correlate turned out to be backwards on real data --
see :doc:`04-llm-analytics`). The discipline that makes that story worth telling is checking the
intuition against real data before trusting it, not skipping that step because the technique sounds
sophisticated.

.. rubric:: References

.. [Grover2016] Grover, A., & Leskovec, J. (2016). node2vec: Scalable Feature Learning for
   Networks. *Proceedings of the 22nd ACM SIGKDD International Conference on Knowledge Discovery
   and Data Mining*, 855-864. https://arxiv.org/abs/1607.00653
.. [Neo4jFastRP] Neo4j Graph Data Science documentation. Fast Random Projection.
   https://neo4j.com/docs/graph-data-science/current/machine-learning/node-embeddings/fastrp/
.. [Chen2019] Chen, H., Sultan, S. F., Tian, Y., Chen, M., & Skiena, S. (2019). Fast and Accurate
   Network Embeddings via Very Sparse Random Projection. *Proceedings of the 28th ACM International
   Conference on Information and Knowledge Management*. https://arxiv.org/abs/1908.11512
.. [Blondel2008] Blondel, V. D., Guillaume, J.-L., Lambiotte, R., & Lefebvre, E. (2008). Fast
   unfolding of communities in large networks. *Journal of Statistical Mechanics: Theory and
   Experiment*, 2008(10).
.. [Traag2019] Traag, V. A., Waltman, L., & van Eck, N. J. (2019). From Louvain to Leiden:
   guaranteeing well-connected communities. *Scientific Reports*, 9, 5233.
   https://arxiv.org/abs/1810.08473
.. [CampbellFiske1959] Campbell, D. T., & Fiske, D. W. (1959). Convergent and discriminant
   validation by the multitrait-multimethod matrix. *Psychological Bulletin*, 56(2), 81-105.
.. [Akoglu2015] Akoglu, L., Tong, H., & Koutra, D. (2015). Graph based anomaly detection and
   description: a survey. *Data Mining and Knowledge Discovery*, 29(3), 626-688.
   https://doi.org/10.1007/s10618-014-0365-y
.. [LibenNowell2007] Liben-Nowell, D., & Kleinberg, J. (2007). The link-prediction problem for
   social networks. *Journal of the American Society for Information Science and Technology*,
   58(7), 1019-1031. https://www.cs.cornell.edu/home/kleinber/link-pred.pdf
.. [Wang2024] Survey coverage of modern knowledge-graph embedding and link-prediction approaches,
   2024. *Knowledge Graph Embeddings: A Comprehensive Survey on Capturing Relation Properties*.
   https://arxiv.org/abs/2410.14733
